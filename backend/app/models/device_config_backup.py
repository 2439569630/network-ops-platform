from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class DeviceConfigBackup:
    id: int
    device_id: int
    config_content: str
    created_by: str
    config_type: Optional[str] = None
    backup_method: Optional[str] = None
    checksum: Optional[str] = None
    created_at: Optional[datetime] = None
