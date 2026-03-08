from pprint import pprint
import unittest
import os

from app.drivers.netmiko_driver import (
    HuaweiDevice,
    parse_huawei_display_esn,
    parse_huawei_display_health,
    parse_huawei_display_version,
    parse_huawei_uptime_from_display_version,
)
from app.drivers.models.huawei_runtime import HuaweiInterfaceRuntime


# 单元测试：解析华为设备 CLI 输出
class TestHuaweiParsers(unittest.TestCase):
    def test_parse_display_version_basic(self) -> None:
        output = (
            "Huawei Versatile Routing Platform Software\n"
            "VRP (R) software, Version 5.130 (AR2200 V200R003C00)\n"
            "Copyright (C) 2011-2012 HUAWEI TECH CO., LTD\n"
            "Huawei AR2220 Router uptime is 0 week, 0 day, 0 hour, 38 minutes\n"
            "BKP 0 version information:\n"
            "1. PCB      Version  : AR01BAK2A VER.NC\n"
            "2. If Supporting PoE : No\n"
            "3. Board    Type     : AR2220\n"
            "4. MPU Slot Quantity : 1\n"
            "5. LPU Slot Quantity : 6\n"
            "\n"
            "MPU 0(Master) : uptime is 0 week, 0 day, 0 hour, 38 minutes\n"
        )
        data = parse_huawei_display_version(output)
        self.assertEqual(data.get("vendor"), "Huawei")
        self.assertEqual(data.get("model"), "AR2220")
        self.assertEqual(data.get("product"), "AR2200")
        self.assertEqual(data.get("vrp_version"), "5.130")
        self.assertEqual(data.get("vrp_release"), "V200R003C00")
        self.assertEqual(data.get("os_version"), "V200R003C00")
        self.assertEqual(data.get("version"), "V200R003C00")
        self.assertTrue(str(data.get("version_raw") or "").startswith("Huawei Versatile"))

    def test_parse_display_version_empty(self) -> None:
        self.assertEqual(parse_huawei_display_version(""), {})
        self.assertEqual(parse_huawei_display_version(None), {})  # type: ignore[arg-type]

    def test_parse_display_esn_basic(self) -> None:
        output = "ESN of slot 0: ABC1234567\n"
        data = parse_huawei_display_esn(output)
        self.assertEqual(data, {"serial_number": "ABC1234567"})

    def test_parse_display_esn_not_found(self) -> None:
        self.assertEqual(parse_huawei_display_esn("something else"), {})
        self.assertEqual(parse_huawei_display_esn(""), {})

    def test_parse_uptime_from_display_version(self) -> None:
        output = (
            "MPU 0(Master) : uptime is 9 week, 9 days\n"
            "Huawei AR2220 Router uptime is 1 week, 2 days\n"
        )
        self.assertEqual(parse_huawei_uptime_from_display_version(output), "1 week, 2 days")
        self.assertIsNone(parse_huawei_uptime_from_display_version(""))

    def test_parse_display_health_formats(self) -> None:
        output_1 = (
            "System CPU Usage Information\n"
            "0 20 %\n"
            "System Memory Usage Information\n"
            "0 1 2 30%\n"
            "System Disk Usage Information\n"
            "40%\n"
            "TEMP NORMAL 0 0 55\n"
        )
        data_1 = parse_huawei_display_health(output_1)
        self.assertEqual(data_1.get("cpu_usage"), 20.0)
        self.assertEqual(data_1.get("memory_usage"), 30.0)
        self.assertEqual(data_1.get("disk_usage"), 40.0)
        self.assertEqual(data_1.get("temperature"), 55.0)

        output_2 = (
            "System CPU Usage Information\n"
            "0 15 %\n"
            "Memory Using Percentage Is: 22%\n"
        )
        data_2 = parse_huawei_display_health(output_2)
        self.assertEqual(data_2.get("cpu_usage"), 15.0)
        self.assertEqual(data_2.get("memory_usage"), 22.0)

    def test_parse_display_health_empty(self) -> None:
        self.assertEqual(parse_huawei_display_health(""), {})

    def test_parse_display_interface_brief_variants(self) -> None:
        output = (
            "PHY: Physical\n"
            "*down: administratively down\n"
            "(l): loopback\n"
            "(s): spoofing\n"
            "InUti/OutUti: input utility/output utility\n"
            "Interface                   PHY   Protocol  InUti OutUti   inErrors  outErrors\n"
            "Cellular0/0/0               down  down         0%     0%          0          0 \n"
            "GigabitEthernet0/0/0        up    up        0.01%  0.01%          0          0 \n"
            "GigabitEthernet0/0/1        *down down         0%     0%          0          0 \n"
            "GigabitEthernet0/0/5        up    down      0.01%     0%          0          0 \n"
            "NULL0                       up    up(s)        0%     0%          0          0 \n"
            "Vlanif1                     up    up           --     --          0          0 \n"
        )
        items = HuaweiInterfaceRuntime.from_output(output)
        by_name = {i.name: i for i in items}

        self.assertIn("GigabitEthernet0/0/0", by_name)
        self.assertIn("GigabitEthernet0/0/5", by_name)
        self.assertIn("Vlanif1", by_name)
        self.assertIn("NULL0", by_name)

        self.assertEqual(by_name["GigabitEthernet0/0/0"].in_uti, "0.01%")
        self.assertEqual(by_name["Vlanif1"].in_uti, "--")
        self.assertEqual(by_name["NULL0"].protocol_state, "up(s)")


# 集成测试用配置（通过环境变量或手动修改）
HUAWEI_HOST = str(os.getenv("HUAWEI_HOST", "") or "").strip()
HUAWEI_USERNAME = str(os.getenv("HUAWEI_USERNAME", "") or "").strip()
HUAWEI_PASSWORD = str(os.getenv("HUAWEI_PASSWORD", "") or "").strip()
HUAWEI_PORT = int(os.getenv("HUAWEI_PORT", "22") or 22)


def _huawei_configured() -> bool:
    """检查是否已填写华为设备连接信息"""
    return bool(str(HUAWEI_HOST or "").strip() and str(HUAWEI_USERNAME or "").strip() and str(HUAWEI_PASSWORD or "").strip())


def _build_huawei_device() -> HuaweiDevice:
    """根据全局变量构建设备对象并应用测试配置"""
    try:
        port = int(HUAWEI_PORT)
    except Exception:
        port = 22
    device_info = {
        "id": 0,
        "ipv4": str(HUAWEI_HOST or "").strip(),
        "device_type": "huawei",
        "user_name": str(HUAWEI_USERNAME or "").strip(),
        "password": str(HUAWEI_PASSWORD or "").strip(),
        "ssh_port": port,
    }
    device = HuaweiDevice(device_info)
    device.apply_config(
        device.config.with_overrides(
            connect_timeout=10.0,
            auth_timeout=10.0,
            banner_timeout=30.0,
            connect_max_retries=1,
            connect_retry_delay_seconds=0.5,
            offline_retry_delay_seconds=5.0,
        )
    )
    return device


# 异步集成测试
class TestHuaweiIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        """每条用例结束后尝试断开设备连接"""
        device = getattr(self, "device", None)
        if device:
            try:
                await device.disconnect()
            except Exception:
                pass

    async def test_connect_and_collect(self) -> None:
        """测试连接并采集静态与状态数据"""
        if not _huawei_configured():
            raise unittest.SkipTest("未配置 HUAWEI_HOST/HUAWEI_USERNAME/HUAWEI_PASSWORD")

        self.device = _build_huawei_device()

        ok = await self.device.connect()
        self.assertTrue(ok)
        self.assertTrue(bool(self.device.connected))

        static_info = await self.device.collect_once()
        if isinstance(static_info, dict):
            normalized = static_info
        else:
            to_dict = getattr(static_info, "to_dict", None)
            self.assertTrue(callable(to_dict))
            normalized = to_dict()
        self.assertIsInstance(normalized, dict)

        status = await self.device.collect_status()
        self.assertIsInstance(status, dict)
        self.assertIn("cpu_usage", status)
        self.assertIn("memory_usage", status)
        self.assertIn("disk_usage", status)

    async def test_custom(self) -> None:
        """占位用例：可在此添加自定义调试逻辑"""
        if not _huawei_configured():
            raise unittest.SkipTest("未配置 HUAWEI_HOST/HUAWEI_USERNAME/HUAWEI_PASSWORD")

        self.device = _build_huawei_device()
        await self.device.connect()
        raw = await self.device.fetch_display_version()
        print("\n===== raw: display version =====\n")
        print(raw)
        parsed = parse_huawei_display_version(raw)
        print("\n===== parsed: display version =====\n")
        pprint(parsed, sort_dicts=True)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("vendor"), "Huawei")


if __name__ == "__main__":
    unittest.main()
