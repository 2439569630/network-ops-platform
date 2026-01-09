from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from app.core.security import PermissionChecker, verify_token_ws, user_is_super, user_has_permission
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationConfig, TestNotification, SiteMessageCreate
from app.core.redis import redis_manager
import logging
import json
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/site-messages", response_model=dict)
async def list_site_messages(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    try:
        rows = await NotificationService.list_site_messages(
            user_id=int(user.get("id")),
            limit=int(limit),
            offset=int(offset),
            unread_only=bool(unread_only),
        )
        return {"code": 200, "data": rows}
    except Exception as e:
        return {"code": 500, "message": f"获取站内消息失败: {str(e)}"}

@router.post("/site-messages", response_model=dict)
async def create_site_message(
    data: SiteMessageCreate,
    user: dict = Depends(PermissionChecker("sys:notify:global")),
):
    try:
        row = await NotificationService.create_site_message(
            sender_id=int(user.get("id")) if user.get("id") is not None else None,
            sender_name=str(user.get("username") or user.get("name") or ""),
            title=data.title,
            content=data.content,
            level=data.level or "info",
            source=data.source or "管理员",
            target_user_id=data.target_user_id,
            is_global=bool(data.is_global) if data.target_user_id is None else False,
        )
        return {"code": 200, "data": row, "message": "发布成功"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"发布失败: {str(e)}"}

@router.post("/site-messages/{message_id}/read", response_model=dict)
async def mark_site_message_read(
    message_id: int,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    try:
        await NotificationService.mark_site_message_read(user_id=int(user.get("id")), message_id=int(message_id))
        return {"code": 200, "message": "已读"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

@router.post("/site-messages/{message_id}/unread", response_model=dict)
async def mark_site_message_unread(
    message_id: int,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    try:
        await NotificationService.mark_site_message_unread(user_id=int(user.get("id")), message_id=int(message_id))
        return {"code": 200, "message": "未读"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

@router.get("/history", response_model=dict)
async def get_history(user: dict = Depends(PermissionChecker("sys:notify:history"))):
    """获取通知历史"""
    try:
        can_view_all = user_is_super(user) or (await user_has_permission(user, "sys:notify:global"))
        rows = await NotificationService.get_history(bool(can_view_all), user.get('id'))
        return {"code": 200, "data": rows}
    except Exception as e:
        return {"code": 500, "message": f"获取历史失败: {str(e)}"}

@router.get("/config", response_model=dict)
async def get_config(user: dict = Depends(PermissionChecker("sys:notify:config:view"))):
    """获取用户通知配置"""
    try:
        config = await NotificationService.get_config(user.get('id'))
        return {"code": 200, "data": config}
    except Exception as e:
        return {"code": 500, "message": f"获取配置失败: {str(e)}"}

@router.post("/config", response_model=dict)
async def update_config(
    data: NotificationConfig,
    user: dict = Depends(PermissionChecker("sys:notify:config:edit")),
):
    """更新用户通知配置"""
    try:
        if getattr(data, "use_global_email", False):
            if not user_is_super(user):
                if not await user_has_permission(user, "sys:notify:global"):
                    return {"code": 403, "message": "权限不足"}
        await NotificationService.update_config(user.get('id'), data)
        return {"code": 200, "message": "配置保存成功"}
    except ValueError as e:
        return {"code": 403, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"保存失败: {str(e)}"}

@router.post("/test", response_model=dict)
async def test_notification(
    data: TestNotification,
    user: dict = Depends(PermissionChecker("sys:notify:test")),
):
    """测试通知发送"""
    try:
        if data.channel == "email" and data.config and data.config.get("use_global_email"):
            if not user_is_super(user):
                if not await user_has_permission(user, "sys:notify:global"):
                    return {"code": 403, "message": "权限不足"}
        success, msg = await NotificationService.test_notification(data)
        if success:
            return {"code": 200, "message": "发送成功"}
        else:
            return {"code": 500, "message": f"发送失败: {msg}"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        logger.error(f"Test notification error: {e}")
        return {"code": 500, "message": str(e)}

@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await websocket.accept()
    
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
    if not (user_is_super(user) or (await user_has_permission(user, "sys:alert:subscribe"))):
        await websocket.close(code=4003, reason="权限不足")
        return

    redis_client = redis_manager.get_client()
    pubsub = redis_client.pubsub()
    
    # WebSocket 发送锁
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        try:
            async with ws_lock:
                await websocket.send_json(data)
        except:
            pass 

    # 监听任务
    async def redis_listener():
        try:
            await pubsub.subscribe("system_alerts")
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'message':
                    try:
                        data_str = message['data']
                        if isinstance(data_str, bytes):
                            data_str = data_str.decode('utf-8')
                        
                        alert_data = json.loads(data_str)
                        await send_safe_json(alert_data)
                    except Exception as e:
                        logger.error(f"Alert WS parse error: {e}")
                
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Alert WS listener error: {e}")

    listener_task = asyncio.create_task(redis_listener())

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        await pubsub.close()
