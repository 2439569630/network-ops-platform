from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class UserNotificationConfig:
    user_id: int
    enable_email: Optional[bool] = None
    use_global_email: Optional[bool] = None
    email_config: Optional[Dict[str, Any]] = None
    enable_pushplus: Optional[bool] = None
    pushplus_token: Optional[str] = None
    enable_http: Optional[bool] = None
    http_url: Optional[str] = None
