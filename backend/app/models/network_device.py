from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class NetworkDevice:
    id: int
    device_name: str
    ipv4: str
    device_type: str
    user_name: str
    password: str
    created_by: str
    ipv6: Optional[str] = None
    mac: Optional[str] = None
    location: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    ssh_port: Optional[int] = None
    snmp_community: Optional[str] = None
    snmp_version: Optional[int] = None
    telnet_port: Optional[int] = None
    is_active: Optional[bool] = None
    online_status: Optional[bool] = None
    last_seen: Optional[datetime] = None
    last_backup: Optional[datetime] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
