
import asyncio
import logging
import json
import time
from fastapi import APIRouter, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect, Query
from typing import List, Optional
from pydantic import BaseModel
from app.core.security import verify_token, verify_token_ws, PermissionChecker, user_is_super, user_has_permission
from app.core.redis import redis_manager
from app.core.database import db
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse, DeviceTest, DeviceDelete
from app.services.device_service import device_service
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
async def get_device(response: Response, type: int = 0, user_data: dict = Depends(PermissionChecker(["sys:device:list"]))):
    return await device_service.get_device_list(type)

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
    redis_client = redis_manager.get_client()
    status_data = await redis_client.hgetall(f"device_status:{device_id}")
    if status_data:
        return format_ws_data(status_data)
    return format_ws_data({})

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
            nd.location,
            nd.ssh_port,
            nd.vendor,
            nd.model,
            nd.serial_number,
            nd.created_by,
            nd.is_active,
            nd.created_at,
            u.username AS created_by_name
        FROM network_devices nd
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
    data["vendor"] = str(data.get("vendor") or "")
    data["model"] = str(data.get("model") or "")
    data["serial_number"] = str(data.get("serial_number") or "")
    data["type"] = str(data.get("device_type") or "")

    redis_client = redis_manager.get_client()
    status_data = await redis_client.hgetall(f"device_status:{device_id}")
    data.update(format_ws_data(status_data or {}))
    return data


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
    redis_client = redis_manager.get_client()
    device_id = int(data.device_id)
    ttl = int(data.ttl_seconds or 60)
    if ttl < 5:
        ttl = 5
    if ttl > 600:
        ttl = 600
    payload = {
        "interval": float(data.interval if data.interval is not None else 1),
        "monitor_interval": float(data.monitor_interval if data.monitor_interval is not None else 1),
        "ts": float(time.time()),
    }
    await redis_client.set(f"device:boost:{device_id}", json.dumps(payload, ensure_ascii=False), ex=ttl)
    await redis_client.sadd("device:boost:set", device_id)
    return {"code": 200}

@router.post("/monitor/restore")
async def restore_device_monitor(
    data: MonitorRestoreRequest,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    redis_client = redis_manager.get_client()
    device_id = int(data.device_id)
    await redis_client.delete(f"device:boost:{device_id}")
    await redis_client.srem("device:boost:set", device_id)
    return {"code": 200}

# WebSocket 详情 (重构：使用 app.core.redis)
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

    redis_client = redis_manager.get_client()
    pubsub = redis_client.pubsub()
    
    try:
        channel = f"device_update:{device_id}"
        await pubsub.subscribe(channel)
        
        # 初始数据
        current_data = await redis_client.hgetall(f"device_status:{device_id}")
        if current_data:
             response = format_ws_data(current_data)
             await websocket.send_json(response)

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                current_data = await redis_client.hgetall(f"device_status:{device_id}")
                if current_data:
                    response = format_ws_data(current_data)
                    await websocket.send_json(response)
            await asyncio.sleep(0.1) 
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device {device_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()

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

    try:
        redis_client = redis_manager.get_client()
        pubsub = redis_client.pubsub()
        logger.info("Redis client obtained")
    except Exception as e:
        logger.error(f"Failed to get Redis client: {e}", exc_info=True)
        await websocket.close()
        return
    
    # WebSocket 发送锁
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        async with ws_lock:
            await websocket.send_json(data)

    # Redis 推送任务
    async def redis_listener():
        try:
            logger.info("Starting Redis listener")
            await pubsub.psubscribe("device_update:*")
            logger.info("Subscribed to device_update:*")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'pmessage':
                    try:
                        channel = message['channel']
                        if isinstance(channel, bytes):
                            channel = channel.decode('utf-8')
                            
                        device_id = int(channel.split(':')[-1])
                        
                        redis_key = f"device_status:{device_id}"
                        status_data = await redis_client.hgetall(redis_key)
                        
                        if status_data:
                            status = '离线'
                            if status_data.get('status') == 'online':
                                status = '在线'
                            
                            update_data = {
                                'id': device_id,
                                'status': status,
                                'cpu_usage': f"{float(status_data.get('cpu_usage', 0))}%",
                                'memory_usage': f"{float(status_data.get('memory_usage', 0))}%",
                                'disk_usage': f"{float(status_data.get('disk_usage', 0))}%"
                            }
                            await send_safe_json({"type": "update", "data": update_data})
                    except Exception as e:
                        logger.error(f"Redis Update Error: {e}", exc_info=True)
                
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Redis Listener Error: {e}", exc_info=True)

    # 启动 Redis 监听
    listener_task = asyncio.create_task(redis_listener())
    
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
        await pubsub.close()

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

def format_ws_data(status_data: dict) -> dict:
    status = 'offline'
    if status_data.get('status') == 'online':
        status = 'online'
    elif status_data.get('online_status'):
        status = 'online'
        
    return {
        'status': status,
        'cpuUsage': float(status_data.get('cpu_usage', 0)),
        'memoryUsage': float(status_data.get('memory_usage', 0)),
        'diskUsage': float(status_data.get('disk_usage', 0)),
        'uptime': status_data.get('uptime', '未知'),
        'lastConnect': status_data.get('last_updated', ''),
        'osVersion': status_data.get('os_version', status_data.get('kernel', 'Unknown')),
    }
