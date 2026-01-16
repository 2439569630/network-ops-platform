
from typing import Optional
from pydantic import BaseModel

class DeviceBase(BaseModel):
    device_name: str
    user_name: str
    type: str
    ipv4: str
    ipv6: Optional[str] = None
    mac: Optional[str] = None
    location: Optional[str] = None
    ssh_port: int = 22

class DeviceCreate(DeviceBase):
    password: str

class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    type: Optional[str] = None
    location: Optional[str] = None
    ssh_port: Optional[int] = None
    # ...其他可更新字段

class DeviceResponse(DeviceBase):
    id: int
    status: str = '待加载'
    cpu_usage: str = '0%'
    memory_usage: str = '0%'
    disk_usage: str = '0%'
    uptime: str = '未知'
    os_version: str = 'Unknown'
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    ops_admin_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class DeviceTest(BaseModel):
    ipv4: str
    ssh_port: int = 22
    user_name: str
    password: str
    type: str

class DeviceDelete(BaseModel):
    id: Optional[int] = None
    ip: Optional[str] = None


class DeviceConfigUpdate(BaseModel):
    device_id: int
    interval: Optional[float] = None
    monitor_interval: Optional[float] = None
    offline_fail_threshold: Optional[int] = None
    recovery_success_threshold: Optional[int] = None
    connect_timeout: Optional[float] = None
    auth_timeout: Optional[float] = None
    banner_timeout: Optional[float] = None
    global_delay_factor: Optional[float] = None
    connect_max_retries: Optional[int] = None
    connect_retry_delay_seconds: Optional[float] = None
    offline_retry_delay_seconds: Optional[float] = None
