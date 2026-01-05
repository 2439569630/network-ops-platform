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
