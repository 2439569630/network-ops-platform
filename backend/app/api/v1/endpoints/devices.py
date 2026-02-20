# -*- coding: utf-8 -*-
#
# 设备管理 API 接口
#
# 此模块负责处理所有与网络设备相关的操作，包括：
# 1. 设备增删改查 (CRUD)
# 2. 设备状态监控 (通过 WebSocket 实时推送)
# 3. 设备配置管理 (获取/更新配置)
# 4. SSH 远程连接 (通过 WebSocket 代理)
# 5. 资源同步 (接口/路由/VLAN)
#

import asyncio
import logging
import json
import time
from fastapi import APIRouter, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from typing import Any, List, Optional
from pydantic import BaseModel
from app.core.security import verify_token, verify_token_ws, PermissionChecker, user_is_super, user_has_permission, get_or_init_user_auth_version
from app.core.database import db
from app.constants.user import DELETED_USER_DISPLAY_NAME
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse, DeviceTest, DeviceDelete, DeviceConfigUpdate
from app.services.device_service import device_service
from app.workers.monitor.manager import MonitorManager
from app.core.redis import redis_manager
from app.drivers.ssh_retry import classify_ssh_failure
from app.utils.device_status import status_fields_from_snapshot
from netmiko import ConnectHandler
from app.services.network_resource_service import network_resource_service

# 主设备管理路由
router = APIRouter()
# SSH 专用路由 (为了避免前缀冲突或逻辑分离)
ssh_router = APIRouter()
logger = logging.getLogger(__name__)


async def _ws_auth_guard(websocket: WebSocket, user: dict):
    """
    WebSocket 连接守护协程。
    
    用于定期检查用户会话是否失效（例如被强制登出、修改密码）。
    WebSocket 是长连接，无法像 HTTP 请求那样每次都通过 Middleware 检查 Token 有效性。
    因此需要启动一个后台任务，定期轮询用户的 auth_ver (认证版本号)。
    如果发现版本号变更，说明用户已在其他地方登录或被强制下线，需主动关闭 WebSocket。
    
    Args:
        websocket: WebSocket 连接对象
        user: 当前用户信息
    """
    uid = user.get("id")
    if uid is None:
        return
    try:
        uid = int(uid)
    except Exception:
        return
    
    # 获取连接时的认证版本号
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
        
        # 每 2 秒检查一次
        await asyncio.sleep(2.0)
        
        # 获取当前最新的认证版本号
        current_ver = await get_or_init_user_auth_version(int(uid))
        if int(current_ver) != int(token_auth_ver):
            try:
                # 版本号不一致，关闭连接 (Code 4001: 会话失效)
                await websocket.close(code=4001, reason="会话已失效")
            except Exception:
                pass
            return


class DeviceRecycleActionRequest(BaseModel):
    """设备回收站操作请求参数"""
    device_id: int


class DeviceUpdateRequest(BaseModel):
    """设备更新请求参数"""
    device_id: int
    device_name: Optional[str] = None
    type: Optional[str] = None
    location: Optional[str] = None
    ssh_port: Optional[int] = None


# --- 设备基本管理接口 ---

@router.get("/get", response_model=List[DeviceResponse])
async def get_device(
    response: Response, 
    type: int = 0, 
    search: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    location_node_id: Optional[int] = Query(None),
    user_data: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    """
    获取设备列表。
    
    支持多种过滤条件：类型、搜索关键字、位置名称、位置节点ID。
    
    Args:
        type: 设备类型过滤 (0表示全部，具体定义参考 frontend/enums)
        search: 搜索关键字 (匹配名称或IP)
        location: 位置名称过滤
        location_node_id: 位置节点ID过滤 (递归查询该节点下的所有设备)
        
    Returns:
        List[DeviceResponse]: 设备列表
    """
    return await device_service.get_device_list(type, search_query=search, location_filter=location, location_node_id=location_node_id)


@router.post("/add")
async def add_device(device: DeviceCreate, user_data: dict = Depends(PermissionChecker(["sys:device:add"]))):
    """
    添加新设备。
    
    Args:
        device: 设备创建信息 (IP, 端口, 账号密码等)
        user_data: 当前操作用户
        
    Returns:
        dict: 包含新设备ID
    """
    try:
        user_id = user_data.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="无法获取用户信息")
            
        device_id = await device_service.add_device(device, user_id)
        return {"message": "设备添加成功", "code": 200, "data": {"device_id": int(device_id)}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"添加设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_device(data: DeviceDelete, user_data: dict = Depends(PermissionChecker(["sys:device:del"]))):
    """
    删除设备（移入回收站）。
    
    注意：此操作是软删除，设备会被标记为已删除并移入回收站。
    不会立即从数据库物理删除。
    
    Args:
        data: 删除请求参数 (ID, IP)
    """
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
    """
    获取回收站中的设备列表。
    
    普通用户只能看到自己删除的设备，超级管理员可以看到所有。
    """
    is_super = user_is_super(user_data)
    user_id = user_data.get("id")
    # 注意: get_deleted_devices 是 DeviceService 的实例方法，需要通过 device_service 实例调用
    # 并且需要确保 user_id 类型正确（int）
    return {"code": 200, "data": await device_service.get_deleted_devices(user_id=int(user_id) if user_id else None, is_super=is_super)}


@router.post("/recycle/restore")
async def restore_recycled_device(
    data: DeviceRecycleActionRequest,
    user_data: dict = Depends(PermissionChecker(["sys:device:del"])),
):
    """
    恢复回收站中的设备。
    
    将设备从回收站还原到正常列表。
    """
    await device_service.restore_device(int(data.device_id), restored_by=str(user_data.get("id") or ""))
    return {"code": 200}


@router.post("/recycle/purge")
async def purge_recycled_device(
    data: DeviceRecycleActionRequest,
    user_data: dict = Depends(PermissionChecker(["sys:device:del"])),
):
    """
    彻底删除回收站中的设备。
    
    此操作不可逆，将从数据库中物理删除设备记录。
    """
    await device_service.purge_device(int(data.device_id))
    return {"code": 200}


@router.post("/update")
async def update_device(
    data: DeviceUpdateRequest,
    user_data: dict = Depends(PermissionChecker(["sys:device:edit"])),
):
    """
    更新设备基本信息。
    
    如名称、类型、位置、SSH端口等。
    
    Args:
        data: 更新请求参数
    """
    patch = DeviceUpdate(
        device_name=data.device_name,
        type=data.type,
        location=data.location,
        ssh_port=data.ssh_port,
    )
    await device_service.update_device(int(data.device_id), patch, updated_by=str(user_data.get("id") or ""))
    return {"code": 200}


@router.post("/test_connect")
async def test_connect(device: DeviceTest, user_data: dict = Depends(PermissionChecker(["sys:device:add", "sys:device:edit"]))):
    """
    测试设备 SSH 连接性。
    
    尝试使用提供的参数连接设备，验证网络和账号密码是否正确。
    此操作会实际发起 SSH 连接，可能会耗时几秒钟。
    
    Args:
        device: 连接测试参数 (IP, 端口, 账号, 密码, 类型)
    """
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
    """
    获取设备单次实时状态快照。
    
    从监控缓存中读取最新的运行时状态（如 CPU、内存、在线状态）。
    """
    monitor = MonitorManager()
    snap = await monitor.get_runtime_snapshot_async(int(device_id))
    return format_ws_data(snap)


@router.get("/detail/{device_id}")
async def get_device_detail(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    """
    获取设备详细信息。
    
    返回数据包含两部分：
    1. 数据库中的静态配置信息（如 IP、位置、端口、厂商型号等）
    2. 内存/Redis 中的实时运行时状态（如 CPU、内存、在线状态、OS版本等）
    """
    # 1. 查询数据库静态信息
    # 使用 CTE 递归查询位置全路径 (例如: "校区A / 教学楼B / 机房C")
    sql = """
        WITH RECURSIVE location_path AS (
            SELECT id, parent_id, name, 1 as level, name as full_path
            FROM location_nodes
            WHERE parent_id IS NULL
            UNION ALL
            SELECT c.id, c.parent_id, c.name, p.level + 1, p.full_path || ' / ' || c.name
            FROM location_nodes c
            JOIN location_path p ON c.parent_id = p.id
        )
        SELECT
            nd.id,
            nd.device_name,
            nd.ipv4,
            nd.ipv6,
            nd.mac,
            nd.device_type,
            COALESCE(lp.full_path, ln.name, '') AS location,  -- 优先使用全路径
            lnd.node_id AS location_node_id,
            nd.ssh_port,
            nd.created_by,
            nd.is_active,
            nd.created_at,
            u.username AS created_by_name
        FROM network_devices nd
        LEFT JOIN location_node_devices lnd ON lnd.device_id = nd.id
        LEFT JOIN location_nodes ln ON ln.id = lnd.node_id
        LEFT JOIN location_path lp ON lp.id = ln.id
        LEFT JOIN users u ON u.id::text = nd.created_by
        WHERE nd.id = $1
          AND COALESCE(nd.is_active, true) = true
    """
    # 如果启用了逻辑删除，过滤掉已删除的记录
    if await device_service.has_deleted_at():
        sql += " AND nd.deleted_at IS NULL"
    
    row = await db.fetch_one(sql, int(device_id))
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 2. 格式化数据库返回的数据
    data = dict(row)
    data["created_by"] = str(data.get("created_by") or "")
    data["created_by_name"] = str(data.get("created_by_name") or DELETED_USER_DISPLAY_NAME)
    data["ops_admin_name"] = str(data.get("created_by_name") or DELETED_USER_DISPLAY_NAME)
    data["ipv4"] = str(data.get("ipv4") or "")
    data["ipv6"] = str(data.get("ipv6") or "")
    data["mac"] = str(data.get("mac") or "")
    data["ssh_port"] = int(data.get("ssh_port") or 22)
    data["location"] = str(data.get("location") or "")
    
    # 处理位置节点 ID 类型
    if "location_node_id" in data and data.get("location_node_id") is not None:
        try:
            data["location_node_id"] = int(data.get("location_node_id"))
        except Exception:
            data["location_node_id"] = None
            
    data["type"] = str(data.get("device_type") or "")

    # 3. 获取实时运行时状态
    # 从 MonitorManager 获取内存快照（包含 CPU、Memory、Uptime、Version 等）
    monitor = MonitorManager()
    snap = await monitor.get_runtime_snapshot_async(int(device_id))
    
    data.update(format_ws_data(snap))
    
    return data


# --- 设备配置管理 ---

@router.get("/config/{device_id}")
async def get_device_config(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    """
    获取设备连接配置。
    
    包括 SSH 超时时间、重试次数等高级配置。
    """
    data = await device_service.get_device_config(int(device_id))
    return {"code": 200, "data": data}


@router.post("/config/update")
async def update_device_config(
    payload: DeviceConfigUpdate,
    user: dict = Depends(PermissionChecker(["sys:device:edit"])),
):
    """
    更新设备连接配置。
    """
    updated = await device_service.update_device_config(
        int(payload.device_id), 
        payload.model_dump(exclude_unset=True),
        updated_by=str(user.get("id", ""))
    )
    return {"code": 200, "data": updated}


# --- 资源同步管理 (接口/路由/VLAN) ---

@router.get("/interfaces/{device_id}")
async def get_device_interfaces(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:interface:view"]))
):
    """
    获取设备接口列表。
    
    数据来源于上次同步的结果（存储在数据库/Redis中）。
    """
    data = await network_resource_service.get_interfaces(int(device_id))
    return {"code": 200, "data": data}

@router.get("/interfaces/detail/{device_id}")
async def get_device_interfaces_detail(
    device_id: int,
    slot: int = Query(0, ge=0),
    user: dict = Depends(PermissionChecker(["sys:device:interface:view"]))
):
    """
    获取设备接口详细数据。
    
    Args:
        slot: 插槽号 (默认为0)
    """
    data = await network_resource_service.get_interfaces_detailed(int(device_id), slot_id=int(slot))
    return {"code": 200, "data": data}

@router.get("/routes/{device_id}")
async def get_device_routes(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:route:view"]))
):
    """
    获取设备路由表。
    """
    data = await network_resource_service.get_routes(int(device_id))
    return {"code": 200, "data": data}

@router.get("/vlans/{device_id}")
async def get_device_vlans(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:vlan:view"]))
):
    """
    获取设备 VLAN 列表。
    """
    data = await network_resource_service.get_vlans(int(device_id))
    return {"code": 200, "data": data}

@router.post("/resources/sync/{device_id}")
async def sync_device_resources(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:edit"]))
):
    """
    手动触发设备资源同步。
    
    异步执行：会立即返回，后台 Worker 会连接设备并拉取最新接口、路由、VLAN 信息。
    """
    await network_resource_service.sync_device_resources(int(device_id))
    return {"code": 200, "message": "同步任务已触发"}

# --- 审计日志 ---

@router.get("/audit/logs/{device_id}")
async def get_device_audit_logs(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(PermissionChecker(["sys:device:audit"])),
):
    """
    获取设备变更审计日志。
    
    记录了设备的增删改操作、配置变更等。
    """
    result = await device_service.get_device_change_logs(int(device_id), page=int(page), page_size=int(page_size))
    return {"code": 200, "data": result}

@router.get("/audit/ssh-commands/{device_id}")
async def get_device_ssh_command_audit_logs(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(PermissionChecker(["sys:device:audit"])),
):
    """
    获取设备 SSH 命令审计日志。
    
    记录了用户通过 Web SSH 执行的所有命令。
    """
    result = await device_service.get_ssh_command_audit_logs(int(device_id), page=int(page), page_size=int(page_size))
    return {"code": 200, "data": result}

@router.post("/monitor/sync/{device_id}")
async def sync_device_monitor(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list", "sys:dashboard:view"])),
):
    """
    手动同步设备监控状态。
    
    强制刷新设备的实时状态快照。
    """
    monitor = MonitorManager()
    snap = await monitor.sync_device_snapshot(int(device_id))
    return {"code": 200, "data": snap}


# --- WebSocket 接口 ---

def format_ws_data(data: Any) -> Any:
    """Helper: 格式化 WebSocket 发送的数据"""
    if isinstance(data, dict):
        return data
    return data

@router.websocket("/ws/detail/{device_id}")
async def websocket_device_detail(websocket: WebSocket, device_id: int):
    """
    WebSocket: 设备详情实时推送。
    
    订阅单个设备的详细状态变更，包括 CPU/内存/流量/日志等高频数据。
    用于设备详情页的实时展示。
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
        
    # 权限检查
    if not user_is_super(user):
        allowed = await user_has_permission(user, "sys:device:list")
        if not allowed:
            allowed = await user_has_permission(user, "sys:dashboard:view")
        if not allowed:
            await websocket.close(code=4003, reason="权限不足")
            return

    monitor = MonitorManager()
    # 1. 订阅内存队列 (处理本机产生的监控数据)
    q = monitor.subscribe_detail(int(device_id))
    guard_task = asyncio.create_task(_ws_auth_guard(websocket, user))

    # 2. 订阅 Redis PubSub (处理其他 Worker 节点产生的监控数据，用于多实例扩展)
    async def redis_listener():
        try:
            redis_client = redis_manager.get_pubsub_client()
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
                        await websocket.send_json(format_ws_data(payload))
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
        # 发送初始快照
        snap = await monitor.sync_device_snapshot(int(device_id))
        await websocket.send_json(format_ws_data(snap))
        
        # 循环发送队列中的更新
        while True:
            payload = await q.get()
            await websocket.send_json(format_ws_data(payload))
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
        if guard_task:
            guard_task.cancel()

@router.websocket("/ws/list")
async def websocket_device_list(websocket: WebSocket):
    """
    WebSocket: 设备列表实时推送。
    
    订阅所有设备的基础状态变更（如在线/离线、CPU使用率概览）。
    用于设备列表页的实时刷新。支持双向通信，前端可发送指令获取列表。
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
    
    # WebSocket 发送锁，防止并发写入冲突
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        async with ws_lock:
            await websocket.send_json(data)

    monitor = MonitorManager()
    q = monitor.subscribe_list()
    guard_task = asyncio.create_task(_ws_auth_guard(websocket, user))

    # 1. 监听内存队列
    async def monitor_listener():
        try:
            while True:
                payload = await q.get()
                enriched = dict(payload or {})
                enriched.update(status_fields_from_snapshot(enriched))
                await send_safe_json({"type": "update", "data": enriched})
        except WebSocketDisconnect:
            raise
        except Exception:
            pass

    listener_task = asyncio.create_task(monitor_listener())

    # 2. 监听 Redis PubSub
    async def redis_listener():
        try:
            redis_client = redis_manager.get_pubsub_client()
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
                        if isinstance(payload.get("data"), dict):
                            enriched = dict(payload["data"])
                            enriched.update(status_fields_from_snapshot(enriched))
                            payload = dict(payload)
                            payload["data"] = enriched
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
            # 3. 接收前端指令 (支持双向通信)
            logger.info("Waiting for WS message...")
            data = await websocket.receive_json()
            logger.info(f"Received WS message: {data}")
            command = data.get("command")
            
            if command == "get_list":
                # 前端主动请求列表刷新
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
                # 心跳保活
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
        if guard_task:
            guard_task.cancel()


@router.websocket("/ws/resources/{device_id}")
async def websocket_device_resources(websocket: WebSocket, device_id: int):
    """
    WebSocket: 设备资源实时推送。
    
    订阅设备接口、路由、VLAN 等资源的变更通知。
    通常用于资源详情页，当后台完成资源同步时自动刷新页面。
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return

    # 权限检查
    if not user_is_super(user):
        allowed = False
        for perm in (
            "sys:device:list",
            "sys:dashboard:view",
            "sys:device:interface:view",
            "sys:device:route:view",
            "sys:device:vlan:view",
        ):
            if await user_has_permission(user, perm):
                allowed = True
                break
        if not allowed:
            await websocket.close(code=4003, reason="权限不足")
            return

    did = int(device_id)
    guard_task = asyncio.create_task(_ws_auth_guard(websocket, user))
    try:
        redis_client = redis_manager.get_pubsub_client()
    except Exception:
        guard_task.cancel()
        await websocket.close(code=1011, reason="Redis不可用")
        return

    pubsub = redis_client.pubsub()
    channel = f"ws:devices:resources:{did}"
    try:
        await pubsub.subscribe(channel)
        await websocket.send_json({"type": "ready", "device_id": did})
        
        # 发送初始数据
        try:
            interfaces = await network_resource_service.get_interfaces(did)
            routes = await network_resource_service.get_routes(did)
            vlans = await network_resource_service.get_vlans(did)
            interfaces_slot0_detailed = await network_resource_service.get_interfaces_detailed(did, slot_id=0)
            await websocket.send_json(
                {
                    "type": "resources_snapshot",
                    "device_id": did,
                    "data": {
                        "interfaces": interfaces,
                        "routes": routes,
                        "vlans": vlans,
                        "interfaces_slot0_detailed": interfaces_slot0_detailed,
                    },
                }
            )
        except Exception:
            pass
            
        # 监听更新
        async for msg in pubsub.listen():
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
                    await websocket.send_json(payload)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
        if guard_task:
            guard_task.cancel()


# --- SSH WebSocket ---

def _pick_netmiko_device_type(value) -> str:
    """Helper: 根据数据库存储的类型推断 netmiko device_type"""
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
    """
    WebSocket: Web SSH 终端连接。
    
    实现浏览器端的 SSH 终端。
    后端充当 WebSocket 和 SSH 连接之间的代理，负责数据转发。
    
    Process:
    1. WebSocket 握手与鉴权
    2. 查找设备信息 (账号、密码、端口、类型)
    3. 建立 SSH 连接 (使用 Netmiko，在线程池中执行)
    4. 启动两个后台任务：
       - ws_to_ssh: 读取 WebSocket 输入 -> 写入 SSH Channel
       - ssh_to_ws: 读取 SSH Channel 输出 -> 发送 WebSocket
    5. 记录审计日志 (连接、断开、命令)
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    port_q = websocket.query_params.get("port")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
    user_id = str(user.get("id") or "")
    guard_task = None

    # 1. 权限检查
    if not user_is_super(user):
        if not await user_has_permission(user, "sys:ssh:connect"):
            try:
                await websocket.send_text("系统: 权限不足\r\n")
            except Exception:
                pass
            await websocket.close(code=4003, reason="权限不足")
            return

    # 2. 查找设备信息 (账号密码)
    row = None
    if port_q:
        try:
            port_val = int(port_q)
        except Exception:
            port_val = None
        if port_val:
            row = await db.fetch_one(
                """
                SELECT id, user_name, password, ssh_port, device_type
                FROM network_devices
                WHERE ipv4 = $1 AND ssh_port = $2
                LIMIT 1
                """,
                str(ip),
                int(port_val),
            )
            
    # 如果没指定端口或没找到，尝试只用 IP 找
    if row is None:
        count_row = await db.fetch_one(
            """
            SELECT COUNT(1) AS c
            FROM network_devices
            WHERE ipv4 = $1
            """,
            str(ip),
        )
        total = int((count_row.get("c") if count_row else 0) or 0)
        if total == 0:
            row = None
        elif total == 1:
            row = await db.fetch_one(
                """
                SELECT id, user_name, password, ssh_port, device_type
                FROM network_devices
                WHERE ipv4 = $1
                LIMIT 1
                """,
                str(ip),
            )
        else:
            try:
                await websocket.send_text(f"系统: 存在多个设备使用IP {ip}，请在连接地址中指定端口，如 /ws/ssh/{ip}?port=22\r\n")
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
            return

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

    # 3. 获取连接配置 (超时、重试等)
    cfg = None
    try:
        cfg = await db.fetch_one(
            """
            SELECT connect_timeout, auth_timeout, banner_timeout, global_delay_factor,
                   connect_max_retries, connect_retry_delay_seconds
            FROM device_configs
            WHERE device_id = $1
            LIMIT 1
            """,
            int(device_id),
        )
    except Exception:
        cfg = None

    connect_timeout = float((cfg.get("connect_timeout") if cfg else None) or 30.0)
    auth_timeout = float((cfg.get("auth_timeout") if cfg else None) or 30.0)
    banner_timeout = float((cfg.get("banner_timeout") if cfg else None) or 100.0)
    global_delay_factor = float((cfg.get("global_delay_factor") if cfg else None) or 2.0)
    connect_max_retries = int((cfg.get("connect_max_retries") if cfg else None) or 3)
    connect_max_retries = max(1, min(8, connect_max_retries))
    retry_base_delay = float((cfg.get("connect_retry_delay_seconds") if cfg else None) or 1.0)
    retry_base_delay = max(0.1, retry_base_delay)

    device_params = {
        "device_type": device_type,
        "host": str(ip),
        "username": username,
        "password": password,
        "port": int(port),
        "timeout": connect_timeout,
        "conn_timeout": connect_timeout,
        "auth_timeout": auth_timeout,
        "banner_timeout": banner_timeout,
        "global_delay_factor": global_delay_factor,
        "allow_agent": False,
        "use_keys": False,
    }

    connected_ok = False
    try:
        last_err: Exception | None = None
        conn = None
        # 4. 执行连接 (带重试)
        for attempt in range(connect_max_retries):
            try:
                # 使用 asyncio.to_thread 在线程池中执行阻塞的 SSH 连接
                conn = await asyncio.to_thread(ConnectHandler, **device_params)
                break
            except Exception as e:
                last_err = e
                decision = classify_ssh_failure(
                    e,
                    default_base_delay_seconds=retry_base_delay,
                    default_max_delay_seconds=max(5.0, retry_base_delay * 20.0),
                )
                delay = float(decision.next_delay_seconds(attempt + 1) or retry_base_delay)
                msg = str(decision.reason or "").splitlines()[0] or "连接失败"
                if attempt == 0:
                    try:
                        await websocket.send_text(f"系统: 连接失败: {msg}，正在重试...\r\n")
                    except Exception:
                        pass
                await asyncio.sleep(delay)
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
    
    # 记录连接成功日志
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

    guard_task = asyncio.create_task(_ws_auth_guard(websocket, user))

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
            """Task: 读取 WebSocket 输入并写入 SSH"""
            while True:
                try:
                    data = await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                try:
                    if device_id:
                        # 记录命令审计日志
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
            """Task: 读取 SSH 输出并发送到 WebSocket"""
            while True:
                try:
                    out = await asyncio.to_thread(conn.read_channel)
                except Exception:
                    out = ""
                if out:
                    try:
                        await websocket.send_text(str(out))
                    except WebSocketDisconnect:
                        return
                    except Exception:
                        return
                await asyncio.sleep(0.05)

        t1 = asyncio.create_task(ws_to_ssh())
        t2 = asyncio.create_task(ssh_to_ws())
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            try:
                _ = t.exception()
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
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
        if guard_task:
            guard_task.cancel()
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
