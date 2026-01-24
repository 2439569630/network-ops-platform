import re
import logging
import time
import asyncio
from dataclasses import replace
from typing import Dict, Any, Optional, List
from .base import BaseDevice
from .models.huawei_runtime import (
    HuaweiDisplayVersionRuntime,
    HuaweiInterfaceRuntime,
    HuaweiRouteRuntime,
    HuaweiVlanRuntime,
    HuaweiInterfaceDetailRuntime,
)

# 使用新的 logger 名称
logger = logging.getLogger("app.drivers.netmiko")


def parse_huawei_display_version(output: str) -> Dict[str, Any]:
    # 解析 display version：统一通过运行时数据结构提取关键信息
    # 兼容返回 dict，便于与现有业务逻辑对接（静态信息入库/展示）
    runtime = HuaweiDisplayVersionRuntime.from_output(str(output or ""))
    return runtime.to_dict()


def parse_huawei_display_esn(output: str) -> Dict[str, Any]:
    # 解析 display esn：提取序列号（设备标识）
    text = str(output or "")
    if not text.strip():
        return {}
    sn_match = re.search(r"ESN of slot \d+:\s+(\w+)", text)
    if not sn_match:
        return {}
    return {"serial_number": sn_match.group(1)}


def parse_huawei_uptime_from_display_version(output: str) -> Optional[str]:
    # 从 display version 输出中提取运行时间
    # 优先匹配 Router uptime，避免命中 MPU uptime 等子模块信息
    text = str(output or "")
    if not text.strip():
        return None
    match = re.search(r"Router uptime is\s+(.+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match_2 = re.search(r"uptime is\s+(.+)", text, flags=re.IGNORECASE)
    if match_2:
        return match_2.group(1).strip()
    return None


def parse_huawei_display_health(output: str) -> Dict[str, Any]:
    # 解析 display health：提取 CPU/内存/磁盘/温度等运行指标
    text = str(output or "")
    if not text.strip():
        return {}

    data: Dict[str, Any] = {}

    cpu_match = re.search(r"System CPU Usage Information[\s\S]*?0\s+(\d+)\s*%", text)
    if cpu_match:
        data["cpu_usage"] = float(cpu_match.group(1))

    mem_match = re.search(
        r"System Memory Usage Information[\s\S]*?0\s+\d+\s+\d+\s+(\d+)%",
        text,
    )
    if mem_match:
        data["memory_usage"] = float(mem_match.group(1))

    mem_match_2 = re.search(r"Memory Using Percentage Is:\s+(\d+)%", text)
    if mem_match_2:
        data["memory_usage"] = float(mem_match_2.group(1))

    disk_match = re.search(r"System Disk Usage Information[\s\S]*?(\d+\.?\d*)%", text)
    if disk_match:
        data["disk_usage"] = float(disk_match.group(1))

    temp_match = re.search(r"TEMP\s+NORMAL\s+\d+\s+\d+\s+(\d+)", text)
    if temp_match:
        data["temperature"] = float(temp_match.group(1))

    return data


class HuaweiDevice(BaseDevice):
    """
    华为网络设备驱动
    通过 SSH (Netmiko) 执行 display 命令采集设备信息。
    """
    def __init__(self, device_info: Dict):
        super().__init__(device_info)
        # 设备类型：Netmiko 驱动使用
        self.device_type = 'huawei'
        self.next_interfaces_sync_at = 0.0
        self.next_routes_sync_at = 0.0
        self.next_vlans_sync_at = 0.0
        self.next_interfaces_slot0_sync_at = 0.0
        self._next_health_collect_at = 0.0
        self._next_version_collect_at = 0.0

    async def fetch_display_version(self) -> str:
        # 获取设备版本与运行时间等静态信息（原始回显）
        return await self.send_command("display version")

    async def fetch_display_esn(self) -> str:
        # 获取设备序列号（原始回显）
        return await self.send_command("display esn")

    async def fetch_display_health(self) -> str:
        # 获取设备健康/资源信息（原始回显）
        return await self.send_command("display health")

    async def get_static_serial_info(self) -> Dict[str, Any]:
        # 静态信息：序列号（结构化）
        esn = await self.fetch_display_esn()
        return parse_huawei_display_esn(esn)

    async def collect_once(self) -> Any:
        # 静态信息采集钩子：在首次成功建立连接后调用一次，用于补齐厂商/型号/版本/序列号等
        # 在当前监控流程中通常只会在设备监控循环启动时触发一次；如需“每次重连后刷新”，需由上层再次调用
        try:
            version_out = await self.fetch_display_version()
            runtime = HuaweiDisplayVersionRuntime.from_output(version_out)

            serial_info = await self.get_static_serial_info()
            serial_number = serial_info.get("serial_number")
            if serial_number:
                runtime = replace(runtime, serial_number=str(serial_number))

            self.static_info = runtime
            data = runtime.to_dict()
            
            # 优化日志显示：排除冗长的原始回显
            log_data = data.copy()
            log_data.pop("version_raw", None)
            logger.debug(f"华为设备 {self.ip} 静态信息采集完毕: {log_data}")
            return runtime
        except Exception as e:
            logger.error(f"华为设备 {self.ip} 一次性采集失败: {self._compact_exception_message(e)}")
            return {}
    
    

    async def collect_status(self) -> Dict[str, Any]:
        now = time.monotonic()
        result = {
            "cpu_usage": float(self.last_metrics.get("cpu_usage") or 0.0),
            "memory_usage": float(self.last_metrics.get("memory_usage") or 0.0),
            "disk_usage": float(self.last_metrics.get("disk_usage") or 0.0),
            "temperature": float(self.last_metrics.get("temperature") or 0.0),
            "uptime": str(self.last_metrics.get("uptime") or "") or None,
        }

        try:
            if now >= float(self._next_health_collect_at or 0.0):
                health_out = await self.fetch_display_health()
                if health_out:
                    parsed = parse_huawei_display_health(health_out)
                    for k, v in parsed.items():
                        self.last_metrics[k] = v
                        result[k] = v
                    if "CPU usage monitor is disabled" in str(health_out):
                        logger.warning(f"华为设备 {self.ip} CPU 监控未开启")
                self._next_health_collect_at = now + 1.0

            if now >= float(self._next_version_collect_at or 0.0):
                version_out = await self.fetch_display_version()
                uptime = parse_huawei_uptime_from_display_version(version_out)
                if uptime:
                    self.last_metrics["uptime"] = str(uptime)
                    result["uptime"] = str(uptime)
                self._next_version_collect_at = now + 60.0
                    
        except Exception as e:
            logger.error(f"采集华为设备 {self.ip} 状态失败: {self._compact_exception_message(e)}")

        return result

    def parse_health(self, output: str) -> Dict[str, Any]:
        # 兼容保留：业务若直接传入输出文本进行解析，可复用该方法
        return parse_huawei_display_health(output)

    async def get_uptime(self) -> Optional[str]:
        # 兼容保留：按需获取 uptime（会触发一次 display version）
        try:
            output = await self.fetch_display_version()
            return parse_huawei_uptime_from_display_version(output)
        except Exception as e:
            logger.warning(f"获取运行时间失败: {self._compact_exception_message(e)}")
            return None

    async def get_health(self) -> str:
        """获取健康状态（温度、电压等）"""
        # 注意：不同型号命令可能不同，AR系列通常支持 display health
        return await self.fetch_display_health()

    async def fetch_display_interface_brief(self) -> str:
        """获取接口简要信息"""
        return await self.send_command("display interface brief")

    async def fetch_display_interface_slot(self, slot_id: int = 0) -> str:
        return await self.send_command(f"display interface slot {int(slot_id)}")

    async def fetch_display_ip_routing_table(self) -> str:
        """获取路由表信息"""
        return await self.send_command("display ip routing-table")

    async def fetch_display_vlan(self) -> str:
        """获取 VLAN 信息"""
        return await self.send_command("display vlan")

    async def collect_interfaces(self) -> Optional[List[Dict[str, Any]]]:
        """采集并解析接口列表"""
        try:
            output = await self.fetch_display_interface_brief()
            items = HuaweiInterfaceRuntime.from_output(output)
            payload = [item.to_dict() for item in items]
            self.last_interfaces = payload
            self.last_interfaces_updated = time.time()
            return payload
        except Exception as e:
            logger.error(f"采集华为设备 {self.ip} 接口失败: {self._compact_exception_message(e)}")
            return None

    async def collect_interfaces_detailed(self, slot_id: int = 0) -> Optional[List[Dict[str, Any]]]:
        try:
            output = await self.fetch_display_interface_slot(int(slot_id))
            items = HuaweiInterfaceDetailRuntime.from_output(output)
            payload = [item.to_dict() for item in items]
            sid = int(slot_id)
            self.last_interfaces_detailed_by_slot[sid] = payload
            self.last_interfaces_detailed_updated_by_slot[sid] = time.time()
            return payload
        except Exception as e:
            logger.error(f"采集华为设备 {self.ip} 插槽{slot_id}接口详情失败: {self._compact_exception_message(e)}")
            return None

    async def collect_routes(self) -> Optional[List[Dict[str, Any]]]:
        """采集并解析路由表"""
        try:
            output = await self.fetch_display_ip_routing_table()
            items = HuaweiRouteRuntime.from_output(output)
            return [item.to_dict() for item in items]
        except Exception as e:
            logger.error(f"采集华为设备 {self.ip} 路由表失败: {self._compact_exception_message(e)}")
            return None

    async def collect_vlans(self) -> Optional[List[Dict[str, Any]]]:
        """采集并解析 VLAN 列表"""
        try:
            output = await self.fetch_display_vlan()
            items = HuaweiVlanRuntime.from_output(output)
            return [item.to_dict() for item in items]
        except Exception as e:
            logger.error(f"采集华为设备 {self.ip} VLAN 失败: {self._compact_exception_message(e)}")
            return None
