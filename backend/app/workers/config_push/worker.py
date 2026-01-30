import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from netmiko import ConnectHandler
from redis.exceptions import ResponseError

from app.core.database import db
from app.core.redis import redis_manager
from app.drivers.ssh_retry import classify_ssh_failure
from app.models.orm.audit import DeviceChangeLog, SshCommandAuditLog
from app.services.config_push_service import ConfigPushService


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_job_final(status: str, finished_at: Any) -> bool:
    s = str(status or "")
    if finished_at is not None:
        return True
    return s in {"success", "failed", "partial", "canceled"}


def _pick_netmiko_device_type(value) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return "linux"
    if s in {"linux", "huawei", "cisco_ios", "cisco_xe", "cisco_xr", "juniper", "arista_eos"}:
        return s
    if s in {"server", "服务器"}:
        return "linux"
    if s in {"router", "switch", "firewall"}:
        return "huawei"
    if s in {"路由器", "交换机", "防火墙"}:
        return "huawei"
    if "huawei" in s or "华为" in s:
        return "huawei"
    if "cisco" in s or "ios" in s:
        return "cisco_ios"
    if "juniper" in s or "junos" in s:
        return "juniper"
    if "arista" in s or "eos" in s:
        return "arista_eos"
    return "linux"


class ConfigPushWorker:
    def __init__(
        self,
        *,
        consumer_group: str = "config_push",
        consumer_name: str = "worker-1",
        max_concurrency: int = 5,
        device_lock_ttl_seconds: int = 900,
        job_lock_ttl_seconds: int = 7200,
    ) -> None:
        self.consumer_group = str(consumer_group)
        self.consumer_name = str(consumer_name)
        self.max_concurrency = int(max_concurrency) if int(max_concurrency) > 0 else 1
        self.device_lock_ttl_seconds = int(device_lock_ttl_seconds) if int(device_lock_ttl_seconds) > 0 else 300
        self.job_lock_ttl_seconds = int(job_lock_ttl_seconds) if int(job_lock_ttl_seconds) > 0 else 3600
        self._running = False
        self._main_task: Optional[asyncio.Task] = None
        self._held_device_locks: Dict[int, int] = {}

        self._unlock_lua = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) "
            "else return 0 end"
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            await self._cleanup_stale_device_locks()
        except Exception:
            pass
        self._main_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        try:
            await self._release_all_held_device_locks()
        except Exception:
            pass
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except Exception:
                pass
            self._main_task = None

    def _job_lock_key(self, job_id: int) -> str:
        return f"config_push:job:{int(job_id)}:worker_lock"

    def _device_lock_key(self, device_id: int) -> str:
        return f"ssh:lock:device:{int(device_id)}"

    async def _safe_unlock_device_lock(self, device_id: int, expected_job_id: int, *, retries: int = 3) -> None:
        redis = redis_manager.get_client()
        key = self._device_lock_key(int(device_id))
        for _ in range(max(1, int(retries))):
            try:
                await redis.eval(self._unlock_lua, 1, key, str(int(expected_job_id)))
                return
            except Exception:
                await asyncio.sleep(0.05)

    async def _release_all_held_device_locks(self) -> None:
        held = list(self._held_device_locks.items())
        for device_id, job_id in held:
            await self._safe_unlock_device_lock(int(device_id), int(job_id), retries=2)
            self._held_device_locks.pop(int(device_id), None)

    async def _cleanup_stale_device_locks(self) -> None:
        redis = redis_manager.get_client()
        cursor = 0
        keys: List[str] = []
        while True:
            cursor, batch = await redis.scan(cursor, match="ssh:lock:device:*", count=200)
            keys.extend([str(k) for k in (batch or [])])
            if int(cursor) == 0:
                break
        keys = list(dict.fromkeys(keys))
        if not keys:
            return

        for key in keys:
            try:
                holder = await redis.get(key)
                ttl = await redis.ttl(key)
            except Exception:
                continue
            if holder is None:
                continue
            holder_str = str(holder).strip()
            if ttl is not None and int(ttl) < 0:
                try:
                    await redis.delete(key)
                except Exception:
                    pass
                continue

            holder_job_id = None
            try:
                holder_job_id = int(holder_str)
            except Exception:
                holder_job_id = None
            if not holder_job_id:
                try:
                    await redis.delete(key)
                except Exception:
                    pass
                continue

            try:
                row = await db.fetch_one(
                    "SELECT status, finished_at FROM config_push_jobs WHERE id = $1",
                    int(holder_job_id),
                )
                status = str((row.get("status") if row else "") or "")
                finished_at = row.get("finished_at") if row else None
                if _is_job_final(status, finished_at):
                    try:
                        await redis.delete(key)
                    except Exception:
                        pass
            except Exception:
                continue

    async def _try_acquire_device_lock(self, job_id: int, device_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        redis = redis_manager.get_client()
        key = self._device_lock_key(int(device_id))
        try:
            got = await redis.set(key, str(int(job_id)), nx=True, ex=self.device_lock_ttl_seconds)
        except Exception:
            got = False
        if got:
            self._held_device_locks[int(device_id)] = int(job_id)
            return True, None, None

        holder = None
        ttl = None
        try:
            raw = await redis.get(key)
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            holder = str(raw) if raw is not None else None
        except Exception:
            holder = None
        try:
            ttl = int(await redis.ttl(key))
        except Exception:
            ttl = None

        holder_job_id = None
        try:
            holder_job_id = int(holder) if holder is not None else None
        except Exception:
            holder_job_id = None

        if holder_job_id:
            try:
                row = await db.fetch_one(
                    "SELECT status, finished_at FROM config_push_jobs WHERE id = $1",
                    int(holder_job_id),
                )
                status = str((row.get("status") if row else "") or "")
                finished_at = row.get("finished_at") if row else None
                if _is_job_final(status, finished_at):
                    try:
                        await redis.delete(key)
                    except Exception:
                        pass
                    try:
                        got2 = await redis.set(key, str(int(job_id)), nx=True, ex=self.device_lock_ttl_seconds)
                    except Exception:
                        got2 = False
                    if got2:
                        self._held_device_locks[int(device_id)] = int(job_id)
                        return True, None, None
            except Exception:
                pass

        return False, holder, ttl

    async def _ensure_group(self) -> None:
        redis = redis_manager.get_client()
        try:
            await redis.xgroup_create(
                ConfigPushService.QUEUE_STREAM,
                self.consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _loop(self) -> None:
        await self._ensure_group()
        redis = redis_manager.get_client()
        sem = asyncio.Semaphore(self.max_concurrency)
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                msgs = await redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {ConfigPushService.QUEUE_STREAM: ">"},
                    count=1,
                    block=1000,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(1.0)
                continue

            if not msgs:
                continue

            for _stream_name, entries in msgs:
                for msg_id, fields in (entries or []):
                    job_id = None
                    try:
                        job_id = int((fields or {}).get("job_id"))
                    except Exception:
                        job_id = None
                    if not job_id:
                        try:
                            await redis.xack(ConfigPushService.QUEUE_STREAM, self.consumer_group, msg_id)
                        except Exception:
                            pass
                        continue

                    try:
                        await self._handle_job(job_id, sem=sem, loop=loop)
                    except Exception as e:
                        logger.error(f"Handle job {job_id} failed: {e}")
                    finally:
                        try:
                            await redis.xack(ConfigPushService.QUEUE_STREAM, self.consumer_group, msg_id)
                        except Exception:
                            pass

    async def _handle_job(self, job_id: int, *, sem: asyncio.Semaphore, loop: asyncio.AbstractEventLoop) -> None:
        redis = redis_manager.get_client()
        got_lock = False
        try:
            got_lock = await redis.set(self._job_lock_key(job_id), self.consumer_name, nx=True, ex=self.job_lock_ttl_seconds)
        except Exception:
            got_lock = False
        if not got_lock:
            return

        try:
            await self._execute_job(job_id, sem=sem, loop=loop)
        finally:
            try:
                await redis.delete(self._job_lock_key(job_id))
            except Exception:
                pass

    async def _execute_job(self, job_id: int, *, sem: asyncio.Semaphore, loop: asyncio.AbstractEventLoop) -> None:
        job_row = await db.fetch_one(
            """
            SELECT id, title, creator_id, status, command_list
            FROM config_push_jobs
            WHERE id = $1
            """,
            int(job_id),
        )
        if not job_row:
            return
        status = str(job_row.get("status") or "")
        if status in {"success", "failed", "canceled"}:
            return
        creator_id = int(job_row.get("creator_id") or 0)
        job_title = str(job_row.get("title") or "")

        commands = job_row.get("command_list")
        if isinstance(commands, list):
            cmd_list = [str(x).strip() for x in commands if str(x).strip()]
        else:
            cmd_list = []
            try:
                if commands:
                    parsed = commands
                    if isinstance(parsed, str):
                        import json
                        parsed = json.loads(parsed)
                    if isinstance(parsed, list):
                        cmd_list = [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                cmd_list = []
        if not cmd_list:
            await db.execute(
                "UPDATE config_push_jobs SET status='failed', finished_at=$2 WHERE id=$1",
                int(job_id),
                _utc_now(),
            )
            await ConfigPushService._emit_event(int(job_id), {"type": "job_failed", "reason": "empty_commands"})
            return

        await db.execute(
            """
            UPDATE config_push_jobs
            SET status = CASE WHEN status IN ('pending', 'canceling') THEN 'running' ELSE status END
            WHERE id = $1
            """,
            int(job_id),
        )
        await ConfigPushService._emit_event(int(job_id), {"type": "job_started", "job_id": str(job_id)})

        items = await db.fetch_all(
            """
            SELECT id, device_id, device_name, device_ip, status
            FROM config_push_job_items
            WHERE job_id = $1
            ORDER BY id
            """,
            int(job_id),
        )
        item_rows = [dict(x) for x in (items or [])]

        tasks = [
            asyncio.create_task(self._run_item(job_id, creator_id, job_title, item, cmd_list, sem=sem, loop=loop))
            for item in item_rows
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        agg = await db.fetch_one(
            """
            SELECT
                COUNT(1) AS total,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS fail_count,
                SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) AS canceled_count
            FROM config_push_job_items
            WHERE job_id = $1
            """,
            int(job_id),
        )
        total = int((agg.get("total") if agg else 0) or 0)
        success_count = int((agg.get("success_count") if agg else 0) or 0)
        fail_count = int((agg.get("fail_count") if agg else 0) or 0)
        canceled_count = int((agg.get("canceled_count") if agg else 0) or 0)

        redis = redis_manager.get_client()
        cancel_flag = False
        try:
            cancel_flag = bool(await redis.get(ConfigPushService.cancel_key(job_id)))
        except Exception:
            cancel_flag = False

        if cancel_flag and canceled_count == total:
            final_status = "canceled"
        elif fail_count > 0 and success_count > 0:
            final_status = "partial"
        elif fail_count > 0:
            final_status = "failed"
        elif cancel_flag and canceled_count > 0:
            final_status = "partial"
        else:
            final_status = "success"

        await db.execute(
            """
            UPDATE config_push_jobs
            SET status=$2, device_count=$3, success_count=$4, fail_count=$5, finished_at=$6
            WHERE id=$1
            """,
            int(job_id),
            str(final_status),
            int(total),
            int(success_count),
            int(fail_count),
            _utc_now(),
        )
        await ConfigPushService._emit_event(
            int(job_id),
            {
                "type": "job_finished",
                "job_id": str(job_id),
                "status": str(final_status),
                "success_count": str(success_count),
                "fail_count": str(fail_count),
                "canceled_count": str(canceled_count),
            },
        )

    async def _run_item(
        self,
        job_id: int,
        creator_id: int,
        job_title: str,
        item: Dict[str, Any],
        commands: List[str],
        *,
        sem: asyncio.Semaphore,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        item_id = int(item.get("id"))
        device_id = int(item.get("device_id"))

        async with sem:
            redis = redis_manager.get_client()
            try:
                if await redis.get(ConfigPushService.cancel_key(job_id)):
                    await db.execute(
                        "UPDATE config_push_job_items SET status='canceled', finished_at=$2 WHERE id=$1 AND status IN ('pending','running')",
                        int(item_id),
                        _utc_now(),
                    )
                    await ConfigPushService._emit_event(job_id, {"type": "item_canceled", "device_id": str(device_id)})
                    return
            except Exception:
                pass

            got_lock, lock_holder, lock_ttl = await self._try_acquire_device_lock(int(job_id), int(device_id))
            if not got_lock:
                details = []
                if lock_holder is not None:
                    details.append(f"holder={lock_holder}")
                if lock_ttl is not None and lock_ttl >= 0:
                    details.append(f"ttl={lock_ttl}s")
                suffix = f" ({', '.join(details)})" if details else ""
                await db.execute(
                    "UPDATE config_push_job_items SET status='failed', error_message=$2, finished_at=$3 WHERE id=$1 AND status IN ('pending','running')",
                    int(item_id),
                    f"设备连接占用中{suffix}",
                    _utc_now(),
                )
                await ConfigPushService._emit_event(
                    job_id,
                    {
                        "type": "item_failed",
                        "device_id": str(device_id),
                        "error": "device_locked",
                        "lock_holder": str(lock_holder or ""),
                        "lock_ttl": str(lock_ttl if lock_ttl is not None else ""),
                    },
                )
                return

            stop_flag = threading.Event()
            cancel_task = asyncio.create_task(self._watch_cancel(job_id, stop_flag))
            try:
                device_row = await db.fetch_one(
                    """
                    SELECT id, device_name, ipv4, user_name, password, ssh_port, device_type
                    FROM network_devices
                    WHERE id = $1
                      AND deleted_at IS NULL
                    """,
                    int(device_id),
                )
                if not device_row:
                    await db.execute(
                        "UPDATE config_push_job_items SET status='failed', error_message=$2, finished_at=$3 WHERE id=$1",
                        int(item_id),
                        "设备不存在或已删除",
                        _utc_now(),
                    )
                    await ConfigPushService._emit_event(job_id, {"type": "item_failed", "device_id": str(device_id), "error": "device_missing"})
                    return

                cfg = None
                try:
                    cfg = await db.fetch_one(
                        """
                        SELECT connect_timeout, auth_timeout, banner_timeout, global_delay_factor
                        FROM device_configs
                        WHERE device_id = $1
                        LIMIT 1
                        """,
                        int(device_id),
                    )
                except Exception:
                    cfg = None
                device_dict = dict(device_row)
                if cfg:
                    device_dict["connect_timeout"] = cfg.get("connect_timeout")
                    device_dict["auth_timeout"] = cfg.get("auth_timeout")
                    device_dict["banner_timeout"] = cfg.get("banner_timeout")
                    device_dict["global_delay_factor"] = cfg.get("global_delay_factor")

                await db.execute(
                    "UPDATE config_push_job_items SET status='running', started_at=$2, error_message=NULL WHERE id=$1 AND status='pending'",
                    int(item_id),
                    _utc_now(),
                )
                await ConfigPushService._emit_event(job_id, {"type": "item_started", "device_id": str(device_id)})
                try:
                    await DeviceChangeLog.create(
                        device_id=int(device_id),
                        change_type="config_push_started",
                        change_description=f"配置下发开始 (job_id={int(job_id)})",
                        changed_by=str(int(creator_id) or ""),
                        old_values=None,
                        new_values={"job_id": int(job_id), "title": str(job_title or "")},
                    )
                except Exception:
                    pass

                ok, err = await asyncio.to_thread(
                    self._execute_device_commands_sync,
                    job_id,
                    str(int(creator_id) or ""),
                    device_dict,
                    commands,
                    stop_flag,
                    loop,
                )

                if not ok:
                    await db.execute(
                        "UPDATE config_push_job_items SET status='failed', error_message=$2, finished_at=$3 WHERE id=$1",
                        int(item_id),
                        str(err or "执行失败"),
                        _utc_now(),
                    )
                    await ConfigPushService._emit_event(job_id, {"type": "item_failed", "device_id": str(device_id), "error": str(err or "")})
                    try:
                        await DeviceChangeLog.create(
                            device_id=int(device_id),
                            change_type="config_push_finished",
                            change_description=f"配置下发失败 (job_id={int(job_id)})",
                            changed_by=str(int(creator_id) or ""),
                            old_values=None,
                            new_values={"job_id": int(job_id), "title": str(job_title or ""), "status": "failed", "error": str(err or "")},
                        )
                    except Exception:
                        pass
                elif stop_flag.is_set():
                    await db.execute(
                        "UPDATE config_push_job_items SET status='canceled', finished_at=$2 WHERE id=$1",
                        int(item_id),
                        _utc_now(),
                    )
                    await ConfigPushService._emit_event(job_id, {"type": "item_canceled", "device_id": str(device_id)})
                    try:
                        await DeviceChangeLog.create(
                            device_id=int(device_id),
                            change_type="config_push_finished",
                            change_description=f"配置下发取消 (job_id={int(job_id)})",
                            changed_by=str(int(creator_id) or ""),
                            old_values=None,
                            new_values={"job_id": int(job_id), "title": str(job_title or ""), "status": "canceled"},
                        )
                    except Exception:
                        pass
                else:
                    await db.execute(
                        "UPDATE config_push_job_items SET status='success', finished_at=$2 WHERE id=$1",
                        int(item_id),
                        _utc_now(),
                    )
                    await ConfigPushService._emit_event(job_id, {"type": "item_success", "device_id": str(device_id)})
                    try:
                        await DeviceChangeLog.create(
                            device_id=int(device_id),
                            change_type="config_push_finished",
                            change_description=f"配置下发成功 (job_id={int(job_id)})",
                            changed_by=str(int(creator_id) or ""),
                            old_values=None,
                            new_values={"job_id": int(job_id), "title": str(job_title or ""), "status": "success"},
                        )
                    except Exception:
                        pass
            finally:
                cancel_task.cancel()
                try:
                    await cancel_task
                except Exception:
                    pass
                expected = self._held_device_locks.get(int(device_id))
                if expected is not None:
                    await self._safe_unlock_device_lock(int(device_id), int(expected), retries=3)
                self._held_device_locks.pop(int(device_id), None)

    async def _watch_cancel(self, job_id: int, stop_flag: threading.Event) -> None:
        redis = redis_manager.get_client()
        while self._running and not stop_flag.is_set():
            try:
                if await redis.get(ConfigPushService.cancel_key(job_id)):
                    stop_flag.set()
                    return
            except Exception:
                pass
            await asyncio.sleep(0.2)

    def _execute_device_commands_sync(
        self,
        job_id: int,
        executed_by: str,
        device: Dict[str, Any],
        commands: List[str],
        stop_flag: threading.Event,
        loop: asyncio.AbstractEventLoop,
    ) -> Tuple[bool, Optional[str]]:
        device_id = int(device.get("id") or 0)
        if not device_id:
            return False, "设备不存在"
        ip = str(device.get("ipv4") or "").strip()
        if not ip:
            return False, "设备缺少 IPv4"
        params = {
            "device_type": _pick_netmiko_device_type(device.get("device_type")),
            "host": ip,
            "username": str(device.get("user_name") or ""),
            "password": str(device.get("password") or ""),
            "port": int(device.get("ssh_port") or 22),
            "timeout": float(device.get("connect_timeout") or 30.0),
            "conn_timeout": float(device.get("connect_timeout") or 30.0),
            "auth_timeout": float(device.get("auth_timeout") or 30.0),
            "banner_timeout": float(device.get("banner_timeout") or 120.0),
            "global_delay_factor": float(device.get("global_delay_factor") or 2.0),
        }

        conn = None
        try:
            conn = ConnectHandler(**params)
            for cmd in commands:
                if stop_flag.is_set():
                    break
                c = str(cmd or "").strip()
                if not c:
                    continue
                try:
                    asyncio.run_coroutine_threadsafe(
                        SshCommandAuditLog.create(
                            device_id=int(device_id),
                            device_ip=str(ip),
                            command=str(c),
                            executed_by=str(executed_by or ""),
                        ),
                        loop,
                    )
                except Exception:
                    pass
                try:
                    out = conn.send_command_timing(c, strip_prompt=False, strip_command=False)
                except Exception as e:
                    fut = asyncio.run_coroutine_threadsafe(
                        ConfigPushService._emit_event(job_id, {"type": "command_error", "device_id": str(device_id), "command": c, "error": str(e)}),
                        loop,
                    )
                    try:
                        fut.result(timeout=5)
                    except Exception:
                        pass
                    return False, str(e)

                fut = asyncio.run_coroutine_threadsafe(
                    ConfigPushService._emit_event(job_id, {"type": "command_output", "device_id": str(device_id), "command": c, "content": str(out or "")}),
                    loop,
                )
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass
            return True, None
        except Exception as e:
            decision = classify_ssh_failure(e)
            raw = ""
            try:
                raw = str(e or "").strip()
            except Exception:
                raw = ""
            if len(raw) > 1200:
                raw = raw[:1197] + "..."
            hint = ""
            if decision.category == "not_ssh":
                hint = "提示：目标端口可能不是 SSH（端口填错/服务未启动/被防火墙拦截）"
            elif decision.category == "unreachable":
                hint = "提示：检查 IP/端口是否可达，以及防火墙/安全组策略"
            elif decision.category == "auth":
                hint = "提示：账号密码错误或不允许该认证方式"
            elif decision.category == "timeout":
                hint = "提示：设备响应慢，可尝试增大 connect_timeout/banner_timeout"

            err_text = raw
            if hint and hint not in err_text:
                err_text = f"{err_text}\n{hint}" if err_text else hint

            fut = asyncio.run_coroutine_threadsafe(
                ConfigPushService._emit_event(job_id, {"type": "device_error", "device_id": str(device_id), "error": err_text}),
                loop,
            )
            try:
                fut.result(timeout=5)
            except Exception:
                pass
            return False, err_text
        finally:
            if conn is not None:
                try:
                    conn.disconnect()
                except Exception:
                    pass
