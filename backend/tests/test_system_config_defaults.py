import unittest
from unittest.mock import AsyncMock


class TestSystemConfigListDefaults(unittest.IsolatedAsyncioTestCase):
    async def test_list_config_ensures_email_keys(self):
        from app.api.v1.endpoints import system as system_endpoint

        system_endpoint._ensure_default_configs_exist = AsyncMock(return_value=None)
        system_endpoint.db.fetch_all = AsyncMock(return_value=[])

        res = await system_endpoint.list_config(user={"id": 1})
        self.assertEqual(res.get("code"), 200)

        args, _kwargs = system_endpoint._ensure_default_configs_exist.call_args
        ensured_keys = set(args[0])
        expected = {
            "email_enabled",
            "login_email_enabled",
            "email_host",
            "email_port",
            "email_username",
            "email_password",
            "email_nickname",
        }
        self.assertTrue(expected.issubset(ensured_keys))
