from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from app.core.security import PermissionChecker, verify_token_ws, user_is_super, user_has_permission
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationConfig, TestNotification
from app.core.redis import redis_manager
import logging
import json
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

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
