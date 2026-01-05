
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
    location: Optional[str] = None
    # ...其他可更新字段

class DeviceResponse(DeviceBase):
    id: int
    status: str = '待加载'
    cpu_usage: str = '0%'
    memory_usage: str = '0%'
    disk_usage: str = '0%'
    uptime: str = '未知'
    os_version: str = 'Unknown'
    
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
