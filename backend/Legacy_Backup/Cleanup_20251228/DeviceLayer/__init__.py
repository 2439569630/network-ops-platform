from .base_device import BaseDevice
from .huawei_device import HuaweiDevice
from .linux_server import LinuxServer

def create_device(device_info: dict) -> BaseDevice:
    """工厂方法：根据设备类型创建对应的设备对象"""
    device_type = device_info.get('device_type', 'server')
    
    if device_type in ['路由器', '交换机']:
        # 假设目前只支持华为网络设备
        return HuaweiDevice(device_info)
    elif device_type == '服务器':
        return LinuxServer(device_info)
    else:
        # 默认回退到 Linux Server 或 BaseDevice
        return LinuxServer(device_info)
