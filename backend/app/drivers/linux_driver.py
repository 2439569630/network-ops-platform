import re
import logging
from typing import Dict, Any
from .base import BaseDevice

# 使用新的 logger 名称
logger = logging.getLogger("app.drivers.linux")

class LinuxServer(BaseDevice):
    def __init__(self, device_info: Dict):
        super().__init__(device_info)
        self.device_type = 'linux'
        # Linux 服务器全量采集间隔 60 秒
        self.interval = 60
        # 在线监测间隔 5 秒 (加快检测速度)
        self.monitor_interval = 5

    async def collect_once(self) -> Dict[str, Any]:
        """执行一次性采集"""
        try:
            # 获取 OS 信息
            os_info = await self.send_command("cat /etc/os-release")
            # PRETTY_NAME="Ubuntu 20.04.2 LTS"
            if os_info:
                match = re.search(r'PRETTY_NAME="([^"]+)"', os_info)
                if match:
                    self.static_info['os_version'] = match.group(1)
                    # 尝试将 OS 名称作为厂商/型号的替代显示，避免 Unknown
                    if 'Ubuntu' in match.group(1):
                        self.static_info['vendor'] = 'Canonical'
                        self.static_info['model'] = 'Ubuntu Server'
                    elif 'CentOS' in match.group(1):
                        self.static_info['vendor'] = 'RedHat'
                        self.static_info['model'] = 'CentOS Server'
                    else:
                         self.static_info['vendor'] = 'Linux'
                         self.static_info['model'] = 'Generic Server'
            
            # 获取 Kernel 版本
            kernel = await self.send_command("uname -r")
            if kernel:
                self.static_info['kernel'] = kernel.strip()
                if 'vendor' not in self.static_info:
                     self.static_info['vendor'] = 'Linux'
                     self.static_info['model'] = 'Generic Server'

            logger.info(f"Linux 服务器 {self.ip} 静态信息采集完毕: {self.static_info}")
            return self.static_info
        except Exception as e:
            logger.error(f"Linux 服务器 {self.ip} 一次性采集失败: {e}")
        return {}

    async def collect_status(self) -> Dict[str, Any]:
        result = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'disk_usage': 0.0
        }
        
        try:
            result['cpu_usage'] = await self.get_cpu_usage()
            result['memory_usage'] = await self.get_memory_usage()
            result['disk_usage'] = await self.get_disk_usage()
                    
        except Exception as e:
            logger.error(f"采集 Linux 服务器 {self.ip} 状态失败: {e}")
            
        return result

    async def get_cpu_usage(self) -> float:
        try:
            # CPU
            # top -bn1 往往返回的是自启动以来的平均值，或者第一次采样不准确
            # 使用 top -bn2 取第二次采样结果，更能反映当前瞬时 CPU 使用率
            cmd = "top -bn2 | grep 'Cpu(s)' | tail -1"
            cpu_out = await self.send_command(cmd)
            
            # Output example: 
            # %Cpu(s):  0.0 us,  0.5 sy,  0.0 ni, 99.5 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
            match = re.search(r'(\d+\.\d+)\s+id', cpu_out)
            if match:
                return round(100 - float(match.group(1)), 2)
        except Exception as e:
            logger.warning(f"获取 CPU 使用率失败: {e}")
        return 0.0

    async def get_memory_usage(self) -> float:
        try:
            # Memory
            mem_out = await self.send_command("free -m | grep Mem:")
            parts = mem_out.split()
            if len(parts) >= 3:
                total = float(parts[1])
                used = float(parts[2])
                if total > 0:
                    return round((used / total) * 100, 2)
        except Exception as e:
            logger.warning(f"获取内存使用率失败: {e}")
        return 0.0

    async def get_disk_usage(self) -> float:
        try:
            # Disk
            disk_out = await self.send_command("df -h / | tail -n 1")
            parts = disk_out.split()
            if len(parts) >= 5:
                use_pct = parts[4].replace('%', '')
                if use_pct.isdigit():
                    return float(use_pct)
        except Exception as e:
            logger.warning(f"获取磁盘使用率失败: {e}")
        return 0.0
