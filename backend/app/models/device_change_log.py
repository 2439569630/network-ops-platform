from dataclasses import dataclass
from typing import Optional, Any, Dict, List
from datetime import datetime

@dataclass
class DeviceChangeLog:
    id: int
    device_id: int
    change_type: str
    change_description: str
    changed_by: str
    changed_at: Optional[datetime] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
