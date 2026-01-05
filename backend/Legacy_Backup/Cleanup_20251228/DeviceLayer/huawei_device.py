import re
import logging
from typing import Dict, Any
from .base_device import BaseDevice
import logging
from typing import Dict, Any

# 使用专门的 DeviceLayer logger
logger = logging.getLogger("DeviceLayer.HuaweiDevice")

class HuaweiDevice(BaseDevice):
    def __init__(self, device_info: Dict):
        super().__init__(device_info)
        # Netmiko 的 device_type
        # 华为 VRP 通常使用 'huawei'
        self.device_type = 'huawei'
        # 华为设备全量采集间隔 60 秒
        self.interval = 60
        # 在线监测间隔 5 秒 (加快检测速度)
        self.monitor_interval = 5

    async def collect_once(self) -> Dict[str, Any]:
        """执行一次性采集"""
        try:
            # 获取版本信息
            version = await self.send_command("display version")
            # 简单解析第一行或特定信息
            # Huawei Versatile Routing Platform Software
            # VRP (R) software, Version 5.130 (AR2200 V200R003C00)
            if version:
                self.static_info['version_raw'] = version
                self.static_info['vendor'] = 'Huawei'
                
                # Version
                match = re.search(r'Version\s+([\w.]+)', version)
                if match:
                    self.static_info['os_version'] = match.group(1)
                    self.static_info['version'] = match.group(1)
                
                # Model
                # Huawei AR2220 Router uptime...
                # Huawei AR151-S2 Router uptime...
                model_match = re.search(r'Huawei\s+(AR[\w-]+)\s+Router', version)
                if model_match:
                    self.static_info['model'] = model_match.group(1)
            
            # 获取序列号
            esn = await self.send_command("display esn")
            if esn:
                # ESN of slot 0: 210235525010B9000006
                sn_match = re.search(r'ESN of slot \d+:\s+(\w+)', esn)
                if sn_match:
                    self.static_info['serial_number'] = sn_match.group(1)

            logger.info(f"华为设备 {self.ip} 静态信息采集完毕: {self.static_info}")
            return self.static_info
        except Exception as e:
            logger.error(f"华为设备 {self.ip} 一次性采集失败: {e}")
        return {}
    
    

    async def collect_status(self) -> Dict[str, Any]:
        """采集华为设备状态"""
        result = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'disk_usage': 0.0,
            'temperature': 0, # 温度
            'uptime': None
        }
        
        try:
            # 1. 使用 display health 获取大部分信息 (CPU, Memory, Disk, Temp)
            health_out = await self.send_command("display health")
            if health_out:
                health_data = self.parse_health(health_out)
                result.update(health_data)

            # 2. Uptime 仍需从 display version 获取
            result['uptime'] = await self.get_uptime()
            
        except Exception as e:
            logger.error(f"采集华为设备 {self.ip} 状态失败: {e}")
            
        return result

    def parse_health(self, output: str) -> Dict[str, Any]:
        """解析 display health 输出"""
        data = {}
        
        # CPU Parsing
        # 1. Table format (e.g. AR151)
        # System CPU Usage Information:
        #   SlotID  CPU Usage  Upper Limit
        #   0       8%         80%
        cpu_match = re.search(r'System CPU Usage Information[\s\S]*?0\s+(\d+)\s*%', output)
        if cpu_match:
            data['cpu_usage'] = float(cpu_match.group(1))
            
        # 2. Check for disabled monitor
        if "CPU usage monitor is disabled" in output:
            logger.warning(f"华为设备 {self.ip} CPU 监控未开启")
            # 保持默认 0.0 或设置为特定状态

        # Memory Parsing
        # 1. Table format (e.g. AR151)
        # SlotID  Total Memory(MB)  Used Memory(MB)  Used Percentage  Upper Limit
        # 0       335               153              45%
        mem_match = re.search(r'System Memory Usage Information[\s\S]*?0\s+\d+\s+\d+\s+(\d+)%', output)
        if mem_match:
            data['memory_usage'] = float(mem_match.group(1))
            
        # 2. Text format (e.g. AR2220)
        # Memory Using Percentage Is: 80%
        mem_match_2 = re.search(r'Memory Using Percentage Is:\s+(\d+)%', output)
        if mem_match_2:
            data['memory_usage'] = float(mem_match_2.group(1))

        # Disk Parsing
        # 1. Table format
        # System Disk Usage Information:
        #   SlotID  Device ... Used Percentage
        #   0       flash: ... 76.98%
        disk_match = re.search(r'System Disk Usage Information[\s\S]*?(\d+\.?\d*)%', output)
        if disk_match:
            data['disk_usage'] = float(disk_match.group(1))

        # Temperature Parsing
        # Slot   Card   Sensor No.   SensorName            Status  Upper  Lower  Temp(C)
        # 0     -     1           AR2220 TEMP      NORMAL  73     0      0 
        temp_match = re.search(r'TEMP\s+NORMAL\s+\d+\s+\d+\s+(\d+)', output)
        if temp_match:
            data['temperature'] = float(temp_match.group(1))
            
        return data

    async def get_uptime(self) -> str:
        """获取运行时间"""
        try:
            cmd = "display version"
            output = await self.send_command(cmd)
            # Output: Huawei AR2220 Router uptime is 0 week, 0 day, 0 hour, 41 minutes
            match = re.search(r'uptime is (.+)', output)
            if match:
                return match.group(1).strip()
        except Exception as e:
            logger.warning(f"获取运行时间失败: {e}")
        return None

    async def get_health(self) -> str:
        """获取健康状态（温度、电压等）"""
        # 注意：不同型号命令可能不同，AR系列通常支持 display health
        return await self.send_command("display health")
