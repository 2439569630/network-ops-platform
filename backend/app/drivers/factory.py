
from .base import BaseDevice
from .netmiko_driver import HuaweiDevice
from .linux_driver import LinuxServer

def create_device(device_info: dict) -> BaseDevice:
    """工厂方法：根据设备类型创建对应的设备对象"""
    device_type = device_info.get('device_type', 'server')
    
    if device_type in ['路由器', '交换机', 'huawei']:
        return HuaweiDevice(device_info)
    elif device_type in ['服务器', 'linux']:
        return LinuxServer(device_info)
    else:
        # 默认回退到 Linux Server
        return LinuxServer(device_info)
