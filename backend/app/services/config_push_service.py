import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import UnicornException


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_command_list(commands: Optional[List[str]], commands_text: Optional[str]) -> List[str]:
    out: List[str] = []
    if commands:
        for c in commands:
            s = str(c or "").strip()
            if s:
                out.append(s)
    if commands_text:
        for line in str(commands_text).splitlines():
            s = str(line or "").strip()
            if not s:
                continue
            if s.startswith("#"):
                continue
            out.append(s)
    cleaned: List[str] = []
    for c in out:
        s = str(c).strip()
        if not s:
            continue
        cleaned.append(s)
    return cleaned


def summarize_commands(commands: List[str], max_len: int = 140) -> str:
    text = "; ".join([str(x) for x in (commands or []) if str(x).strip()])
    if len(text) <= int(max_len):
        return text
    return text[: max(0, int(max_len) - 3)] + "..."


class ConfigPushService:
    QUEUE_STREAM = "config_push:queue"

    @staticmethod
    def events_stream(job_id: int) -> str:
        return f"config_push:job:{int(job_id)}:events"

    @staticmethod
    def cancel_key(job_id: int) -> str:
        return f"config_push:job:{int(job_id)}:cancel"

    @staticmethod
    async def _emit_event(job_id: int, payload: Dict[str, Any]) -> None:
        redis = redis_manager.get_client()
        body = {"ts": _utc_iso(), **{str(k): ("" if v is None else str(v)) for k, v in (payload or {}).items()}}
        try:
            await redis.xadd(ConfigPushService.events_stream(job_id), body, maxlen=20000, approximate=True)
        except Exception:
            pass

    @staticmethod
    async def _write_log(job_id: int, type_: str, content: str, subject: Optional[str] = None) -> None:
        try:
            await db.execute(
                """
                INSERT INTO config_push_logs (job_id, type, subject, content)
                VALUES ($1, $2, $3, $4)
                """,
                int(job_id),
                str(type_),
                str(subject) if subject is not None else None,
                str(content or ""),
            )
        except Exception:
            return

    @staticmethod
    async def create_job(creator_id: int, title: Optional[str], device_ids: List[int], commands: List[str]) -> int:
        uid = int(creator_id)
        ids = [int(x) for x in (device_ids or [])]
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise UnicornException(400, "未选择设备")
        cmd_list = [str(x).strip() for x in (commands or []) if str(x).strip()]
        if not cmd_list:
            raise UnicornException(400, "命令列表为空")
        if len(cmd_list) > 500:
            raise UnicornException(400, "命令条数过多（最多 500 条）")
        t = str(title or "").strip() or "配置下发任务"

        device_rows = await db.fetch_all(
            """
            SELECT id, device_name, ipv4
            FROM network_devices
            WHERE id = ANY($1::int[])
              AND deleted_at IS NULL
            ORDER BY id
            """,
            ids,
        )
        devices = [dict(r) for r in (device_rows or [])]
        found_ids = {int(d.get("id")) for d in devices if d and d.get("id") is not None}
        missing = [int(x) for x in ids if int(x) not in found_ids]
        if missing:
            raise UnicornException(400, f"设备不存在或已删除: {missing}")
        for d in devices:
            ip = str(d.get("ipv4") or "").strip()
            if not ip:
                raise UnicornException(400, f"设备缺少 IPv4: {int(d.get('id'))}")

        pool = db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                job_row = await conn.fetchrow(
                    """
                    INSERT INTO config_push_jobs
                        (title, creator_id, status, command_list, device_count, success_count, fail_count)
                    VALUES
                        ($1, $2, 'pending', $3::jsonb, $4, 0, 0)
                    RETURNING id
                    """,
                    t,
                    uid,
                    json.dumps(cmd_list, ensure_ascii=False),
                    int(len(devices)),
                )
                job_id = int(job_row["id"])

                for d in devices:
                    await conn.execute(
                        """
                        INSERT INTO config_push_job_items
                            (job_id, device_id, device_name, device_ip, status)
                        VALUES
                            ($1, $2, $3, $4, 'pending')
                        """,
                        int(job_id),
                        int(d["id"]),
                        str(d.get("device_name") or ""),
                        str(d.get("ipv4") or ""),
                    )

        await ConfigPushService._write_log(job_id, "job_created", summarize_commands(cmd_list), subject=t)
        await ConfigPushService._emit_event(
            job_id,
            {"type": "job_created", "job_id": str(job_id), "title": t, "summary": summarize_commands(cmd_list)},
        )

        redis = redis_manager.get_client()
        try:
            await redis.xadd(
                ConfigPushService.QUEUE_STREAM,
                {"job_id": str(job_id), "created_at": str(time.time())},
                maxlen=10000,
                approximate=True,
            )
        except Exception as e:
            await ConfigPushService._write_log(job_id, "enqueue_failed", str(e))
            await ConfigPushService._emit_event(job_id, {"type": "enqueue_failed", "job_id": str(job_id), "error": str(e)})
        return int(job_id)

    @staticmethod
    async def get_job(job_id: int) -> Dict[str, Any]:
        job = await db.fetch_one(
            """
            SELECT id, title, creator_id, status, command_list, device_count, success_count, fail_count, created_at, finished_at
            FROM config_push_jobs
            WHERE id = $1
            """,
            int(job_id),
        )
        if not job:
            raise UnicornException(404, "任务不存在")
        items = await db.fetch_all(
            """
            SELECT id, device_id, device_name, device_ip, status, error_message, started_at, finished_at
            FROM config_push_job_items
            WHERE job_id = $1
            ORDER BY id
            """,
            int(job_id),
        )
        return {"job": dict(job), "items": [dict(x) for x in (items or [])]}

    @staticmethod
    async def cancel_job(job_id: int, actor_id: int) -> None:
        job = await db.fetch_one(
            "SELECT id, status FROM config_push_jobs WHERE id = $1",
            int(job_id),
        )
        if not job:
            raise UnicornException(404, "任务不存在")
        status = str(job.get("status") or "")
        if status in {"success", "failed", "canceled"}:
            return

        try:
            await db.execute(
                """
                UPDATE config_push_jobs
                SET status = CASE WHEN status IN ('pending', 'running', 'canceling') THEN 'canceling' ELSE status END
                WHERE id = $1
                """,
                int(job_id),
            )
        except Exception:
            pass

        redis = redis_manager.get_client()
        try:
            await redis.set(ConfigPushService.cancel_key(job_id), "1", ex=86400)
        except Exception:
            pass

        await ConfigPushService._write_log(job_id, "job_cancel_requested", f"actor={int(actor_id)}")
        await ConfigPushService._emit_event(job_id, {"type": "job_cancel_requested", "job_id": str(job_id)})
