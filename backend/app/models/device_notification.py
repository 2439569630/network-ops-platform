from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class DeviceNotification:
    id: int
    device_id: Optional[int] = None
    level: Optional[str] = None
    message: Optional[str] = None
    created_at: Optional[datetime] = None
