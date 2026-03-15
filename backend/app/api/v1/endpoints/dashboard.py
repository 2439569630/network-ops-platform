import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import get_or_init_user_auth_version, user_has_permission, user_is_super, verify_token_ws
from app.services.device_service import device_service
from app.services.notification_service import NotificationService
from app.utils.device_status import status_fields_from_snapshot
from app.workers.monitor.manager import MonitorManager

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_usage(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return 0.0
        if s.endswith("%"):
            s = s[:-1].strip()
        return float(s)
    except Exception:
        return 0.0


async def _get_active_devices_brief() -> List[Dict[str, Any]]:
    sql = """
        SELECT id, device_name
        FROM network_devices
        WHERE COALESCE(is_active, TRUE) = TRUE
    """
    if await device_service.has_deleted_at():
        sql += " AND deleted_at IS NULL"
    try:
        rows = await db.fetch_all(sql)
    except Exception:
        rows = []
    return [dict(r) for r in (rows or []) if r]


async def _build_overview() -> Dict[str, Any]:
    devices = await _get_active_devices_brief()
    monitor = MonitorManager()

    total = 0
    online = 0
    offline = 0
    stale = 0
    by_display_status: Dict[str, int] = {}
    by_fsm_state: Dict[str, int] = {}
    top_usage: List[Dict[str, Any]] = []

    sem = asyncio.Semaphore(50)

    async def fetch_one(item: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        did = int(item.get("id") or 0)
        async with sem:
            snap = await monitor.get_runtime_snapshot_async(did)
        return item, snap if isinstance(snap, dict) else {}

    pairs = await asyncio.gather(*[fetch_one(d) for d in devices], return_exceptions=True)
    for pair in pairs:
        if isinstance(pair, Exception):
            continue
        item, snap = pair
        did = int(item.get("id") or 0)
        if did <= 0:
            continue
        name = str(item.get("device_name") or "")

        total += 1
        base = status_fields_from_snapshot(snap)
        display_status = str(base.get("display_status") or "").strip() or "未知"
        fsm_state = str(base.get("fsm_state") or "").strip() or "init"
        online_status = bool(base.get("online_status"))
        is_stale = bool(snap.get("stale"))

        if online_status:
            online += 1
        else:
            offline += 1
        if is_stale:
            stale += 1

        by_display_status[display_status] = int(by_display_status.get(display_status, 0)) + 1
        by_fsm_state[fsm_state] = int(by_fsm_state.get(fsm_state, 0)) + 1

        cpu = _parse_usage(snap.get("cpu_usage"))
        mem = _parse_usage(snap.get("memory_usage"))
        top_usage.append(
            {
                "device_id": did,
                "device_name": name,
                "cpu_usage": cpu,
                "memory_usage": mem,
            }
        )

    top_usage_sorted = sorted(top_usage, key=lambda x: float(x.get("cpu_usage") or 0.0), reverse=True)[:10]

    return {
        "generated_at": float(time.time()),
        "devices": {
            "total": int(total),
            "online": int(online),
            "offline": int(offline),
            "stale": int(stale),
            "by_display_status": by_display_status,
            "by_fsm_state": by_fsm_state,
        },
        "top_usage": top_usage_sorted,
    }


async def _get_monitor_health() -> Dict[str, Any]:
    now = float(time.time())
    key = str(getattr(MonitorManager, "_LEADER_HEARTBEAT_KEY", "monitor:leader:heartbeat"))
    ttl = float(getattr(MonitorManager, "_LEADER_LOCK_TTL_SECONDS", 90) or 90)

    try:
        redis_client = redis_manager.get_client()
    except Exception:
        redis_client = None

    raw = None
    if redis_client is not None:
        try:
            raw = await redis_client.get(key)
        except Exception:
            raw = None

    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")

    payload: Optional[dict] = None
    if raw:
        try:
            payload = json.loads(raw)
        except Exception:
            payload = None

    ts = float(payload.get("ts") or 0.0) if isinstance(payload, dict) else 0.0
    pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    age = max(0.0, now - ts) if ts > 0 else float("inf")
    alive = bool(ts > 0 and age <= max(ttl, 1.0))

    return {
        "alive": alive,
        "heartbeat_age_seconds": (age if age != float("inf") else None),
        "pid": (pid if pid > 0 else None),
        "ts": (ts if ts > 0 else None),
    }


async def _get_alert_statistics() -> Dict[str, Any]:
    end_dt = datetime.now()
    start_dt = (end_dt - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_exclusive = (end_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_map: Dict[str, Dict[str, int]] = {}
    x_axis_data: List[str] = []

    for i in range(7):
        current_date = start_dt + timedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        date_map[date_str] = {"critical": 0, "warning": 0, "info": 0}
        x_axis_data.append(week_days[current_date.weekday()])

    try:
        rows = await db.fetch_all(
            """
            SELECT to_char(triggered_at::date, 'YYYY-MM-DD') AS day, severity, COUNT(*)::int AS cnt
            FROM device_alert_logs
            WHERE triggered_at >= $1 AND triggered_at < $2
            GROUP BY day, severity
            """,
            start_dt,
            end_exclusive,
        )
    except Exception:
        rows = []

    for r in rows or []:
        day = str(r.get("day") or "")
        sev = str(r.get("severity") or "")
        cnt = int(r.get("cnt") or 0)
        if day in date_map and sev in date_map[day]:
            date_map[day][sev] += cnt

    series_critical: List[int] = []
    series_warning: List[int] = []
    series_info: List[int] = []
    for date_str in sorted(date_map.keys()):
        counts = date_map[date_str]
        series_critical.append(int(counts.get("critical", 0)))
        series_warning.append(int(counts.get("warning", 0)))
        series_info.append(int(counts.get("info", 0)))

    return {
        "xAxis": x_axis_data,
        "series": [
            {"name": "严重", "data": series_critical},
            {"name": "警告", "data": series_warning},
            {"name": "提醒", "data": series_info},
        ],
    }


def _period_range(period: str) -> Tuple[datetime, datetime]:
    p = str(period or "").strip().lower()
    now = datetime.now()
    if p in ("today", "day", "0"):
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_exclusive = (start_dt + timedelta(days=1))
        return start_dt, end_exclusive
    if p in ("month", "30", "30d"):
        start_dt = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_exclusive = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start_dt, end_exclusive
    start_dt = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_exclusive = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start_dt, end_exclusive


async def _get_alert_level_distribution(period: str) -> Dict[str, Any]:
    start_dt, end_exclusive = _period_range(period)
    try:
        rows = await db.fetch_all(
            """
            SELECT severity, COUNT(*)::int AS cnt
            FROM device_alert_logs
            WHERE triggered_at >= $1 AND triggered_at < $2
            GROUP BY severity
            """,
            start_dt,
            end_exclusive,
        )
    except Exception:
        rows = []

    counts = {"critical": 0, "warning": 0, "info": 0}
    for r in rows or []:
        sev = str(r.get("severity") or "").strip()
        cnt = int(r.get("cnt") or 0)
        if sev in counts:
            counts[sev] += cnt

    return {
        "period": str(period or "week"),
        "xAxis": ["严重", "警告", "提醒"],
        "series": [
            {
                "name": "告警数量",
                "data": [int(counts["critical"]), int(counts["warning"]), int(counts["info"])],
            }
        ],
    }


async def _get_recent_system_alerts(*, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        redis_client = redis_manager.get_client()
    except Exception:
        return []

    try:
        rows = await redis_client.lrange(NotificationService.SYSTEM_ALERTS_RECENT_KEY, 0, max(int(limit) - 1, 0))
    except Exception:
        rows = []

    out: List[Dict[str, Any]] = []
    for raw in rows or []:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            obj = json.loads(raw) if raw else None
        except Exception:
            obj = None
        if isinstance(obj, dict):
            out.append(obj)
    return out


async def _auth_guard(*, websocket: WebSocket, user: dict) -> None:
    uid = user.get("id")
    if uid is None:
        return
    try:
        uid = int(uid)
    except Exception:
        return

    token_auth_ver = user.get("auth_ver")
    try:
        token_auth_ver = int(token_auth_ver) if token_auth_ver is not None else None
    except Exception:
        token_auth_ver = None
    if token_auth_ver is None:
        return

    while True:
        try:
            if websocket.client_state != WebSocketState.CONNECTED:
                return
        except Exception:
            return

        await asyncio.sleep(2.0)

        current_ver = await get_or_init_user_auth_version(int(uid))
        if int(current_ver) != int(token_auth_ver):
            try:
                await websocket.close(code=4001, reason="会话已失效")
            except Exception:
                pass
            return


@router.websocket("/ws/overview")
async def websocket_dashboard_overview(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return

    if not await user_has_permission(user, "sys:dashboard:view"):
        await websocket.close(code=4003, reason="权限不足")
        return

    ws_lock = asyncio.Lock()
    force_refresh = asyncio.Event()
    alert_period = {"value": "week"}

    async def safe_send(payload: Dict[str, Any]) -> None:
        async with ws_lock:
            try:
                await websocket.send_json(payload)
            except Exception:
                try:
                    await websocket.close()
                except Exception:
                    pass

    guard_task = asyncio.create_task(_auth_guard(websocket=websocket, user=user))

    client_task: Optional[asyncio.Task] = None
    stats_task: Optional[asyncio.Task] = None
    overview_task: Optional[asyncio.Task] = None
    pubsub_task: Optional[asyncio.Task] = None

    try:
        redis_client = redis_manager.get_pubsub_client()
    except Exception:
        guard_task.cancel()
        await websocket.close(code=1011, reason="Redis不可用")
        return

    pubsub = redis_client.pubsub()

    async def client_loop() -> None:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                return
            except Exception:
                return
            try:
                msg = json.loads(raw) if raw else None
            except Exception:
                msg = None
            if not isinstance(msg, dict):
                continue
            if str(msg.get("type") or "").strip() == "refresh":
                force_refresh.set()
                continue
            if str(msg.get("type") or "").strip() == "set_alert_period":
                p = str(msg.get("period") or "").strip().lower()
                if p in ("today", "week", "month"):
                    alert_period["value"] = p
                    force_refresh.set()

    async def publish_loop() -> None:
        try:
            await pubsub.subscribe(NotificationService.SYSTEM_ALERTS_CHANNEL)
        except Exception:
            return
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            try:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            except Exception:
                msg = None
            if msg and msg.get("type") == "message":
                raw = msg.get("data")
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    payload = json.loads(raw) if raw else None
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    await safe_send({"type": "alert", "data": payload})
            await asyncio.sleep(0.01)

    async def overview_loop() -> None:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            try:
                await asyncio.wait_for(force_refresh.wait(), timeout=10.0)
                force_refresh.clear()
            except asyncio.TimeoutError:
                pass
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            overview = await _build_overview()
            monitor_health = await _get_monitor_health()
            await safe_send({"type": "overview", "data": overview})
            await safe_send({"type": "monitor_health", "data": monitor_health})

    async def stats_loop() -> None:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            try:
                await asyncio.wait_for(force_refresh.wait(), timeout=60.0)
                force_refresh.clear()
            except asyncio.TimeoutError:
                pass
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            dist = await _get_alert_level_distribution(alert_period["value"])
            await safe_send({"type": "alert_level_dist", "data": dist})

    try:
        init_payload = {
            "overview": await _build_overview(),
            "monitor_health": await _get_monitor_health(),
            "alert_level_dist": await _get_alert_level_distribution(alert_period["value"]),
            "alerts_recent": await _get_recent_system_alerts(limit=50),
        }
        await safe_send({"type": "init", "data": init_payload})

        client_task = asyncio.create_task(client_loop())
        pubsub_task = asyncio.create_task(publish_loop())
        overview_task = asyncio.create_task(overview_loop())
        stats_task = asyncio.create_task(stats_loop())

        done, pending = await asyncio.wait(
            {client_task, pubsub_task, overview_task, stats_task, guard_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in done:
            try:
                _ = t.exception()
            except Exception:
                pass
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        return
    finally:
        for t in (client_task, pubsub_task, overview_task, stats_task, guard_task):
            if t:
                try:
                    t.cancel()
                except Exception:
                    pass
        try:
            await pubsub.unsubscribe(NotificationService.SYSTEM_ALERTS_CHANNEL)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
