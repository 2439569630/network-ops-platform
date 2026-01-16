
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from app.core.database import db
from app.core.redis import redis_manager
from app.core.system_config import SystemConfig
from app.utils.notification_sender import send_email, send_pushplus, send_http
from app.schemas.notification import NotificationConfig, TestNotification

# ORM Imports
from app.models.orm.notification import DeviceNotification, SiteMessage, SiteMessageRead, UserNotificationConfig
from app.models.orm.device import NetworkDevice
from tortoise.expressions import Q

logger = logging.getLogger(__name__)

class NotificationService:
    SYSTEM_ALERTS_CHANNEL = "system_alerts"
    SYSTEM_ALERTS_RECENT_KEY = "system_alerts:recent"
    SYSTEM_ALERTS_RECENT_LIMIT = 500
    SYSTEM_ALERTS_RECENT_TTL_SECONDS = 7 * 24 * 60 * 60
    SITE_MESSAGES_CHANNEL_GLOBAL = "site_messages:global"
    SITE_MESSAGES_CHANNEL_USER_PREFIX = "site_messages:user:"
    _site_message_tables_ready = False
    _user_notification_config_table_ready = False
    SITE_MESSAGE_EMAIL_MAX_RECIPIENTS = 500
    SITE_MESSAGE_EMAIL_CONCURRENCY = 10

    @staticmethod
    async def get_history(can_view_all: bool, user_id: int) -> List[dict]:
        """获取通知历史"""
        if can_view_all:
            # Join with NetworkDevice to get device_name
            notifications = await DeviceNotification.all().order_by("-created_at").limit(100)
            
            # Fetch device names manually or assume they are in message? 
            # The original SQL joined network_devices.
            # Let's map device names.
            device_ids = {n.device_id for n in notifications if n.device_id}
            devices = await NetworkDevice.filter(id__in=list(device_ids)).all()
            device_map = {d.id: d.device_name for d in devices}

            result = []
            for n in notifications:
                result.append({
                    "id": n.id,
                    "device_id": n.device_id,
                    "device_name": device_map.get(n.device_id, ""),
                    "level": n.level,
                    "message": n.message,
                    "created_at": n.created_at
                })
            return result
        else:
            # TODO: Filter by user's devices
            return []

    @staticmethod
    async def _ensure_site_message_tables():
        # Assumed handled by Tortoise init
        return

    @staticmethod
    async def _ensure_user_notification_config_table():
        # Assumed handled by Tortoise init
        return

    @staticmethod
    async def list_site_messages(
        *,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[dict]:
        lim = max(1, min(int(limit or 100), 200))
        off = max(0, int(offset or 0))

        # Query messages targeted to user OR global
        query = SiteMessage.filter(Q(is_global=True) | Q(target_user_id=user_id))
        
        # Unread filter is tricky with ORM unless we do a subquery or join.
        # Tortoise supports joins if defined in model. 
        # But we don't have explicit relationship defined in SiteMessage model pointing to SiteMessageRead.
        # We can fetch reads first.
        
        reads = await SiteMessageRead.filter(user_id=user_id).all()
        read_msg_ids = {r.message_id for r in reads}
        
        if unread_only:
            query = query.filter(id__not_in=list(read_msg_ids))
            
        messages = await query.order_by("-created_at").offset(off).limit(lim)
        
        result = []
        for m in messages:
            read_at = None
            is_read = False
            # Find read status
            # This is inefficient for large lists if we iterate reads list every time, 
            # but reads list is for ONE user, usually manageable. 
            # Better: use a dict for O(1) lookup.
            read_entry = next((r for r in reads if r.message_id == m.id), None)
            if read_entry:
                is_read = True
                read_at = read_entry.read_at
            
            result.append({
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": m.sender_name,
                "source": m.source,
                "title": m.title,
                "content": m.content,
                "is_global": m.is_global,
                "target_user_id": m.target_user_id,
                "created_at": m.created_at,
                "is_read": is_read,
                "read_at": read_at
            })
            
        return result

    @staticmethod
    async def get_site_message_detail(*, user_id: int, message_id: int) -> Optional[dict]:
        m = await SiteMessage.filter(id=message_id).filter(Q(is_global=True) | Q(target_user_id=user_id)).first()
        if not m:
            return None
            
        read_entry = await SiteMessageRead.filter(user_id=user_id, message_id=message_id).first()
        
        return {
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "source": m.source,
            "title": m.title,
            "content": m.content,
            "is_global": m.is_global,
            "target_user_id": m.target_user_id,
            "created_at": m.created_at,
            "is_read": bool(read_entry),
            "read_at": read_entry.read_at if read_entry else None
        }

    @staticmethod
    async def create_site_message(
        *,
        sender_id: Optional[int],
        sender_name: Optional[str],
        title: str,
        content: str,
        source: str = "管理员",
        target_user_id: Optional[int] = None,
        is_global: bool = True,
    ) -> dict:
        t = str(title or "").strip()
        c = str(content or "").strip()
        if not t:
            raise ValueError("标题不能为空")
        if not c:
            raise ValueError("内容不能为空")

        tg = int(target_user_id) if target_user_id is not None else None
        global_flag = bool(is_global) if tg is None else False
        if tg is None and not global_flag:
            raise ValueError("请选择全站或指定用户")

        msg = await SiteMessage.create(
            sender_id=sender_id,
            sender_name=sender_name,
            source=str(source or "系统"),
            title=t,
            content=c,
            is_global=global_flag,
            target_user_id=tg,
            created_at=datetime.now(timezone.utc),
        )
        
        # Result dict
        result = {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender_name,
            "source": msg.source,
            "title": msg.title,
            "content": msg.content,
            "is_global": msg.is_global,
            "target_user_id": msg.target_user_id,
            "created_at": msg.created_at
        }

        try:
            await NotificationService.publish_site_message_created(
                target_user_id=tg,
                is_global=global_flag,
                message=result,
            )
        except Exception as e:
            logger.error(f"发布站内消息实时事件失败: {e}")

        return result

    @staticmethod
    async def mark_site_message_read(*, user_id: int, message_id: int) -> bool:
        # Check if already read
        exists = await SiteMessageRead.filter(user_id=user_id, message_id=message_id).exists()
        if not exists:
            await SiteMessageRead.create(user_id=user_id, message_id=message_id, read_at=datetime.now(timezone.utc))
        else:
            # Update read_at?
            await SiteMessageRead.filter(user_id=user_id, message_id=message_id).update(read_at=datetime.now(timezone.utc))

        try:
            await NotificationService.publish_site_message_read_state_changed(
                target_user_id=int(user_id),
                message_id=int(message_id),
                is_read=True,
            )
        except Exception as e:
            logger.error(f"发布站内消息已读事件失败: {e}")
        return True

    @staticmethod
    async def mark_site_message_unread(*, user_id: int, message_id: int) -> bool:
        await SiteMessageRead.filter(user_id=user_id, message_id=message_id).delete()
        try:
            await NotificationService.publish_site_message_read_state_changed(
                target_user_id=int(user_id),
                message_id=int(message_id),
                is_read=False,
            )
        except Exception as e:
            logger.error(f"发布站内消息未读事件失败: {e}")
        return True

    @staticmethod
    def get_site_messages_user_channel(user_id: int) -> str:
        return f"{NotificationService.SITE_MESSAGES_CHANNEL_USER_PREFIX}{int(user_id)}"

    @staticmethod
    def _json_default(obj: Any):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    @staticmethod
    async def publish_site_message_created(*, target_user_id: Optional[int], is_global: bool, message: dict) -> None:
        redis_client = redis_manager.get_client()
        payload = {
            "type": "site_message_created",
            "target_user_id": int(target_user_id) if target_user_id is not None else None,
            "is_global": bool(is_global),
            "message": message or {},
        }
        payload_str = json.dumps(payload, ensure_ascii=False, default=NotificationService._json_default)
        if is_global:
            await redis_client.publish(NotificationService.SITE_MESSAGES_CHANNEL_GLOBAL, payload_str)
        elif target_user_id is not None:
            await redis_client.publish(NotificationService.get_site_messages_user_channel(int(target_user_id)), payload_str)

    @staticmethod
    async def publish_site_message_read_state_changed(
        *, target_user_id: Optional[int], message_id: int, is_read: bool
    ) -> None:
        if target_user_id is None:
            return
        redis_client = redis_manager.get_client()
        payload = {
            "type": "site_message_read_state",
            "target_user_id": int(target_user_id),
            "is_global": False,
            "message_id": int(message_id),
            "is_read": bool(is_read),
        }
        payload_str = json.dumps(payload, ensure_ascii=False, default=NotificationService._json_default)
        await redis_client.publish(NotificationService.get_site_messages_user_channel(int(target_user_id)), payload_str)

    @staticmethod
    async def get_site_message_unread_count(*, user_id: int) -> int:
        # Count messages for user (global or direct)
        total_msgs = await SiteMessage.filter(Q(is_global=True) | Q(target_user_id=user_id)).count()
        # Count read messages
        # Note: This logic is slightly flawed if global messages are many and reads are many.
        # Ideally: Count (All Applicable Messages) - Count (Read Messages for those messages)
        # But we can iterate or use a smarter query.
        # Since we are using ORM without complex joins (or rather, explicit joins), 
        # let's try to do it accurately.
        
        # Raw SQL was:
        # SELECT COUNT(1) AS cnt
        # FROM site_messages m
        # LEFT JOIN site_message_reads r
        #     ON r.message_id = m.id AND r.user_id = $1
        # WHERE (m.is_global = TRUE OR m.target_user_id = $1)
        #   AND r.read_at IS NULL
        
        # In ORM:
        # Fetch IDs of read messages for this user
        read_ids = await SiteMessageRead.filter(user_id=user_id).values_list('message_id', flat=True)
        
        # Count messages targeted to user that are NOT in read_ids
        cnt = await SiteMessage.filter(Q(is_global=True) | Q(target_user_id=user_id)).filter(id__not_in=read_ids).count()
        return cnt

    @staticmethod
    async def notify(
        *,
        level: str,
        source: str,
        type: str,
        description: str,
        device_id: Optional[int] = None,
        device_name: Optional[str] = None,
        ipv4: Optional[str] = None,
        save_history: bool = True,
        publish_realtime: bool = True,
        cache_realtime: bool = True,
        time_iso: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "time": time_iso or datetime.now(timezone.utc).isoformat(),
            "level": level,
            "source": source,
            "type": type,
            "description": description,
        }

        if device_id is not None:
            payload["device_id"] = device_id
        if device_name:
            payload["device_name"] = device_name
        if ipv4:
            payload["ipv4"] = ipv4
        if extra:
            payload.update(extra)

        if save_history:
            try:
                await DeviceNotification.create(
                    device_id=device_id,
                    level=level,
                    message=description,
                    created_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error(f"写入通知历史失败: {e}")

        if publish_realtime or cache_realtime:
            try:
                redis_client = redis_manager.get_client()
                payload_str = json.dumps(payload, ensure_ascii=False)
                async with redis_client.pipeline(transaction=True) as pipe:
                    if cache_realtime:
                        await pipe.lpush(NotificationService.SYSTEM_ALERTS_RECENT_KEY, payload_str)
                        await pipe.ltrim(NotificationService.SYSTEM_ALERTS_RECENT_KEY, 0, NotificationService.SYSTEM_ALERTS_RECENT_LIMIT - 1)
                        await pipe.expire(NotificationService.SYSTEM_ALERTS_RECENT_KEY, NotificationService.SYSTEM_ALERTS_RECENT_TTL_SECONDS)
                    if publish_realtime:
                        await pipe.publish(NotificationService.SYSTEM_ALERTS_CHANNEL, payload_str)
                    await pipe.execute()
            except Exception as e:
                logger.error(f"Redis 发布/缓存通知失败: {e}")

        return payload

    @staticmethod
    async def notify_device_offline(device_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        device_name = None
        ipv4 = None
        try:
            dev = await NetworkDevice.filter(id=device_id).first()
            if dev:
                device_name = dev.device_name
                ipv4 = str(dev.ipv4) if dev.ipv4 else None
        except Exception as e:
            logger.error(f"获取设备信息失败: {e}")

        display_name = device_name or f"Device {device_id}"
        display_ip = ipv4 or "-"

        message = f"{display_name} ({display_ip}) 离线"
        if reason:
            message = f"{message}: {reason}"

        return await NotificationService.notify(
            level="error",
            source=display_name,
            type="device_offline",
            description=message,
            device_id=device_id,
            device_name=display_name,
            ipv4=display_ip,
            save_history=True,
            publish_realtime=True,
            cache_realtime=True,
        )

    @staticmethod
    async def notify_repair_order_submitted(
        *,
        order_id: int,
        title: str,
        priority: str,
        submitter_id: int,
        submitter_name: Optional[str] = None,
        device_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        level = "info"
        p = str(priority or "").strip().lower()
        if p in {"high"}:
            level = "warning"
        if p in {"emergency"}:
            level = "error"

        device_name = None
        ipv4 = None
        if device_id is not None:
            try:
                dev = await NetworkDevice.filter(id=device_id).first()
                if dev:
                    device_name = dev.device_name
                    ipv4 = str(dev.ipv4) if dev.ipv4 else None
            except Exception as e:
                logger.error(f"获取工单关联设备信息失败: {e}")

        submitter_display = submitter_name or f"用户{submitter_id}"
        parts = [f"新工单 #{order_id}", title]
        if device_name:
            ip_part = f" ({ipv4})" if ipv4 else ""
            parts.append(f"设备: {device_name}{ip_part}")
        parts.append(f"优先级: {priority}")
        parts.append(f"提交人: {submitter_display}")
        description = " | ".join([p for p in parts if p])

        extra: Dict[str, Any] = {
            "order_id": order_id,
            "priority": priority,
            "submitter_id": submitter_id,
            "submitter_name": submitter_name,
            "status": "pending",
        }

        return await NotificationService.notify(
            level=level,
            source="工单系统",
            type="repair_order_submitted",
            description=description,
            device_id=device_id,
            device_name=device_name,
            ipv4=ipv4,
            save_history=True,
            publish_realtime=True,
            cache_realtime=True,
            extra=extra,
        )

    @staticmethod
    async def get_config(user_id: int) -> dict:
        """获取用户通知配置"""
        config = await UserNotificationConfig.filter(user_id=user_id).first()
        
        if not config:
            return {
                "enable_email": False,
                "email_config": {},
                "enable_pushplus": False,
                "pushplus_token": "",
                "enable_http": False,
                "http_url": ""
            }
            
        data = dict(config)
        # JSONField automatically handles deserialization in Tortoise, usually.
        # But if it was stored as string previously, we might need to handle it.
        # Since we use new table/model, it should be fine.
        return data

    @staticmethod
    async def update_config(user_id: int, data: NotificationConfig):
        """更新用户通知配置"""
        # Upsert
        defaults = {
            "enable_email": data.enable_email,
            "email_config": data.email_config or {},
            "enable_pushplus": data.enable_pushplus,
            "pushplus_token": data.pushplus_token,
            "enable_http": data.enable_http,
            "http_url": data.http_url
        }
        await UserNotificationConfig.update_or_create(defaults=defaults, user_id=user_id)

    @staticmethod
    async def test_notification(data: TestNotification):
        """测试通知发送"""
        if data.channel == 'email':
            host = None
            port = None
            username = None
            password = None
            nickname = None

            if data.config and isinstance(data.config, dict):
                cfg = data.config.get("email_config", {}) if isinstance(data.config.get("email_config"), dict) else {}
                host = cfg.get("host")
                port = cfg.get("port")
                username = cfg.get("username")
                password = cfg.get("password")
                nickname = data.config.get("email_nickname")

            if not all([host, port, username, password]):
                host = SystemConfig.get("email_host")
                port = SystemConfig.get("email_port")
                username = SystemConfig.get("email_username")
                password = SystemConfig.get("email_password")
                nickname = SystemConfig.get("email_nickname")
                if not all([host, port, username, password]):
                    await SystemConfig.load()
                    host = SystemConfig.get("email_host")
                    port = SystemConfig.get("email_port")
                    username = SystemConfig.get("email_username")
                    password = SystemConfig.get("email_password")
                    nickname = SystemConfig.get("email_nickname")

            if not all([host, port, username, password]):
                raise ValueError("邮箱配置不完整")
                
            to_email = data.target
            if not to_email:
                raise ValueError("请输入接收邮箱")
                
            success, msg = await send_email(
                host,
                port,
                username,
                password,
                to_email,
                "测试通知",
                "这是一条测试消息",
                nickname=str(nickname or "").strip() or None,
            )
            
        elif data.channel == 'pushplus':
            token = data.config.get('pushplus_token') if data.config else None
            if not token:
                raise ValueError("缺少 PushPlus Token")
            success, msg = await send_pushplus(token, "这是一条测试消息")
            
        elif data.channel == 'http':
            url = data.config.get('http_url') if data.config else None
            if not url:
                raise ValueError("缺少 Webhook URL")
            success, msg = await send_http(url, "这是一条测试消息")
            
        else:
            raise ValueError("不支持的通知渠道")
            
        return success, msg
