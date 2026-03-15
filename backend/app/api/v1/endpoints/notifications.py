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
    except Exception:
        logger.exception("list_site_messages failed: user_id=%s unread_only=%s", str(user.get("id")), str(unread_only))
        return {"code": 500, "message": "获取站内消息失败"}

@router.get("/site-messages/unread-count", response_model=dict)
async def get_site_message_unread_count(
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """获取未读站内信数量"""
    try:
        cnt = await NotificationService.get_site_message_unread_count(user_id=int(user.get("id")))
        return {"code": 200, "data": {"count": int(cnt)}}
    except Exception:
        logger.exception("get_site_message_unread_count failed: user_id=%s", str(user.get("id")))
        return {"code": 500, "message": "获取未读数失败"}

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
    except Exception:
        logger.exception(
            "get_site_message_detail failed: user_id=%s message_id=%s",
            str(user.get("id")),
            str(message_id),
        )
        return {"code": 500, "message": "获取站内消息失败"}

@router.post("/site-messages", response_model=dict)
async def create_site_message(
    data: SiteMessageCreate,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """
    发送站内信
    
    仅限管理员使用
    """
    title = ""
    target_user_id = None
    is_global = False
    try:
        # 1. 权限检查：仅超级管理员可发送全站/定向消息
        if not user_is_super(user):
            return {"code": 403, "message": "权限不足"}

        title = str(data.title or "").strip()
        content = str(data.content or "").strip()
        target_user_id = int(data.target_user_id) if data.target_user_id is not None else None
        
        # 2. 确定消息范围
        # 如果未指定 target_user_id，则视为全局消息 (is_global=True)
        # 全局消息对所有用户可见
        is_global = bool(data.is_global) if target_user_id is None else False
        
        # 3. 创建消息记录
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
    except Exception:
        logger.exception(
            "create_site_message failed: sender_id=%s target_user_id=%s is_global=%s title_len=%s",
            str(user.get("id")),
            str(target_user_id) if target_user_id is not None else "",
            str(is_global),
            str(len(title)),
        )
        return {"code": 500, "message": "发布失败"}

@router.post("/site-messages/{message_id}/read", response_model=dict)
async def mark_site_message_read(
    message_id: int,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """标记站内信为已读"""
    try:
        await NotificationService.mark_site_message_read(user_id=int(user.get("id")), message_id=int(message_id))
        return {"code": 200, "message": "已读"}
    except Exception:
        logger.exception(
            "mark_site_message_read failed: user_id=%s message_id=%s",
            str(user.get("id")),
            str(message_id),
        )
        return {"code": 500, "message": "操作失败"}

@router.post("/site-messages/{message_id}/unread", response_model=dict)
async def mark_site_message_unread(
    message_id: int,
    user: dict = Depends(PermissionChecker("sys:message:access")),
):
    """标记站内信为未读"""
    try:
        await NotificationService.mark_site_message_unread(user_id=int(user.get("id")), message_id=int(message_id))
        return {"code": 200, "message": "未读"}
    except Exception:
        logger.exception(
            "mark_site_message_unread failed: user_id=%s message_id=%s",
            str(user.get("id")),
            str(message_id),
        )
        return {"code": 500, "message": "操作失败"}

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
    except Exception:
        logger.exception("mark_all_site_messages_read failed: user_id=%s", str(user.get("id")))
        return {"code": 500, "message": "操作失败"}

@router.get("/history", response_model=dict)
async def get_history(user: dict = Depends(PermissionChecker("sys:notify:history"))):
    """获取通知历史"""
    try:
        can_view_all = user_is_super(user) or (await user_has_permission(user, "sys:notify:global"))
        rows = await NotificationService.get_history(bool(can_view_all), user.get('id'))
        return {"code": 200, "data": rows}
    except Exception:
        logger.exception("get_history failed: user_id=%s", str(user.get("id")))
        return {"code": 500, "message": "获取历史失败"}

@router.get("/config", response_model=dict)
async def get_config(user: dict = Depends(PermissionChecker("sys:notify:config:view"))):
    """获取用户通知配置"""
    try:
        config = await NotificationService.get_config(user.get('id'))
        return {"code": 200, "data": config}
    except Exception:
        logger.exception("get_config failed: user_id=%s", str(user.get("id")))
        return {"code": 500, "message": "获取配置失败"}

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
    except Exception:
        logger.exception("update_config failed: user_id=%s", str(user.get("id")))
        return {"code": 500, "message": "保存失败"}

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
            logger.error("test_notification failed: %s", str(msg or ""))
            return {"code": 500, "message": "发送失败"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception:
        logger.exception("test_notification error")
        return {"code": 500, "message": "发送失败"}

@router.get("/sse/site-messages")
async def sse_site_messages(user: dict = Depends(PermissionChecker("sys:message:access"))):
    """
    SSE 站内信实时推送
    
    使用 Server-Sent Events (SSE) 技术推送站内消息。
    客户端建立连接后，服务端会保持连接开启，并通过 Redis PubSub 监听消息。
    
    推送内容包括：
    1. 新消息通知 (message)
    2. 消息已读状态变更 (read_state)
    3. 未读数更新 (unread)
    
    包含心跳检测 (ping) 和认证状态检查 (auth_ver)。
    """
    user_id = int(user.get("id"))
    token_auth_ver = user.get("auth_ver")
    try:
        token_auth_ver = int(token_auth_ver) if token_auth_ver is not None else None
    except Exception:
        token_auth_ver = None

    async def event_stream():
        # 1. 建立 Redis PubSub 连接
        # 使用独立的连接，避免阻塞主连接池
        redis_client = redis_manager.get_pubsub_client()
        pubsub = redis_client.pubsub()
        
        # 2. 订阅频道
        # 订阅全局消息频道和用户专属频道 (用于定向消息)
        channels = [
            NotificationService.SITE_MESSAGES_CHANNEL_GLOBAL,
            NotificationService.get_site_messages_user_channel(user_id),
        ]

        try:
            await pubsub.subscribe(*channels)

            # 3. 发送 SSE 重连时间设置
            yield "retry: 3000\n\n"

            # 4. 首次推送：发送当前未读数
            init_count = await NotificationService.get_site_message_unread_count(user_id=user_id)
            yield f"event: unread\ndata: {json.dumps({'count': int(init_count)}, ensure_ascii=False)}\n\n"

            last_auth_check = 0.0
            while True:
                now = asyncio.get_running_loop().time()
                
                # 5. 定期检查用户认证状态 (每3秒)
                # 防止用户注销或密码变更后 SSE 仍保持连接
                if token_auth_ver is not None and now - last_auth_check >= 3.0:
                    last_auth_check = now
                    current_ver = await get_or_init_user_auth_version(int(user_id))
                    if int(current_ver) != int(token_auth_ver):
                        # 认证失效，断开连接
                        return
                        
                # 6. 等待 Redis 消息 (非阻塞，带超时)
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
                        # 7. 根据消息类型推送不同事件
                        if msg_type == "site_message_created":
                            yield f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        elif msg_type == "site_message_read_state":
                            yield f"event: read_state\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                    # 8. 每次收到消息后，推送最新的未读数
                    next_count = await NotificationService.get_site_message_unread_count(user_id=user_id)
                    yield f"event: unread\ndata: {json.dumps({'count': int(next_count)}, ensure_ascii=False)}\n\n"
                else:
                    # 9. 发送心跳包 (Ping) 保持连接活跃
                    # 避免前端 EventSource 因超时自动重连
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
    """
    获取最近的系统告警记录
    
    从 Redis 缓存列表中获取最近的告警消息。
    通常用于前端页面初始化时展示历史告警。
    
    Args:
        limit: 获取数量限制，默认 50，最大 200
    """
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
    """
    WebSocket 系统告警实时推送
    
    用于实时接收系统产生的告警消息。
    连接建立后，首先推送最近的历史告警 (init)，然后进入监听模式 (alert)。
    
    Args:
        token: 认证 Token (通过 Query 参数传递)
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return
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
        # 1. 订阅系统告警频道
        await pubsub.subscribe(NotificationService.SYSTEM_ALERTS_CHANNEL)

        # 2. 获取最近的历史告警 (Recent Alerts)
        # 用于前端页面初始化时填充数据，避免空白
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
        
        # 3. 推送初始化数据 (type: init)
        await websocket.send_json({"type": "init", "data": init_items})

        # 4. 进入实时监听循环
        while True:
            # 使用较短的 timeout (1.0s) 以便能响应 WebSocket 断开事件
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
                    # 5. 推送实时告警 (type: alert)
                    await websocket.send_json({"type": "alert", "data": payload})
            
            # 6. 短暂休眠，避免 CPU 占用过高
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
    except Exception:
        logger.exception("get_subscribers failed: user_id=%s", str(user.get("id")))
        return {"code": 500, "message": "获取订阅列表失败"}

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
    except Exception:
        logger.exception("toggle_subscription failed: user_id=%s is_enabled=%s", str(user.get("id")), str(getattr(data, "is_enabled", "")))
        return {"code": 500, "message": "设置失败"}
