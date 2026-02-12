from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime

class NotificationConfig(BaseModel):
    """通知配置模型"""
    enable_email: bool
    email_config: Optional[Dict] = None
    enable_http: bool
    http_url: Optional[str] = None

class TestNotification(BaseModel):
    """通知测试模型"""
    channel: str # email, http
    config: Optional[Dict] = None # 如果不传则尝试使用已保存配置
    target: Optional[str] = None # 测试目标（如接收邮箱）

class NotificationHistory(BaseModel):
    """通知历史模型"""
    id: int
    device_id: Optional[int]
    device_name: Optional[str]
    level: Optional[str]
    message: str
    created_at: datetime

class SiteMessageCreate(BaseModel):
    """站内信创建模型"""
    title: str
    content: str
    target_user_id: Optional[int] = None
    is_global: Optional[bool] = True
    source: Optional[str] = "管理员"

class SiteMessageRow(BaseModel):
    """站内信响应模型"""
    id: int
    sender_id: Optional[int]
    sender_name: Optional[str]
    source: Optional[str]
    title: str
    content: str
    is_global: bool
    target_user_id: Optional[int]
    created_at: datetime
    is_read: bool
    read_at: Optional[datetime] = None


class SystemAlertPayload(BaseModel):
    time: str
    level: str
    source: str
    type: str
    description: str
    device_id: Optional[int] = None
    device_name: Optional[str] = None
    ipv4: Optional[str] = None


class SystemAlertRecentResponse(BaseModel):
    items: List[SystemAlertPayload]
