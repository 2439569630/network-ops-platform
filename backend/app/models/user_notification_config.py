from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class UserNotificationConfig:
    user_id: int
    enable_email: Optional[bool] = None
    email_config: Optional[Dict[str, Any]] = None
    enable_http: Optional[bool] = None
    http_url: Optional[str] = None
