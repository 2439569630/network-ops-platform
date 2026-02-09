from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from app.core.security import PermissionChecker, user_is_super, user_has_permission, verify_token_ws, get_or_init_user_auth_version
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationConfig, TestNotification, SiteMessageCreate, SystemAlertPayload, SystemAlertRecentResponse
from app.core.redis import redis_manager
from app.models.orm.user import User
from pydantic import BaseModel
import logging
import json
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/site-messages", response_model=dict)
async def list_site_messages(
    unread_only: bool = Query(False),
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """
    获取站内信列表
    
    Args:
        unread_only: 是否仅显示未读消息
    """
    try:
        rows = await NotificationService.list_site_messages(
            user_id=int(user.get("id")),
            limit=20,
            offset=0,
            unread_only=bool(unread_only),
        )
        return {"code": 200, "data": rows}
    except Exception as e:
        return {"code": 500, "message": f"获取站内消息失败: {str(e)}"}

@router.get("/site-messages/unread-count", response_model=dict)
async def get_site_message_unread_count(
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """获取未读站内信数量"""
    try:
        cnt = await NotificationService.get_site_message_unread_count(user_id=int(user.get("id")))
        return {"code": 200, "data": {"count": int(cnt)}}
    except Exception as e:
        return {"code": 500, "message": f"获取未读数失败: {str(e)}"}

@router.get("/site-messages/{message_id}", response_model=dict)
async def get_site_message_detail(
    message_id: int,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """获取站内信详情"""
    try:
        row = await NotificationService.get_site_message_detail(
            user_id=int(user.get("id")),
            message_id=int(message_id),
        )
        if not row:
            return {"code": 404, "message": "消息不存在"}
        return {"code": 200, "data": row}
    except Exception as e:
        return {"code": 500, "message": f"获取站内消息失败: {str(e)}"}

@router.post("/site-messages", response_model=dict)
async def create_site_message(
    data: SiteMessageCreate,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """
    发送站内信
    
    仅限管理员使用
    """
    try:
        if not user_is_super(user):
            return {"code": 403, "message": "权限不足"}

        title = str(data.title or "").strip()
        content = str(data.content or "").strip()
        target_user_id = int(data.target_user_id) if data.target_user_id is not None else None
        is_global = bool(data.is_global) if target_user_id is None else False
        row = await NotificationService.create_site_message(
            sender_id=int(user.get("id")) if user.get("id") is not None else None,
            sender_name=str(user.get("username") or user.get("name") or ""),
            title=title,
            content=content,
            source="管理员",
            target_user_id=target_user_id,
            is_global=is_global,
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
    """标记站内信为已读"""
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
    """标记站内信为未读"""
    try:
        await NotificationService.mark_site_message_unread(user_id=int(user.get("id")), message_id=int(message_id))
        return {"code": 200, "message": "未读"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

@router.post("/site-messages/read-all", response_model=dict)
async def mark_all_site_messages_read(
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """
    一键已阅：将所有未读消息标记为已读
    """
    try:
        count = await NotificationService.mark_all_site_messages_read(user_id=int(user.get("id")))
        return {"code": 200, "message": f"已将 {count} 条消息标记为已读", "data": {"count": count}}
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

@router.get("/sse/site-messages")
async def sse_site_messages(user: dict = Depends(PermissionChecker("sys:message:access"))):
    """
    SSE 站内信实时推送
    
    使用 Server-Sent Events 推送站内消息
    """
    user_id = int(user.get("id"))
    token_auth_ver = user.get("auth_ver")
    try:
        token_auth_ver = int(token_auth_ver) if token_auth_ver is not None else None
    except Exception:
        token_auth_ver = None

    async def event_stream():
        redis_client = redis_manager.get_pubsub_client()
        pubsub = redis_client.pubsub()
        channels = [
            NotificationService.SITE_MESSAGES_CHANNEL_GLOBAL,
            NotificationService.get_site_messages_user_channel(user_id),
        ]

        try:
            await pubsub.subscribe(*channels)

            yield "retry: 3000\n\n"

            init_count = await NotificationService.get_site_message_unread_count(user_id=user_id)
            yield f"event: unread\ndata: {json.dumps({'count': int(init_count)}, ensure_ascii=False)}\n\n"

            last_auth_check = 0.0
            while True:
                now = asyncio.get_running_loop().time()
                if token_auth_ver is not None and now - last_auth_check >= 3.0:
                    last_auth_check = now
                    current_ver = await get_or_init_user_auth_version(int(user_id))
                    if int(current_ver) != int(token_auth_ver):
                        return
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message and message.get("type") == "message":
                    payload = None
                    try:
                        raw = message.get("data")
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        payload = json.loads(raw) if raw else None
                    except Exception:
                        payload = None

                    if isinstance(payload, dict):
                        msg_type = str(payload.get("type") or "")
                        if msg_type == "site_message_created":
                            yield f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        elif msg_type == "site_message_read_state":
                            yield f"event: read_state\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                    next_count = await NotificationService.get_site_message_unread_count(user_id=user_id)
                    yield f"event: unread\ndata: {json.dumps({'count': int(next_count)}, ensure_ascii=False)}\n\n"
                else:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            try:
                await pubsub.unsubscribe(*channels)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

class SubscribeToggle(BaseModel):
    is_enabled: bool


@router.get("/system-alerts/recent", response_model=SystemAlertRecentResponse)
async def get_system_alerts_recent(
    limit: int = Query(50),
    user: dict = Depends(PermissionChecker("sys:notify:history")),
):
    lim = max(1, min(int(limit or 50), 200))
    try:
        redis_client = redis_manager.get_client()
    except Exception:
        return {"items": []}
    try:
        rows = await redis_client.lrange(NotificationService.SYSTEM_ALERTS_RECENT_KEY, 0, lim - 1)
    except Exception:
        rows = []
    items = []
    for raw in rows:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            obj = json.loads(raw) if raw else None
        except Exception:
            obj = None
        if isinstance(obj, dict):
            try:
                items.append(SystemAlertPayload(**obj).model_dump())
            except Exception:
                pass
    return {"items": items}


@router.websocket("/ws/system-alerts")
async def websocket_system_alerts(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
    if not user_is_super(user):
        if not await user_has_permission(user, "sys:notify:history"):
            await websocket.close(code=4003, reason="权限不足")
            return

    try:
        redis_client = redis_manager.get_pubsub_client()
    except Exception:
        await websocket.close(code=1011, reason="Redis不可用")
        return

    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(NotificationService.SYSTEM_ALERTS_CHANNEL)

        try:
            rows = await redis_client.lrange(NotificationService.SYSTEM_ALERTS_RECENT_KEY, 0, 49)
        except Exception:
            rows = []

        init_items = []
        for raw in rows:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                obj = json.loads(raw) if raw else None
            except Exception:
                obj = None
            if isinstance(obj, dict):
                init_items.append(obj)
        await websocket.send_json({"type": "init", "data": init_items})

        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                raw = msg.get("data")
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    payload = json.loads(raw) if raw else None
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    await websocket.send_json({"type": "alert", "data": payload})
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await pubsub.unsubscribe(NotificationService.SYSTEM_ALERTS_CHANNEL)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass

@router.get("/subscribers", response_model=dict)
async def get_subscribers(
    user: dict = Depends(PermissionChecker("sys:alert:subscribe"))
):
    """
    获取通知订阅用户列表
    
    管理员(sys:user:list)可以看到所有用户
    普通用户(sys:alert:subscribe)只能看到自己
    """
    try:
        user_id = user.get("id")
        is_admin = user_is_super(user) or await user_has_permission(user, "sys:user:list")
        
        query = User.all()
        if not is_admin:
            query = query.filter(id=user_id)
            
        users = await query.values("id", "username", "nickname", "email", "is_email_notify")
        return {"code": 200, "data": users}
    except Exception as e:
        return {"code": 500, "message": f"获取订阅列表失败: {str(e)}"}

@router.post("/subscribe", response_model=dict)
async def toggle_subscription(
    data: SubscribeToggle,
    user: dict = Depends(PermissionChecker("sys:alert:subscribe"))
):
    """切换通知订阅状态"""
    try:
        user_obj = await User.get(id=user.get("id"))
        user_obj.is_email_notify = data.is_enabled
        await user_obj.save()
        return {"code": 200, "message": "设置成功", "data": {"is_email_notify": user_obj.is_email_notify}}
    except Exception as e:
        return {"code": 500, "message": f"设置失败: {str(e)}"}
