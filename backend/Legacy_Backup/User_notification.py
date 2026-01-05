import logging
import json
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from DataBase import PostgreSQL
from auth.security import verify_token, RoleChecker, verify_token_ws
from pydantic import BaseModel
from typing import Optional, Dict
from Utils.notification_sender import send_email, send_pushplus, send_http
from Config.sys_config import SystemConfig
from DataBase.Redis import RedisManager
import asyncio

router = APIRouter(prefix="/user/notification", tags=["Notification Center"])
logger = logging.getLogger(__name__)

@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await websocket.accept()
    
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return

    redis_manager = RedisManager()
    redis_client = await redis_manager.get_redis()
    pubsub = redis_client.pubsub()
    
    # WebSocket 发送锁
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        try:
            async with ws_lock:
                await websocket.send_json(data)
        except:
            pass # 连接可能已关闭

    # 监听任务
    async def redis_listener():
        try:
            # 订阅 Trap 告警频道
            await pubsub.subscribe("system_alerts")
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'message':
                    try:
                        # 解析消息
                        data_str = message['data']
                        if isinstance(data_str, bytes):
                            data_str = data_str.decode('utf-8')
                        
                        alert_data = json.loads(data_str)
                        # 推送给前端
                        await send_safe_json(alert_data)
                    except Exception as e:
                        logger.error(f"Alert WS parse error: {e}")
                
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Alert WS listener error: {e}")

    listener_task = asyncio.create_task(redis_listener())

    try:
        # 保持连接
        while True:
            # 接收前端消息（如心跳或指令），这里暂时只需保持连接
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        await pubsub.close()

class NotificationConfig(BaseModel):
    enable_email: bool
    use_global_email: bool
    email_config: Optional[Dict] = None
    enable_pushplus: bool
    pushplus_token: Optional[str] = None
    enable_http: bool
    http_url: Optional[str] = None

class TestNotification(BaseModel):
    channel: str # email, pushplus, http
    config: Optional[Dict] = None # 如果不传则尝试使用已保存配置
    target: Optional[str] = None # 测试目标（如接收邮箱）

@router.get("/history")
async def get_history(user = Depends(verify_token)):
    """获取通知历史 (仅获取有权限的设备的通知)"""
    # 简单的权限控制：管理员/运维看所有，普通用户看无（或者分配给他的设备，这里暂且简化为 level <= 1 看所有， level 2 看空或者后续关联设备）
    user_role = int(user.get('permission_level', 2))
    
    if user_role <= 1:
        sql = """
            SELECT dn.id, dn.device_id, d.device_name, dn.level, dn.message, dn.created_at 
            FROM device_notifications dn
            LEFT JOIN network_devices d ON dn.device_id = d.id
            ORDER BY dn.created_at DESC
            LIMIT 100
        """
        rows = await PostgreSQL.execute(sql, fetch=True)
    else:
        # TODO: 关联普通用户和设备
        rows = []
        
    return {"code": 200, "data": rows}

@router.get("/config")
async def get_config(user = Depends(verify_token)):
    """获取用户通知配置"""
    user_id = user.get('id')
    sql = "SELECT * FROM user_notification_config WHERE user_id = $1"
    config = await PostgreSQL.execute(sql, user_id, fetch_row=True)
    
    if not config:
        # 默认配置
        return {"code": 200, "data": {
            "enable_email": False,
            "use_global_email": False,
            "email_config": {},
            "enable_pushplus": False,
            "pushplus_token": "",
            "enable_http": False,
            "http_url": ""
        }}
        
    # 处理 JSONB
    data = dict(config)
    if isinstance(data.get('email_config'), str):
         data['email_config'] = json.loads(data['email_config'])
    
    return {"code": 200, "data": data}

@router.post("/config")
async def update_config(data: NotificationConfig, user = Depends(verify_token)):
    """更新用户通知配置"""
    user_id = user.get('id')
    user_role = int(user.get('permission_level', 2))
    
    # 检查权限：如果开启 global email，必须是管理员或运维 (level <= 1)
    # 或者拥有特殊权限。这里按 prompt 要求 "使用全局的需要邮箱权限"
    # 假设 role 0 和 1 有此权限
    if data.use_global_email and user_role > 1:
        return {"code": 403, "message": "无权使用全局邮箱配置"}

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
    
    await PostgreSQL.execute(
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
    
    return {"code": 200, "message": "配置保存成功"}

@router.post("/test")
async def test_notification(data: TestNotification, user = Depends(verify_token)):
    """测试通知发送"""
    try:
        if data.channel == 'email':
            email_config = {}
            # 优先使用传入的配置（测试未保存的配置）
            if data.config:
                email_config = data.config
            else:
                # 否则加载用户配置或全局配置
                # 这里简化：仅支持测试传入的配置，或者前端负责组装好完整的配置传过来
                return {"code": 400, "message": "请提供配置信息"}
            
            # 检查是否使用全局配置
            if email_config.get('use_global_email'):
                # 获取全局配置
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
                return {"code": 400, "message": "邮箱配置不完整"}
                
            to_email = data.target
            if not to_email:
                return {"code": 400, "message": "请输入接收邮箱"}
                
            success, msg = await send_email(host, port, username, password, to_email, "测试通知", "这是一条测试消息")
            
        elif data.channel == 'pushplus':
            token = data.config.get('pushplus_token') if data.config else None
            if not token:
                return {"code": 400, "message": "缺少 PushPlus Token"}
            
            success, msg = await send_pushplus(token, "这是一条测试消息")
            
        elif data.channel == 'http':
            url = data.config.get('http_url') if data.config else None
            if not url:
                return {"code": 400, "message": "缺少 Webhook URL"}
                
            success, msg = await send_http(url, "这是一条测试消息")
            
        else:
            return {"code": 400, "message": "不支持的通知渠道"}
            
        if success:
            return {"code": 200, "message": "发送成功"}
        else:
            return {"code": 500, "message": f"发送失败: {msg}"}
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return {"code": 500, "message": str(e)}
