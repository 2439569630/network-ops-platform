
import asyncio
import logging
import json
import time
from fastapi import APIRouter, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect, Query
from typing import List, Optional
from pydantic import BaseModel
from app.core.security import verify_token, verify_token_ws, PermissionChecker, user_is_super, user_has_permission
from app.core.database import db
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse, DeviceTest, DeviceDelete, DeviceConfigUpdate
from app.services.device_service import device_service
from app.workers.monitor.manager import MonitorManager
from app.core.redis import redis_manager
from netmiko import ConnectHandler

router = APIRouter()
ssh_router = APIRouter()
logger = logging.getLogger(__name__)

class MonitorBoostRequest(BaseModel):
    device_id: int
    ttl_seconds: int = 60
    interval: Optional[float] = None
    monitor_interval: Optional[float] = None

class MonitorRestoreRequest(BaseModel):
    device_id: int

class DeviceRecycleActionRequest(BaseModel):
    device_id: int

class DeviceUpdateRequest(BaseModel):
    device_id: int
    device_name: Optional[str] = None
    type: Optional[str] = None
    location: Optional[str] = None
    ssh_port: Optional[int] = None

# 获取设备列表
@router.get("/get", response_model=List[DeviceResponse])
async def get_device(
    response: Response, 
    type: int = 0, 
    search: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    location_node_id: Optional[int] = Query(None),
    user_data: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    return await device_service.get_device_list(type, search_query=search, location_filter=location, location_node_id=location_node_id)

# 添加设备
@router.post("/add")
async def add_device(device: DeviceCreate, user_data: dict = Depends(PermissionChecker(["sys:device:add"]))):
    try:
        user_id = user_data.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="无法获取用户信息")
            
        await device_service.add_device(device, user_id)
        return {"message": "设备添加成功", "code": 200}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"添加设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 删除设备
@router.post("/delete")
async def delete_device(data: DeviceDelete, user_data: dict = Depends(PermissionChecker(["sys:device:del"]))):
    try:
        deleted_by = str(user_data.get("id") or "")
        await device_service.delete_device(data.id, data.ip, deleted_by=deleted_by)
        return {"message": "设备已移入回收站", "code": 200}
    except ValueError as e:
         raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recycle/list")
async def list_recycled_devices(
    user_data: dict = Depends(PermissionChecker(["sys:device:del"])),
):
    return {"code": 200, "data": await device_service.get_deleted_devices()}

@router.post("/recycle/restore")
async def restore_recycled_device(
    data: DeviceRecycleActionRequest,
    user_data: dict = Depends(PermissionChecker(["sys:device:del"])),
):
    await device_service.restore_device(int(data.device_id), restored_by=str(user_data.get("id") or ""))
    return {"code": 200}

@router.post("/recycle/purge")
async def purge_recycled_device(
    data: DeviceRecycleActionRequest,
    user_data: dict = Depends(PermissionChecker(["sys:device:del"])),
):
    await device_service.purge_device(int(data.device_id))
    return {"code": 200}

@router.post("/update")
async def update_device(
    data: DeviceUpdateRequest,
    user_data: dict = Depends(PermissionChecker(["sys:device:edit"])),
):
    patch = DeviceUpdate(
        device_name=data.device_name,
        type=data.type,
        location=data.location,
        ssh_port=data.ssh_port,
    )
    await device_service.update_device(int(data.device_id), patch, updated_by=str(user_data.get("id") or ""))
    return {"code": 200}

# 测试连接
@router.post("/test_connect")
async def test_connect(device: DeviceTest, user_data: dict = Depends(PermissionChecker(["sys:device:add", "sys:device:edit"]))):
    try:
        await device_service.test_connect(device)
        return {"message": "连接测试成功", "code": 200}
    except Exception as e:
        logger.error(f"连接测试失败: {e}")
        return {"message": f"连接失败: {str(e)}", "code": 500}

@router.get("/status/{device_id}")
async def get_device_status(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    monitor = MonitorManager()
    snap = await monitor.get_runtime_snapshot_async(int(device_id))
    return format_ws_data(_snapshot_to_status_data(snap))

@router.get("/detail/{device_id}")
async def get_device_detail(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    sql = """
        SELECT
            nd.id,
            nd.device_name,
            nd.ipv4,
            nd.ipv6,
            nd.mac,
            nd.device_type,
            COALESCE(ln.name, '') AS location,
            lnd.node_id AS location_node_id,
            nd.ssh_port,
            nd.vendor,
            nd.model,
            nd.serial_number,
            nd.created_by,
            nd.is_active,
            nd.created_at,
            u.username AS created_by_name
        FROM network_devices nd
        LEFT JOIN location_node_devices lnd ON lnd.device_id = nd.id
        LEFT JOIN location_nodes ln ON ln.id = lnd.node_id
        LEFT JOIN users u ON u.id::text = nd.created_by
        WHERE nd.id = $1
          AND COALESCE(nd.is_active, true) = true
    """
    if await device_service.has_deleted_at():
        sql += " AND nd.deleted_at IS NULL"
    row = await db.fetch_one(sql, int(device_id))
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")

    data = dict(row)
    data["created_by"] = str(data.get("created_by") or "")
    data["created_by_name"] = str(data.get("created_by_name") or "未知")
    data["ops_admin_name"] = str(data.get("created_by_name") or "未知")
    data["ipv4"] = str(data.get("ipv4") or "")
    data["ipv6"] = str(data.get("ipv6") or "")
    data["mac"] = str(data.get("mac") or "")
    data["ssh_port"] = int(data.get("ssh_port") or 22)
    data["location"] = str(data.get("location") or "")
    if "location_node_id" in data and data.get("location_node_id") is not None:
        try:
            data["location_node_id"] = int(data.get("location_node_id"))
        except Exception:
            data["location_node_id"] = None
    data["vendor"] = str(data.get("vendor") or "")
    data["model"] = str(data.get("model") or "")
    data["serial_number"] = str(data.get("serial_number") or "")
    data["type"] = str(data.get("device_type") or "")

    monitor = MonitorManager()
    snap = await monitor.get_runtime_snapshot_async(int(device_id))
    data.update(format_ws_data(_snapshot_to_status_data(snap)))
    return data


@router.get("/config/{device_id}")
async def get_device_config(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    data = await device_service.get_device_config(int(device_id))
    return {"code": 200, "data": data}


@router.post("/config/update")
async def update_device_config(
    payload: DeviceConfigUpdate,
    user: dict = Depends(PermissionChecker(["sys:device:edit"])),
):
    updated = await device_service.update_device_config(int(payload.device_id), payload.model_dump(exclude_unset=True))
    monitor = MonitorManager()
    try:
        await monitor.refresh_device_config(int(payload.device_id))
    except Exception:
        pass
    return {"code": 200, "data": updated}


@router.get("/audit/logs/{device_id}")
async def get_device_audit_logs(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(PermissionChecker(["sys:device:audit"])),
):
    result = await device_service.get_device_change_logs(int(device_id), page=int(page), page_size=int(page_size))
    return {"code": 200, "data": result}

@router.get("/audit/ssh-commands/{device_id}")
async def get_device_ssh_command_audit_logs(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(PermissionChecker(["sys:device:audit"])),
):
    result = await device_service.get_ssh_command_audit_logs(int(device_id), page=int(page), page_size=int(page_size))
    return {"code": 200, "data": result}

@router.post("/monitor/boost")
async def boost_device_monitor(
    data: MonitorBoostRequest,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    monitor = MonitorManager()
    await monitor.boost_device(
        device_id=int(data.device_id),
        ttl_seconds=int(data.ttl_seconds or 60),
        interval=data.interval,
        monitor_interval=data.monitor_interval,
    )
    return {"code": 200}

@router.post("/monitor/restore")
async def restore_device_monitor(
    data: MonitorRestoreRequest,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    monitor = MonitorManager()
    await monitor.restore_boost(int(data.device_id))
    return {"code": 200}

@router.post("/monitor/sync/{device_id}")
async def sync_device_monitor(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    monitor = MonitorManager()
    snap = await monitor.sync_device_snapshot(int(device_id))
    return {"code": 200, "data": snap}

@router.websocket("/ws/detail/{device_id}")
async def websocket_device_detail(websocket: WebSocket, device_id: int):
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
    if not user_is_super(user):
        allowed = await user_has_permission(user, "sys:device:list")
        if not allowed:
            allowed = await user_has_permission(user, "sys:dashboard:view")
        if not allowed:
            await websocket.close(code=4003, reason="权限不足")
            return

    monitor = MonitorManager()
    q = monitor.subscribe_detail(int(device_id))

    async def redis_listener():
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return
        pubsub = redis_client.pubsub()
        channel = f"ws:devices:detail:{int(device_id)}"
        try:
            await pubsub.subscribe(channel)
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    raw = msg.get("data")
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8", errors="ignore")
                    if isinstance(raw, str):
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            payload = None
                    else:
                        payload = raw
                    if isinstance(payload, dict):
                        await websocket.send_json(format_ws_data(_snapshot_to_status_data(payload)))
                await asyncio.sleep(0.01)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass

    redis_task = asyncio.create_task(redis_listener()) if not monitor.running else None

    try:
        snap = await monitor.sync_device_snapshot(int(device_id))
        await websocket.send_json(format_ws_data(_snapshot_to_status_data(snap)))
        while True:
            payload = await q.get()
            await websocket.send_json(format_ws_data(_snapshot_to_status_data(payload)))
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device {device_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass
    finally:
        monitor.unsubscribe_detail(int(device_id), q)
        if redis_task:
            redis_task.cancel()

@router.websocket("/ws/list")
async def websocket_device_list(websocket: WebSocket):
    """
    WebSocket 设备列表实时更新 (双向通信)
    """
    logger.info("New WebSocket connection request to /ws/list")
    await websocket.accept()
    logger.info("WebSocket accepted")
    
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        logger.warning("WebSocket authentication failed")
        return
    if not user_is_super(user):
        if not await user_has_permission(user, "sys:device:list"):
            await websocket.close(code=4003, reason="权限不足")
            return
    logger.info(f"WebSocket authenticated for user: {user.get('id')}")
    
    # WebSocket 发送锁
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        async with ws_lock:
            await websocket.send_json(data)

    monitor = MonitorManager()
    q = monitor.subscribe_list()

    async def monitor_listener():
        try:
            while True:
                payload = await q.get()
                await send_safe_json({"type": "update", "data": payload})
        except WebSocketDisconnect:
            raise
        except Exception:
            pass

    listener_task = asyncio.create_task(monitor_listener())

    async def redis_listener():
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return
        pubsub = redis_client.pubsub()
        channel = "ws:devices:list"
        try:
            await pubsub.subscribe(channel)
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    raw = msg.get("data")
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8", errors="ignore")
                    if isinstance(raw, str):
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            payload = None
                    else:
                        payload = raw
                    if isinstance(payload, dict):
                        await send_safe_json(payload)
                await asyncio.sleep(0.01)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass

    redis_task = asyncio.create_task(redis_listener()) if not monitor.running else None
    
    try:
        logger.info("Entering WS main loop")
        while True:
            # 接收前端指令
            logger.info("Waiting for WS message...")
            data = await websocket.receive_json()
            logger.info(f"Received WS message: {data}")
            command = data.get("command")
            
            if command == "get_list":
                req_type = int(data.get("type", 0))
                search_kw = data.get("search", "")
                logger.info(f"WS Command: get_list type={req_type}, search='{search_kw}'")
                try:
                    # 获取列表并发送
                    initial_data = await device_service.get_device_list(req_type, search_kw)
                    logger.info(f"Got device list data, len: {len(initial_data)}")
                    await send_safe_json({"type": "list", "data": initial_data})
                    logger.info("Sent list data to WS")
                except Exception as e:
                    logger.error(f"Error processing get_list: {e}", exc_info=True)
                
            elif command == "ping":
                await send_safe_json({"type": "pong"})
                
    except WebSocketDisconnect:
        logger.info("WS Disconnected")
    except Exception as e:
        logger.error(f"WS Main Loop Error: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up WS resources")
        listener_task.cancel()
        if redis_task:
            redis_task.cancel()
        monitor.unsubscribe_list(q)

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

@ssh_router.websocket("/ws/ssh/{ip}")
async def ssh_websocket(websocket: WebSocket, ip: str):
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
    user_id = str(user.get("id") or "")

    if not user_is_super(user):
        if not await user_has_permission(user, "sys:ssh:connect"):
            try:
                await websocket.send_text("系统: 权限不足\r\n")
            except Exception:
                pass
            await websocket.close(code=4003, reason="权限不足")
            return

    row = await db.fetch_one(
        """
        SELECT id, user_name, password, ssh_port, device_type
        FROM network_devices
        WHERE ipv4 = $1
        LIMIT 1
        """,
        str(ip),
    )

    if not row:
        await websocket.send_text(f"系统: 未找到设备 {ip}，请先在设备管理录入\r\n")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    username = str(row.get("user_name") or "").strip()
    password = str(row.get("password") or "").strip()
    device_id = int(row.get("id") or 0)
    if not username or not password:
        await websocket.send_text(f"系统: 设备 {ip} 未配置 SSH 账号或密码\r\n")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    try:
        port = int((row.get("ssh_port") if row else None) or 22)
    except Exception:
        port = 22
    device_type = _pick_netmiko_device_type((row.get("device_type") if row else None))

    await websocket.send_text(f"系统: 正在连接 {ip}...\r\n")

    device_params = {
        "device_type": device_type,
        "host": str(ip),
        "username": username,
        "password": password,
        "port": int(port),
        "timeout": 30,
        "auth_timeout": 30,
        "banner_timeout": 100,
        "global_delay_factor": 2,
        "allow_agent": False,
        "use_keys": False,
    }

    connected_ok = False
    try:
        last_err: Exception | None = None
        conn = None
        for _ in range(3):
            try:
                conn = await asyncio.to_thread(ConnectHandler, **device_params)
                break
            except Exception as e:
                last_err = e
                await asyncio.sleep(1)
        if conn is None:
            raise last_err or Exception("连接失败")
    except Exception as e:
        msg = str(e).splitlines()[0] if str(e) else "连接失败"
        try:
            if device_id:
                await device_service.log_device_action(
                    device_id=int(device_id),
                    action="ssh_connect_failed",
                    description=f"SSH连接失败: {msg}",
                    changed_by=user_id,
                    payload={"ipv4": str(ip), "ssh_port": int(port), "device_type": str(device_type)},
                )
        except Exception:
            pass
        await websocket.send_text(f"系统: 连接失败: {msg}\r\n")
        try:
            await websocket.close()
        except Exception:
            pass
        return
    try:
        if device_id:
            await device_service.log_device_action(
                device_id=int(device_id),
                action="ssh_connect",
                description=f"SSH连接 {ip}",
                changed_by=user_id,
                payload={"ipv4": str(ip), "ssh_port": int(port), "device_type": str(device_type)},
            )
    except Exception:
        pass
    connected_ok = True

    async def close_conn():
        try:
            await asyncio.to_thread(conn.disconnect)
        except Exception:
            pass

    try:
        try:
            try:
                await asyncio.to_thread(conn.write_channel, "\n")
            except Exception:
                pass
            initial = await asyncio.to_thread(conn.read_channel)
            if initial:
                await websocket.send_text(str(initial))
        except Exception:
            pass

        async def ws_to_ssh():
            while True:
                data = await websocket.receive_text()
                try:
                    if device_id:
                        await device_service.log_ssh_command(
                            device_id=int(device_id),
                            device_ip=str(ip),
                            command=str(data),
                            executed_by=str(user.get("id") or ""),
                        )
                except Exception:
                    pass
                await asyncio.to_thread(conn.write_channel, f"{data}\n")

        async def ssh_to_ws():
            while True:
                out = await asyncio.to_thread(conn.read_channel)
                if out:
                    await websocket.send_text(str(out))
                await asyncio.sleep(0.05)

        t1 = asyncio.create_task(ws_to_ssh())
        t2 = asyncio.create_task(ssh_to_ws())
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        msg = str(e).splitlines()[0] if str(e) else "连接异常"
        try:
            await websocket.send_text(f"\r\n系统: 连接异常: {msg}\r\n")
        except Exception:
            pass
    finally:
        await close_conn()
        try:
            if connected_ok and device_id:
                await device_service.log_device_action(
                    device_id=int(device_id),
                    action="ssh_disconnect",
                    description=f"SSH断开 {ip}",
                    changed_by=user_id,
                    payload={"ipv4": str(ip), "ssh_port": int(port), "device_type": str(device_type)},
                )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

def _parse_usage(value) -> float:
    try:
        s = str(value or "").strip()
        if not s:
            return 0.0
        if s.endswith("%"):
            s = s[:-1].strip()
        return float(s)
    except Exception:
        return 0.0

def _snapshot_to_status_data(snapshot: dict) -> dict:
    fsm_state = str(snapshot.get("fsm_state") or "").strip()
    return {
        "status": fsm_state,
        "online_status": fsm_state in {"online", "recovering", "degraded", "checking", "collecting"},
        "fsm_state": fsm_state,
        "fsm_reason": str(snapshot.get("fsm_reason") or ""),
        "fsm_updated": str(snapshot.get("fsm_updated") or ""),
        "state_phase": str(snapshot.get("state_phase") or ""),
        "state_reason": str(snapshot.get("state_reason") or ""),
        "state_updated": str(snapshot.get("state_updated") or ""),
        "cpu_usage": snapshot.get("cpu_usage", 0),
        "memory_usage": snapshot.get("memory_usage", 0),
        "disk_usage": snapshot.get("disk_usage", 0),
        "uptime": str(snapshot.get("uptime") or ""),
        "last_updated": str(snapshot.get("last_updated") or ""),
    }

def format_ws_data(status_data: dict) -> dict:
    raw_status = status_data.get('status')
    status = 'offline'
    if raw_status in {'online', 'recovering', 'degraded', 'checking', 'collecting'}:
        status = 'online'
    elif status_data.get('online_status'):
        status = 'online'
        
    return {
        'status': status,
        'rawStatus': raw_status or '',
        'fsmState': status_data.get('fsm_state', ''),
        'fsmReason': status_data.get('fsm_reason', status_data.get('offline_reason', '')),
        'fsmUpdated': status_data.get('fsm_updated', ''),
        'statePhase': status_data.get('state_phase', ''),
        'stateReason': status_data.get('state_reason', ''),
        'stateUpdated': status_data.get('state_updated', ''),
        'phase': status_data.get('phase', ''),
        'cpuUsage': _parse_usage(status_data.get('cpu_usage', 0)),
        'memoryUsage': _parse_usage(status_data.get('memory_usage', 0)),
        'diskUsage': _parse_usage(status_data.get('disk_usage', 0)),
        'uptime': status_data.get('uptime', '未知'),
        'lastConnect': status_data.get('last_updated', ''),
        'osVersion': status_data.get('os_version', status_data.get('kernel', 'Unknown')),
    }
