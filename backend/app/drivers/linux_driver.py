import re
import logging
import time
from typing import Dict, Any
from .base import BaseDevice

# 使用新的 logger 名称
logger = logging.getLogger("app.drivers.linux")

class LinuxServer(BaseDevice):
    """
    Linux 服务器驱动
    通过 SSH 执行 Linux 命令采集系统信息 (CPU, 内存, 磁盘等)。
    """
    def __init__(self, device_info: Dict):
        super().__init__(device_info)
        self.device_type = 'linux'
        self._next_cpu_mem_collect_at = 0.0
        self._next_disk_collect_at = 0.0

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

            logger.debug(f"Linux 服务器 {self.ip} 静态信息采集完毕: {self.static_info}")
            return self.static_info
        except Exception as e:
            logger.error(f"Linux 服务器 {self.ip} 一次性采集失败: {self._compact_exception_message(e)}")
        return {}

    async def collect_status(self) -> Dict[str, Any]:
        now = time.monotonic()
        cpu_cached = float(self.last_metrics.get("cpu_usage") or 0.0)
        mem_cached = float(self.last_metrics.get("memory_usage") or 0.0)
        disk_cached = float(self.last_metrics.get("disk_usage") or 0.0)
        result = {"cpu_usage": cpu_cached, "memory_usage": mem_cached, "disk_usage": disk_cached}
        
        try:
            if now >= float(self._next_cpu_mem_collect_at or 0.0):
                cpu = await self.get_cpu_usage()
                mem = await self.get_memory_usage()
                self.last_metrics["cpu_usage"] = float(cpu or 0.0)
                self.last_metrics["memory_usage"] = float(mem or 0.0)
                result["cpu_usage"] = float(cpu or 0.0)
                result["memory_usage"] = float(mem or 0.0)
                self._next_cpu_mem_collect_at = now + 1.0

            if now >= float(self._next_disk_collect_at or 0.0):
                disk = await self.get_disk_usage()
                self.last_metrics["disk_usage"] = float(disk or 0.0)
                result["disk_usage"] = float(disk or 0.0)
                self._next_disk_collect_at = now + 10.0
                    
        except Exception as e:
            logger.error(f"采集 Linux 服务器 {self.ip} 状态失败: {self._compact_exception_message(e)}")
            
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
            logger.warning(f"获取 CPU 使用率失败: {self._compact_exception_message(e)}")
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
            logger.warning(f"获取内存使用率失败: {self._compact_exception_message(e)}")
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
            logger.warning(f"获取磁盘使用率失败: {self._compact_exception_message(e)}")
        return 0.0
