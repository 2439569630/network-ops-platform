
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import get_disabled_permission_codes_cached
from app.core.system_config import SystemConfig
from app.utils.notification_sender import send_email, send_pushplus, send_http
from app.schemas.notification import NotificationConfig, TestNotification

# ORM Imports
from app.models.orm.notification import DeviceNotification, SiteMessage, SiteMessageRead
from app.models.orm.device import NetworkDevice
from app.models.orm.location import LocationNodeDevice, LocationNodeRole, LocationNodeUser
from app.models.orm.rbac import UserRole
from app.models.orm.user import User
from app.models.orm.alert import AlertSubscription
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
    async def _is_email_globally_enabled() -> Tuple[bool, Optional[str]]:
        try:
            disabled = await get_disabled_permission_codes_cached()
        except Exception:
            disabled = []
        disabled_set = {str(x).strip() for x in (disabled or []) if str(x).strip()}
        if "sys:notify:email" in disabled_set:
            return False, "permission_disabled"

        raw = SystemConfig.get("email_enabled")
        s = str(raw or "").strip().lower()
        if s in {"0", "false", "no", "off"}:
            return False, "config_disabled"
        return True, None

    @staticmethod
    def _parse_user_id(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            v = int(s)
        except Exception:
            return None
        return v if v > 0 else None

    @staticmethod
    async def _notify_device_creator_site_message(
        *,
        dev: NetworkDevice,
        title: str,
        content: str,
        source: str,
    ) -> None:
        user_id = NotificationService._parse_user_id(getattr(dev, "created_by", None))
        if user_id is None:
            return
        await NotificationService.create_site_message(
            sender_id=None,
            sender_name=None,
            source=source,
            title=title,
            content=content,
            target_user_id=user_id,
            is_global=False,
        )

    @staticmethod
    async def _get_location_recipient_user_ids(*, device_id: int) -> set[int]:
        node = await LocationNodeDevice.filter(device_id=int(device_id)).first()
        if not node:
            return set()

        node_id = int(node.node_id)
        direct_user_ids = await LocationNodeUser.filter(node_id=node_id).values_list("user_id", flat=True)
        role_ids = await LocationNodeRole.filter(node_id=node_id).values_list("role_id", flat=True)
        role_user_ids: List[int] = []
        if role_ids:
            role_user_ids = await UserRole.filter(role_id__in=list(role_ids)).values_list("user_id", flat=True)

        result: set[int] = set()
        for uid in list(direct_user_ids or []) + list(role_user_ids or []):
            try:
                v = int(uid)
            except Exception:
                continue
            if v > 0:
                result.add(v)
        return result

    @staticmethod
    async def _notify_site_message_to_users(
        *,
        user_ids: set[int],
        title: str,
        content: str,
        source: str,
    ) -> None:
        if not user_ids:
            return
        for uid in sorted(user_ids):
            await NotificationService.create_site_message(
                sender_id=None,
                sender_name=None,
                source=source,
                title=title,
                content=content,
                target_user_id=int(uid),
                is_global=False,
            )

    @staticmethod
    async def _get_device_location_node_id(*, device_id: int) -> Optional[int]:
        node = await LocationNodeDevice.filter(device_id=int(device_id)).first()
        if not node:
            return None
        try:
            v = int(node.node_id)
        except Exception:
            return None
        return v if v > 0 else None

    @staticmethod
    def _severity_matches(subscription_severities: Any, severity: str) -> bool:
        sev = str(severity or "").strip().lower()
        if not sev:
            return True
        if subscription_severities is None:
            return True
        try:
            allowed = {str(x).strip().lower() for x in (subscription_severities or []) if str(x).strip()}
        except Exception:
            return True
        return True if not allowed else sev in allowed

    @staticmethod
    async def _get_subscription_channel_recipients(
        *,
        device_id: int,
        location_node_id: Optional[int],
        rule_id: Optional[int],
        severity: str,
    ) -> Dict[str, set[int]]:
        channel_users: Dict[str, set[int]] = {"site": set(), "email": set()}
        subs: List[AlertSubscription] = []
        subs.extend(await AlertSubscription.filter(scope_type="device", scope_id=int(device_id), is_enabled=True).all())
        if location_node_id is not None:
            subs.extend(await AlertSubscription.filter(scope_type="location", scope_id=int(location_node_id), is_enabled=True).all())
        if rule_id is not None:
            subs.extend(await AlertSubscription.filter(scope_type="rule", scope_id=int(rule_id), is_enabled=True).all())

        for s in subs:
            if not NotificationService._severity_matches(getattr(s, "severities", None), severity):
                continue
            try:
                uid = int(getattr(s, "subscriber_user_id", 0))
            except Exception:
                continue
            if uid <= 0:
                continue
            ch = getattr(s, "channels", None)
            try:
                channels = {str(x).strip().lower() for x in (ch or []) if str(x).strip()}
            except Exception:
                channels = set()
            if "site" in channels:
                channel_users["site"].add(uid)
            if "email" in channels:
                channel_users["email"].add(uid)

        return channel_users

    @staticmethod
    async def _send_alert_emails(*, user_ids: set[int], subject: str, content: str) -> Dict[str, Any]:
        if not user_ids:
            return {"sent": 0, "skipped": 0, "errors": 0}

        enabled, reason = await NotificationService._is_email_globally_enabled()
        if not enabled:
            logger.warning(f"跳过告警邮件发送: reason={reason}; recipients={len(user_ids)}")
            return {"sent": 0, "skipped": len(user_ids), "errors": 0, "reason": reason or "global_disabled"}

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
            missing: list[str] = []
            if not host:
                missing.append("email_host")
            if not port:
                missing.append("email_port")
            if not username:
                missing.append("email_username")
            if not password:
                missing.append("email_password")
            logger.warning(f"跳过告警邮件发送: SMTP 配置不完整; missing={missing}; recipients={len(user_ids)}")
            return {"sent": 0, "skipped": len(user_ids), "errors": 0, "reason": "config_missing"}

        users = await User.filter(id__in=list(user_ids)).all()
        user_map = {int(u.id): u for u in users}

        sem = asyncio.Semaphore(int(NotificationService.SITE_MESSAGE_EMAIL_CONCURRENCY))
        stats: Dict[str, Any] = {
            "sent": 0,
            "skipped": 0,
            "errors": 0,
            "skipped_no_email": 0,
            "skipped_user_disabled": 0,
        }

        async def _send_one(uid: int):
            u = user_map.get(int(uid))
            if not u or not getattr(u, "email", None):
                stats["skipped"] += 1
                stats["skipped_no_email"] += 1
                return
            if not bool(getattr(u, "is_email_notify", False)):
                stats["skipped"] += 1
                stats["skipped_user_disabled"] += 1
                return
            async with sem:
                ok, msg = await send_email(
                    host,
                    port,
                    username,
                    password,
                    str(u.email),
                    subject,
                    content,
                    nickname=str(nickname or "运维系统").strip() or None,
                )
            if ok:
                stats["sent"] += 1
            else:
                stats["errors"] += 1
                logger.error(f"告警邮件发送失败: user_id={uid}; host={host}; port={port}; msg={msg}")

        await asyncio.gather(*[_send_one(uid) for uid in sorted(user_ids)])
        if stats.get("sent", 0) == 0 and stats.get("errors", 0) == 0:
            logger.warning(
                "告警邮件未发送: 所有收件人都被过滤; "
                f"recipients={len(user_ids)}; skipped_no_email={stats.get('skipped_no_email')}; "
                f"skipped_user_disabled={stats.get('skipped_user_disabled')}"
            )
        return stats

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
                d_name = device_map.get(n.device_id, "")
                result.append({
                    "id": n.id,
                    "device_id": n.device_id,
                    "device_name": d_name,
                    "level": n.level,
                    "message": n.message,
                    "created_at": n.created_at,
                    "title": d_name or "系统通知",
                    "content": n.message
                })
            return result
        else:
            # 1. 查找用户创建的设备
            # 注意: created_by 是字符串类型
            user_devices = await NetworkDevice.filter(created_by=str(user_id)).all()
            if not user_devices:
                return []
            
            user_device_ids = [d.id for d in user_devices]
            
            # 2. 查找这些设备的通知
            notifications = await DeviceNotification.filter(
                device_id__in=user_device_ids
            ).order_by("-created_at").limit(100)
            
            # 3. 组装结果
            device_map = {d.id: d.device_name for d in user_devices}
            
            result = []
            for n in notifications:
                d_name = device_map.get(n.device_id, "")
                result.append({
                    "id": n.id,
                    "device_id": n.device_id,
                    "device_name": d_name,
                    "level": n.level,
                    "message": n.message,
                    "created_at": n.created_at,
                    "title": d_name or "系统通知",
                    "content": n.message
                })
            return result

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

        sender_ids: set[int] = set()
        for m in messages:
            if m.sender_id is None:
                continue
            try:
                sid = int(m.sender_id)
            except Exception:
                continue
            if sid > 0:
                sender_ids.add(sid)

        sender_avatar_map: Dict[int, Optional[str]] = {}
        if sender_ids:
            sender_rows = await User.filter(id__in=list(sender_ids)).values("id", "avatar_url")
            sender_avatar_map = {int(r["id"]): r.get("avatar_url") for r in sender_rows if r.get("id") is not None}
        
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
            
            sender_avatar_url = None
            if m.sender_id is not None:
                try:
                    sender_avatar_url = sender_avatar_map.get(int(m.sender_id))
                except Exception:
                    sender_avatar_url = None

            result.append({
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": m.sender_name,
                "sender_avatar_url": sender_avatar_url,
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
        """
        获取站内信详情
        """
        m = await SiteMessage.filter(id=message_id).filter(Q(is_global=True) | Q(target_user_id=user_id)).first()
        if not m:
            return None
            
        read_entry = await SiteMessageRead.filter(user_id=user_id, message_id=message_id).first()

        sender_avatar_url = None
        if m.sender_id is not None:
            try:
                sid = int(m.sender_id)
            except Exception:
                sid = None
            if sid and sid > 0:
                sender_avatar_url = await User.filter(id=sid).values_list("avatar_url", flat=True).first()
        
        return {
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "sender_avatar_url": sender_avatar_url,
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
        """
        创建站内信
        """
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

        sender_avatar_url = None
        if sender_id is not None:
            try:
                sid = int(sender_id)
            except Exception:
                sid = None
            if sid and sid > 0:
                sender_avatar_url = await User.filter(id=sid).values_list("avatar_url", flat=True).first()
        
        # Result dict
        result = {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender_name,
            "sender_avatar_url": sender_avatar_url,
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
        """
        标记站内信为已读
        """
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
        """
        标记站内信为未读
        """
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
    async def mark_all_site_messages_read(*, user_id: int) -> int:
        """
        标记所有站内信为已读
        """
        # 1. Get all relevant message IDs
        all_ids = await SiteMessage.filter(
            Q(is_global=True) | Q(target_user_id=user_id)
        ).values_list('id', flat=True)
        
        if not all_ids:
            return 0
            
        # 2. Get already read message IDs
        read_ids = await SiteMessageRead.filter(user_id=user_id).values_list('message_id', flat=True)
        
        # 3. Determine unread
        unread_ids = set(all_ids) - set(read_ids)
        if not unread_ids:
            return 0
            
        # 4. Bulk create
        now = datetime.now(timezone.utc)
        to_create = [
            SiteMessageRead(user_id=user_id, message_id=mid, read_at=now)
            for mid in unread_ids
        ]
        await SiteMessageRead.bulk_create(to_create)
        
        # 5. Publish event (optional, or just reuse single read event? No, too many.
        # Ideally client should reload unread count.
        # We can publish a special event type "site_message_read_all" if needed, 
        # or rely on the client refreshing after the API call returns.)
        
        return len(unread_ids)

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
        """
        获取未读站内信数量
        """
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
                )
            except Exception as e:
                logger.error(f"写入通知历史失败: {e}; payload_time={payload.get('time')}")

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
        dev = None
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

        payload = await NotificationService.notify(
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
        try:
            enabled, global_reason = await NotificationService._is_email_globally_enabled()
            location_node_id = await NotificationService._get_device_location_node_id(device_id=device_id)
            subs = await NotificationService._get_subscription_channel_recipients(
                device_id=device_id,
                location_node_id=location_node_id,
                rule_id=None,
                severity="critical",
            )
            recipients: set[int] = set()
            if dev is not None:
                creator_id = NotificationService._parse_user_id(getattr(dev, "created_by", None))
                if creator_id is not None:
                    recipients.add(creator_id)
            recipients |= await NotificationService._get_location_recipient_user_ids(device_id=device_id)
            recipients |= subs.get("site", set())
            await NotificationService._notify_site_message_to_users(
                user_ids=recipients,
                title=f"设备离线：{display_name}",
                content=message,
                source="设备告警",
            )
            email_user_ids = subs.get("email", set())
            if not email_user_ids:
                logger.warning(
                    "跳过设备离线邮件发送: 没有邮箱订阅者; "
                    f"device_id={device_id}; email_global_enabled={enabled}; email_reason={global_reason}; "
                    f"site_recipients={len(recipients)}"
                )
            else:
                await NotificationService._send_alert_emails(
                    user_ids=email_user_ids,
                    subject=f"【设备离线】{display_name} ({display_ip})",
                    content=f"{message}\n\n时间: {payload.get('time')}",
                )
        except Exception as e:
            logger.error(f"发送设备离线通知失败: device_id={device_id}; err={e}")

        return payload

    @staticmethod
    async def notify_device_alert(
        device_id: int,
        message: str,
        severity: str = "warning",
        rule_id: Optional[int] = None,
        subscription_severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送设备告警通知
        """
        device_name = None
        ipv4 = None
        dev = None
        try:
            dev = await NetworkDevice.filter(id=device_id).first()
            if dev:
                device_name = dev.device_name
                ipv4 = str(dev.ipv4) if dev.ipv4 else None
        except Exception as e:
            logger.error(f"获取设备信息失败: {e}")

        display_name = device_name or f"Device {device_id}"
        display_ip = ipv4 or "-"

        level_map = {
            "info": "info",
            "warning": "warning",
            "critical": "error"
        }
        level = level_map.get(severity, "warning")

        payload = await NotificationService.notify(
            level=level,
            source=display_name,
            type="device_alert",
            description=message,
            device_id=device_id,
            device_name=display_name,
            ipv4=display_ip,
            save_history=True,
            publish_realtime=True,
            cache_realtime=True,
        )
        try:
            notify_sev = str(severity or "").strip().lower()
            match_sev = str(subscription_severity or severity or "").strip().lower()
            sev_cn = {"critical": "严重", "warning": "警告", "info": "提示"}.get(notify_sev, notify_sev or "告警")
            location_node_id = await NotificationService._get_device_location_node_id(device_id=device_id)
            subs = await NotificationService._get_subscription_channel_recipients(
                device_id=device_id,
                location_node_id=location_node_id,
                rule_id=rule_id,
                severity=match_sev,
            )

            recipients: set[int] = set()
            if dev is not None:
                creator_id = NotificationService._parse_user_id(getattr(dev, "created_by", None))
                if creator_id is not None:
                    recipients.add(creator_id)
            recipients |= await NotificationService._get_location_recipient_user_ids(device_id=device_id)
            recipients |= subs.get("site", set())
        except Exception as e:
            logger.error(f"设备告警通知后处理失败: device_id={device_id}; rule_id={rule_id}; severity={severity}; err={e}")
            return payload

        try:
            await NotificationService._notify_site_message_to_users(
                user_ids=recipients,
                title=f"{sev_cn}告警：{display_name}",
                content=message,
                source="设备告警",
            )
        except Exception as e:
            logger.error(f"发送设备告警站内信失败: device_id={device_id}; rule_id={rule_id}; severity={sev}; err={e}")

        try:
            email_user_ids = subs.get("email", set())
            if not email_user_ids:
                logger.warning(
                    "跳过设备告警邮件发送: 没有邮箱订阅者; "
                    f"device_id={device_id}; rule_id={rule_id}; severity={notify_sev}; match_severity={match_sev}; "
                    f"site_recipients={len(recipients)}"
                )
            else:
                await NotificationService._send_alert_emails(
                    user_ids=email_user_ids,
                    subject=f"【{sev_cn}告警】{display_name} ({display_ip})",
                    content=f"{message}\n\n设备: {display_name} ({display_ip})\n级别: {sev_cn}\n时间: {payload.get('time')}",
                )
        except Exception as e:
            logger.error(f"发送设备告警邮件失败: device_id={device_id}; rule_id={rule_id}; severity={notify_sev}; match_severity={match_sev}; err={e}")

        return payload

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
        """
        发送工单提交通知
        """
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
    async def notify_repair_order_assigned(
        *,
        order_id: int,
        title: str,
        assignee_id: int,
        priority: str,
        reason: str = "工单指派",
    ) -> Dict[str, Any]:
        """
        发送工单指派通知 (站内信 + 邮件)
        """
        # 1. 发送站内信
        site_msg_content = f"【{reason}】工单 #{order_id} 已指派给您。\n标题: {title}\n优先级: {priority}"
        await NotificationService.create_site_message(
            sender_id=None, # System
            sender_name="系统",
            title=f"新工单 ({reason})",
            content=site_msg_content,
            source="工单系统",
            target_user_id=assignee_id,
            is_global=False
        )
        
        # 2. 发送邮件
        try:
            # 获取用户信息
            user = await User.filter(id=assignee_id).first()
            # Remove is_email_notify check as requested
            if not user or not user.email:
                return {"site_message": "sent", "email": "skipped_no_email"}
            
            # Check global email switch
            email_enabled = SystemConfig.get("email_enabled")
            if email_enabled != "1" and email_enabled != "true":
                return {"site_message": "sent", "email": "skipped_global_disabled"}
            
            # 获取系统配置
            host = SystemConfig.get("email_host")
            port = SystemConfig.get("email_port")
            username = SystemConfig.get("email_username")
            password = SystemConfig.get("email_password")
            nickname = SystemConfig.get("email_nickname")
            
            # 检查配置完整性
            if not all([host, port, username, password]):
                # 尝试重新加载配置
                await SystemConfig.load()
                host = SystemConfig.get("email_host")
                port = SystemConfig.get("email_port")
                username = SystemConfig.get("email_username")
                password = SystemConfig.get("email_password")
                nickname = SystemConfig.get("email_nickname")
                
            if not all([host, port, username, password]):
                logger.warning("系统邮件配置不完整，跳过发送工单邮件")
                return {"site_message": "sent", "email": "config_missing"}

            # 发送邮件
            email_subject = f"【{reason}】#{order_id} - {title}"
            email_content = f"""
尊敬的 {user.nickname or user.username}:

您有一个新的报修工单待处理。

工单编号: #{order_id}
指派类型: {reason}
标题: {title}
优先级: {priority}

请登录系统查看详情并及时处理。
"""
            success, msg = await send_email(
                host, port, username, password, 
                user.email, email_subject, email_content, 
                nickname=str(nickname or "运维系统").strip()
            )
            
            if not success:
                logger.error(f"工单邮件发送失败: {msg}")
                return {"site_message": "sent", "email": "failed", "error": msg}
                
            return {"site_message": "sent", "email": "sent"}
            
        except Exception as e:
            logger.error(f"工单邮件通知流程异常: {e}")
            return {"site_message": "sent", "email": "error", "error": str(e)}

    @staticmethod
    async def get_config(user_id: int) -> dict:
        """获取用户通知配置"""
        return {
            "enable_email": False,
            "email_config": {},
            "enable_pushplus": False,
            "pushplus_token": "",
            "enable_http": False,
            "http_url": ""
        }

    @staticmethod
    async def update_config(user_id: int, data: NotificationConfig):
        """更新用户通知配置"""
        # 功能已禁用，不做任何操作
        pass

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
