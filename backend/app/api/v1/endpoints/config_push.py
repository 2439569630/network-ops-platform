# -*- coding: utf-8 -*-
#
# 配置下发 API 接口
#
# 此模块负责处理网络设备的批量配置下发任务。
# 支持创建配置下发任务、查询任务状态、取消任务以及通过 WebSocket 实时推送任务进度。
# 任务的实际执行由后台 Worker 进程处理，API 仅负责任务的创建和状态查询。
#

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query

from app.core.redis import redis_manager
from app.core.security import PermissionChecker, user_has_permission, user_is_super, verify_token_ws, UnicornException, get_or_init_user_auth_version
from app.schemas.config_push import ConfigPushJobCreateRequest
from app.services.config_push_service import ConfigPushService, normalize_command_list


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/jobs")
async def create_config_push_job(
    req: ConfigPushJobCreateRequest,
    user_data: dict = Depends(PermissionChecker(["sys:config:push"])),
):
    """
    创建配置下发任务。
    
    接收设备列表和配置命令，创建一个后台任务来执行配置下发。
    命令支持列表形式或文本形式（自动按行分割）。
    
    Args:
        req: 任务创建请求，包含设备ID列表、命令列表等
        user_data: 当前用户信息
        
    Returns:
        dict: 包含任务ID和初始状态
    """
    # 1. 规范化命令列表
    # 用户可能通过 commands (列表) 或 commands_text (多行文本) 提交命令
    # 这里统一处理为字符串列表，并去除空行和首尾空格
    commands = normalize_command_list(req.commands, req.commands_text)
    
    if not commands:
        return {"code": 400, "message": "配置命令不能为空"}
    
    # 2. 调用 Service 创建任务
    # 创建任务记录和任务详情 (job_devices)，状态置为 pending
    job_id = await ConfigPushService.create_job(
        creator_id=int(user_data.get("id")),
        title=req.title,
        device_ids=req.device_ids,
        commands=commands,
    )
    
    # 3. 返回任务 ID，后续客户端可通过 WebSocket 监听该 ID 的进度
    return {"code": 200, "data": {"job_id": int(job_id), "status": "pending"}}


@router.get("/jobs/{job_id}")
async def get_config_push_job(
    job_id: int,
    user_data: dict = Depends(PermissionChecker(["sys:config:push"])),
):
    """
    获取配置下发任务详情。
    
    包含任务的基本信息、每个设备的执行状态和输出结果。
    普通用户只能查看自己创建的任务，超级管理员可查看所有。
    
    Args:
        job_id: 任务ID
        user_data: 当前用户信息
        
    Returns:
        dict: 任务详情数据
        
    Raises:
        UnicornException: 如果无权访问
    """
    payload = await ConfigPushService.get_job(int(job_id))
    job = payload.get("job") or {}
    
    # 权限检查：非超管只能看自己的任务
    if not user_is_super(user_data):
        if int(job.get("creator_id") or 0) != int(user_data.get("id") or 0):
            raise UnicornException(403, "权限不足")
            
    return {"code": 200, "data": payload}


@router.post("/jobs/{job_id}/cancel")
async def cancel_config_push_job(
    job_id: int,
    user_data: dict = Depends(PermissionChecker(["sys:config:push"])),
):
    """
    取消配置下发任务。
    
    仅能取消尚未开始或正在执行中的任务。
    普通用户只能取消自己创建的任务。
    
    Args:
        job_id: 任务ID
        user_data: 当前用户信息
        
    Returns:
        dict: 操作结果
        
    Raises:
        UnicornException: 如果无权操作
    """
    payload = await ConfigPushService.get_job(int(job_id))
    job = payload.get("job") or {}
    
    # 权限检查
    if not user_is_super(user_data):
        if int(job.get("creator_id") or 0) != int(user_data.get("id") or 0):
            raise UnicornException(403, "权限不足")
            
    # 执行取消操作
    await ConfigPushService.cancel_job(int(job_id), actor_id=int(user_data.get("id") or 0))
    return {"code": 200}


@router.websocket("/ws/{job_id}")
async def config_push_ws(websocket: WebSocket, job_id: int, token: str | None = Query(None)):
    """
    WebSocket 实时推送配置下发任务进度。
    
    客户端连接此 WebSocket 后，服务器会实时推送任务的执行日志和状态变更。
    使用 Redis Stream 实现消息分发。
    
    Args:
        websocket: WebSocket 连接对象
        job_id: 任务ID
        token: 认证 Token (通过 Query 参数传递)
    """
    await websocket.accept()
    
    # WebSocket 握手阶段的 Token 验证
    user = await verify_token_ws(websocket, token)
    if not user:
        return
        
    # 权限检查
    if not await user_has_permission(user, "sys:config:push"):
        try:
            await websocket.send_text("系统: 权限不足\r\n")
        except Exception:
            pass
        await websocket.close(code=4003, reason="权限不足")
        return

    # 1. 权限检查：确保用户有权查看此任务
    # 超级管理员可查看所有，普通用户只能查看自己创建的任务
    try:
        job_payload = await ConfigPushService.get_job(int(job_id))
        job = job_payload.get("job") or {}
        if not user_is_super(user):
            if int(job.get("creator_id") or 0) != int(user.get("id") or 0):
                await websocket.close(code=4003, reason="权限不足")
                return
    except Exception:
        await websocket.close(code=4004, reason="任务不存在")
        return

    # 2. 准备 Redis Stream 消费者
    # 支持从指定的 last_id 开始消费，实现断线重连
    # 默认从 "0-0" 开始，即获取该任务的所有历史日志
    last_id = str(websocket.query_params.get("last_id") or "0-0").strip() or "0-0"
    redis = redis_manager.get_client()

    try:
        token_auth_ver = user.get("auth_ver")
        try:
            token_auth_ver = int(token_auth_ver) if token_auth_ver is not None else None
        except Exception:
            token_auth_ver = None
        last_auth_check = 0.0
        
        # 3. 进入消息循环
        while True:
            now = asyncio.get_running_loop().time()
            
            # 3.1 定期检查用户会话状态 (每2秒)
            if token_auth_ver is not None and now - last_auth_check >= 2.0:
                last_auth_check = now
                current_ver = await get_or_init_user_auth_version(int(user.get("id") or 0))
                if int(current_ver) != int(token_auth_ver):
                    await websocket.close(code=4001, reason="会话已失效")
                    return
                    
            # 3.2 从 Redis Stream 读取新消息
            # xread(block=1000) 阻塞等待 1秒，如有新消息立即返回
            try:
                # 注意：Stream Key 需要与 Service 中写入的一致
                # 这里假设 ConfigPushService.events_stream 返回正确的 Key
                actual_stream_key = ConfigPushService.events_stream(int(job_id))
                res = await redis.xread({actual_stream_key: last_id}, count=100, block=1000)
            except Exception:
                res = None
                
            if not res:
                # 无消息，继续下一次循环
                # 这里短暂休眠并非必须，因为 xread 已经阻塞了，但为了安全起见保留
                await asyncio.sleep(0.01) 
                continue
                
            # 3.3 处理并发送消息
            for _stream_name, entries in res:
                for entry_id, fields in (entries or []):
                    last_id = str(entry_id) # 更新 last_id，用于下次读取
                    
                    # 构造消息体
                    payload: Dict[str, Any] = {"id": str(entry_id)}
                    if isinstance(fields, dict):
                        # Redis Stream 字段通常是 bytes，需要解码 (redis-py decode_responses=True 时不需要)
                        # 假设 redis_manager 返回的 client 已配置 decode_responses=True
                        payload.update({str(k): v for k, v in fields.items()})
                        
                    await websocket.send_json(payload)
                    
    except WebSocketDisconnect:
        # 客户端断开连接
        return
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.error(f"config-push ws error: {e}")
        try:
            await websocket.close(code=1011, reason="服务器错误")
        except Exception:
            pass
