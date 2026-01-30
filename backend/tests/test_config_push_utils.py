import unittest

from app.services.config_push_service import normalize_command_list, summarize_commands
from app.workers.config_push.worker import _pick_netmiko_device_type


class TestConfigPushCommandParsing(unittest.TestCase):
    def test_normalize_command_list_merges_sources(self):
        cmds = normalize_command_list([" a ", "", None, "b"], "\n# comment\n  c  \n\n")
        self.assertEqual(cmds, ["a", "b", "c"])

    def test_summarize_commands_truncates(self):
        cmds = ["x" * 50] * 10
        s = summarize_commands(cmds, max_len=60)
        self.assertTrue(len(s) <= 60)
        self.assertTrue(s.endswith("..."))


class TestNetmikoDeviceTypePick(unittest.TestCase):
    def test_pick_huawei_for_chinese_router(self):
        self.assertEqual(_pick_netmiko_device_type("路由器"), "huawei")

    def test_pick_linux_for_server(self):
        self.assertEqual(_pick_netmiko_device_type("服务器"), "linux")
