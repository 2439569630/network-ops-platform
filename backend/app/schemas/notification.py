from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime

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

class NotificationHistory(BaseModel):
    id: int
    device_id: Optional[int]
    device_name: Optional[str]
    level: Optional[str]
    message: str
    created_at: datetime

class SiteMessageCreate(BaseModel):
    title: str
    content: str
    level: Optional[str] = "info"
    target_user_id: Optional[int] = None
    is_global: Optional[bool] = True
    source: Optional[str] = "管理员"

class SiteMessageRow(BaseModel):
    id: int
    sender_id: Optional[int]
    sender_name: Optional[str]
    source: Optional[str]
    level: Optional[str]
    title: str
    content: str
    is_global: bool
    target_user_id: Optional[int]
    created_at: datetime
    is_read: bool
    read_at: Optional[datetime] = None
