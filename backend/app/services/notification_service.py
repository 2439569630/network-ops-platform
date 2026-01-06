import json
from typing import List, Optional, Dict
from app.core.database import db
from app.core.system_config import SystemConfig
from app.utils.notification_sender import send_email, send_pushplus, send_http
from app.schemas.notification import NotificationConfig, TestNotification

class NotificationService:
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
