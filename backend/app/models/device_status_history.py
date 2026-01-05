from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from decimal import Decimal

@dataclass
class DeviceStatusHistory:
    id: int
    device_id: int
    cpu_usage: Optional[Decimal] = None
    memory_usage: Optional[Decimal] = None
    temperature: Optional[Decimal] = None
    uptime: Optional[int] = None
    interface_errors: Optional[int] = None
    collected_at: Optional[datetime] = None
    disk_usage: Optional[Decimal] = None
