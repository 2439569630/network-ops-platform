import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.database import db
from app.core.system_config import SystemConfig
from app.core.redis import redis_manager
from app.utils.notification_sender import send_email, send_pushplus, send_http
from app.schemas.notification import NotificationConfig, TestNotification

logger = logging.getLogger(__name__)

class NotificationService:
    SYSTEM_ALERTS_CHANNEL = "system_alerts"
    SYSTEM_ALERTS_RECENT_KEY = "system_alerts:recent"
    SYSTEM_ALERTS_RECENT_LIMIT = 500
    SYSTEM_ALERTS_RECENT_TTL_SECONDS = 7 * 24 * 60 * 60
    SITE_MESSAGES_CHANNEL_GLOBAL = "site_messages:global"
    SITE_MESSAGES_CHANNEL_USER_PREFIX = "site_messages:user:"
    _site_message_tables_ready = False

    @staticmethod
    async def get_history(can_view_all: bool, user_id: int) -> List[dict]:
        """获取通知历史"""
        if can_view_all:
            sql = """
                SELECT dn.id, dn.device_id, d.device_name, dn.level, dn.message, dn.created_at 
                FROM device_notifications dn
                LEFT JOIN network_devices d ON dn.device_id = d.id
                ORDER BY dn.created_at DESC
                LIMIT 100
            """
            rows = await db.fetch_all(sql)
        else:
            # TODO: Filter by user's devices
            rows = []
        return [dict(row) for row in rows]

    @staticmethod
    async def _ensure_site_message_tables():
        if NotificationService._site_message_tables_ready:
            return

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS site_messages (
                id BIGSERIAL PRIMARY KEY,
                sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                sender_name TEXT,
                source TEXT NOT NULL DEFAULT '系统',
                level VARCHAR(20) NOT NULL DEFAULT 'info',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                is_global BOOLEAN NOT NULL DEFAULT FALSE,
                target_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_messages_target_created ON site_messages(target_user_id, created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_messages_global_created ON site_messages(is_global, created_at DESC)"
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS site_message_reads (
                message_id BIGINT NOT NULL REFERENCES site_messages(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (message_id, user_id)
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_message_reads_user_readat ON site_message_reads(user_id, read_at DESC)"
        )
        NotificationService._site_message_tables_ready = True

    @staticmethod
    async def list_site_messages(
        *,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[dict]:
        await NotificationService._ensure_site_message_tables()

        lim = max(1, min(int(limit or 100), 200))
        off = max(0, int(offset or 0))
        where_unread = "AND r.read_at IS NULL" if unread_only else ""

        sql = f"""
            SELECT
                m.id,
                m.sender_id,
                m.sender_name,
                m.source,
                m.level,
                m.title,
                m.content,
                m.is_global,
                m.target_user_id,
                m.created_at,
                (r.read_at IS NOT NULL) AS is_read,
                r.read_at
            FROM site_messages m
            LEFT JOIN site_message_reads r
                ON r.message_id = m.id AND r.user_id = $1
            WHERE (m.is_global = TRUE OR m.target_user_id = $1)
            {where_unread}
            ORDER BY m.created_at DESC
            LIMIT $2 OFFSET $3
        """
        rows = await db.fetch_all(sql, int(user_id), lim, off)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def create_site_message(
        *,
        sender_id: Optional[int],
        sender_name: Optional[str],
        title: str,
        content: str,
        level: str = "info",
        source: str = "管理员",
        target_user_id: Optional[int] = None,
        is_global: bool = True,
    ) -> dict:
        await NotificationService._ensure_site_message_tables()

        t = str(title or "").strip()
        c = str(content or "").strip()
        if not t:
            raise ValueError("标题不能为空")
        if not c:
            raise ValueError("内容不能为空")

        lv = str(level or "info").strip().lower()
        if lv not in {"info", "warning", "error", "success"}:
            lv = "info"

        tg = int(target_user_id) if target_user_id is not None else None
        global_flag = bool(is_global) if tg is None else False
        if tg is None and not global_flag:
            raise ValueError("请选择全站或指定用户")

        row = await db.fetch_one(
            """
            INSERT INTO site_messages (
                sender_id, sender_name, source, level, title, content, is_global, target_user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, sender_id, sender_name, source, level, title, content, is_global, target_user_id, created_at
            """,
            sender_id,
            sender_name,
            str(source or "系统"),
            lv,
            t,
            c,
            global_flag,
            tg,
        )
        result = dict(row) if row else {}

        try:
            await NotificationService.publish_site_message_changed(target_user_id=tg, is_global=global_flag)
        except Exception as e:
            logger.error(f"发布站内消息实时事件失败: {e}")

        return result

    @staticmethod
    async def mark_site_message_read(*, user_id: int, message_id: int) -> bool:
        await NotificationService._ensure_site_message_tables()
        await db.execute(
            """
            INSERT INTO site_message_reads (message_id, user_id, read_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (message_id, user_id) DO UPDATE SET read_at = EXCLUDED.read_at
            """,
            int(message_id),
            int(user_id),
        )
        try:
            await NotificationService.publish_site_message_changed(target_user_id=int(user_id), is_global=False)
        except Exception as e:
            logger.error(f"发布站内消息已读事件失败: {e}")
        return True

    @staticmethod
    async def mark_site_message_unread(*, user_id: int, message_id: int) -> bool:
        await NotificationService._ensure_site_message_tables()
        await db.execute(
            "DELETE FROM site_message_reads WHERE message_id = $1 AND user_id = $2",
            int(message_id),
            int(user_id),
        )
        try:
            await NotificationService.publish_site_message_changed(target_user_id=int(user_id), is_global=False)
        except Exception as e:
            logger.error(f"发布站内消息未读事件失败: {e}")
        return True

    @staticmethod
    def get_site_messages_user_channel(user_id: int) -> str:
        return f"{NotificationService.SITE_MESSAGES_CHANNEL_USER_PREFIX}{int(user_id)}"

    @staticmethod
    async def publish_site_message_changed(*, target_user_id: Optional[int], is_global: bool) -> None:
        redis_client = redis_manager.get_client()
        payload = {
            "type": "site_message_changed",
            "target_user_id": int(target_user_id) if target_user_id is not None else None,
            "is_global": bool(is_global),
        }
        payload_str = json.dumps(payload, ensure_ascii=False)
        if is_global:
            await redis_client.publish(NotificationService.SITE_MESSAGES_CHANNEL_GLOBAL, payload_str)
        elif target_user_id is not None:
            await redis_client.publish(NotificationService.get_site_messages_user_channel(int(target_user_id)), payload_str)

    @staticmethod
    async def get_site_message_unread_count(*, user_id: int) -> int:
        await NotificationService._ensure_site_message_tables()
        row = await db.fetch_one(
            """
            SELECT COUNT(1) AS cnt
            FROM site_messages m
            LEFT JOIN site_message_reads r
                ON r.message_id = m.id AND r.user_id = $1
            WHERE (m.is_global = TRUE OR m.target_user_id = $1)
              AND r.read_at IS NULL
            """,
            int(user_id),
        )
        try:
            return int(row["cnt"]) if row and row.get("cnt") is not None else 0
        except Exception:
            return 0

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
            "time": time_iso or datetime.now().isoformat(),
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
                await db.execute(
                    "INSERT INTO device_notifications (device_id, level, message, created_at) VALUES ($1, $2, $3, NOW())",
                    device_id,
                    level,
                    description,
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
            row = await db.fetch_one(
                "SELECT device_name, ipv4 FROM network_devices WHERE id = $1",
                device_id,
            )
            if row:
                device_name = row["device_name"]
                ipv4 = str(row["ipv4"]) if row["ipv4"] else None
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
                row = await db.fetch_one(
                    "SELECT device_name, ipv4 FROM network_devices WHERE id = $1",
                    device_id,
                )
                if row:
                    device_name = row["device_name"]
                    ipv4 = str(row["ipv4"]) if row["ipv4"] else None
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
        sql = "SELECT * FROM user_notification_config WHERE user_id = $1"
        config = await db.fetch_one(sql, user_id)
        
        if not config:
            return {
                "enable_email": False,
                "use_global_email": False,
                "email_config": {},
                "enable_pushplus": False,
                "pushplus_token": "",
                "enable_http": False,
                "http_url": ""
            }
            
        data = dict(config)
        if isinstance(data.get('email_config'), str):
             try:
                 data['email_config'] = json.loads(data['email_config'])
             except:
                 data['email_config'] = {}
        return data

    @staticmethod
    async def update_config(user_id: int, data: NotificationConfig):
        """更新用户通知配置"""
        sql = """
            INSERT INTO user_notification_config (
                user_id, enable_email, use_global_email, email_config, 
                enable_pushplus, pushplus_token, enable_http, http_url
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id) DO UPDATE SET
                enable_email = EXCLUDED.enable_email,
                use_global_email = EXCLUDED.use_global_email,
                email_config = EXCLUDED.email_config,
                enable_pushplus = EXCLUDED.enable_pushplus,
                pushplus_token = EXCLUDED.pushplus_token,
                enable_http = EXCLUDED.enable_http,
                http_url = EXCLUDED.http_url
        """
        
        await db.execute(
            sql, 
            user_id, 
            data.enable_email, 
            data.use_global_email, 
            json.dumps(data.email_config) if data.email_config else '{}',
            data.enable_pushplus,
            data.pushplus_token,
            data.enable_http,
            data.http_url
        )

    @staticmethod
    async def test_notification(data: TestNotification):
        """测试通知发送"""
        if data.channel == 'email':
            email_config = {}
            if data.config:
                email_config = data.config
            else:
                raise ValueError("请提供配置信息")
            
            if email_config.get('use_global_email'):
                host = SystemConfig.get('email_host')
                port = SystemConfig.get('email_port')
                username = SystemConfig.get('email_username')
                password = SystemConfig.get('email_password')
            else:
                cfg = email_config.get('email_config', {})
                host = cfg.get('host')
                port = cfg.get('port')
                username = cfg.get('username')
                password = cfg.get('password')
            
            if not all([host, port, username, password]):
                raise ValueError("邮箱配置不完整")
                
            to_email = data.target
            if not to_email:
                raise ValueError("请输入接收邮箱")
                
            success, msg = await send_email(host, port, username, password, to_email, "测试通知", "这是一条测试消息")
            
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
