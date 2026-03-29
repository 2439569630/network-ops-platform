import unittest
import json
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response


class TestMyLoginLogsEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_returns_items_and_meta(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        auth_endpoint.db.fetch_val = AsyncMock(return_value=5)
        auth_endpoint.db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": 10,
                    "ip": "127.0.0.1",
                    "user_agent": "ua",
                    "device": "web",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        )

        resp = await auth_endpoint.get_my_login_logs(page=2, page_size=2, token_payload={"id": 7})

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(resp.get("meta", {}).get("total"), 5)
        self.assertEqual(resp.get("meta", {}).get("page"), 2)
        self.assertEqual(resp.get("meta", {}).get("page_size"), 2)

        data = resp.get("data") or []
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get("id"), 10)

        args, _kwargs = auth_endpoint.db.fetch_all.call_args
        self.assertEqual(args[1:], (7, 2, 2))

    async def test_requires_login(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        with self.assertRaises(HTTPException) as cm:
            await auth_endpoint.get_my_login_logs(page=1, page_size=10, token_payload={})

        self.assertEqual(getattr(cm.exception, "status_code", None), 401)


class TestLoginRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_required_returns_400(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)
        response = Response()

        auth_endpoint.db.fetch_one = AsyncMock(return_value=None)

        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=object()):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=False)):
                with patch("app.api.v1.endpoints.auth._should_require_login_captcha", new=AsyncMock(return_value=True)):
                    with patch(
                        "app.api.v1.endpoints.auth._verify_login_captcha",
                        new=AsyncMock(return_value=(False, "AUTH_CAPTCHA_REQUIRED", "请完成验证码")),
                    ):
                        result = await auth_endpoint.login(
                            data=auth_endpoint.LoginForm(username="u", password="p"),
                            response=response,
                            request=request,
                        )

        self.assertEqual(getattr(result, "status_code", None), 400)
        payload = json.loads(result.body.decode("utf-8"))
        self.assertEqual(payload.get("error"), "AUTH_CAPTCHA_REQUIRED")
        self.assertEqual(payload.get("data", {}).get("captcha_required"), True)

    async def test_rate_limited_returns_429(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)
        response = Response()

        auth_endpoint.db.fetch_one = AsyncMock(return_value=None)

        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=object()):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=True)):
                result = await auth_endpoint.login(
                    data=auth_endpoint.LoginForm(username="u", password="p"),
                    response=response,
                    request=request,
                )

        self.assertEqual(getattr(result, "status_code", None), 429)
        payload = json.loads(result.body.decode("utf-8"))
        self.assertEqual(payload.get("error"), "AUTH_RATE_LIMITED")
        self.assertEqual(payload.get("data", {}).get("captcha_required"), True)

    async def test_user_not_found_records_fail(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)
        response = Response()

        auth_endpoint.db.fetch_one = AsyncMock(return_value=None)

        record = AsyncMock(return_value=None)
        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=object()):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=False)):
                with patch("app.api.v1.endpoints.auth._should_require_login_captcha", new=AsyncMock(return_value=False)):
                    with patch("app.api.v1.endpoints.auth._record_login_fail", new=record):
                        result = await auth_endpoint.login(
                            data=auth_endpoint.LoginForm(username="u", password="p"),
                            response=response,
                            request=request,
                        )

        self.assertEqual(getattr(result, "status_code", None), 401)
        self.assertGreaterEqual(record.await_count, 1)




class TestLoginChangeNotification(unittest.IsolatedAsyncioTestCase):
    def _build_request(self):
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [
                (b"user-agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        return Request(scope)

    async def test_same_ip_and_device_skips_notifications(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        user_row = {
            "id": 7,
            "username": "u",
            "password": "hashed",
            "is_approved": True,
            "email": "u@example.com",
            "is_email_notify": True,
            "is_login_email_notify": True,
        }
        prev_row = {"ip": "127.0.0.1", "device": "Windows · Chrome"}

        auth_endpoint.db.fetch_one = AsyncMock(side_effect=[user_row, prev_row])
        auth_endpoint.db.execute = AsyncMock(return_value=None)

        redis_client = AsyncMock()
        redis_client.delete = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=None)

        create_task_calls = []
        def fake_create_task(coro):
            create_task_calls.append(coro)
            coro.close()
            return None

        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=redis_client):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=False)):
                with patch("app.api.v1.endpoints.auth._should_require_login_captcha", new=AsyncMock(return_value=False)):
                    with patch("app.api.v1.endpoints.auth._verify_password_compat", return_value=True):
                        with patch("app.api.v1.endpoints.auth.RbacService.get_user_permission_codes", new=AsyncMock(return_value=[])):
                            with patch("app.api.v1.endpoints.auth.RbacService.get_user_role_codes", new=AsyncMock(return_value=[])):
                                with patch("app.api.v1.endpoints.auth._get_or_init_perm_ver", new=AsyncMock(return_value=1)):
                                    with patch("app.api.v1.endpoints.auth.bump_user_auth_version", new=AsyncMock(return_value=2)):
                                        with patch("app.api.v1.endpoints.auth.set_user_auth_session_info", new=AsyncMock(return_value=None)):
                                            with patch("app.api.v1.endpoints.auth.NotificationService._is_login_email_globally_enabled", new=AsyncMock(return_value=(True, None))) as email_enabled:
                                                with patch("app.api.v1.endpoints.auth.NotificationService.create_site_message", new=AsyncMock(return_value=None)) as create_site_message:
                                                    with patch("app.api.v1.endpoints.auth.asyncio.create_task", side_effect=fake_create_task):
                                                        result = await auth_endpoint.login(
                                                            data=auth_endpoint.LoginForm(username="u", password="p"),
                                                            response=Response(),
                                                            request=self._build_request(),
                                                        )

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(len(create_task_calls), 0)
        self.assertEqual(create_site_message.await_count, 0)
        self.assertEqual(email_enabled.await_count, 0)

    async def test_changed_ip_triggers_notifications(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        user_row = {
            "id": 7,
            "username": "u",
            "password": "hashed",
            "is_approved": True,
            "email": "u@example.com",
            "is_email_notify": True,
            "is_login_email_notify": True,
        }
        prev_row = {"ip": "10.0.0.8", "device": "Windows · Chrome"}

        auth_endpoint.db.fetch_one = AsyncMock(side_effect=[user_row, prev_row])
        auth_endpoint.db.execute = AsyncMock(return_value=None)

        redis_client = AsyncMock()
        redis_client.delete = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=None)

        create_task_calls = []
        def fake_create_task(coro):
            create_task_calls.append(coro)
            coro.close()
            return None

        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=redis_client):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=False)):
                with patch("app.api.v1.endpoints.auth._should_require_login_captcha", new=AsyncMock(return_value=False)):
                    with patch("app.api.v1.endpoints.auth._verify_password_compat", return_value=True):
                        with patch("app.api.v1.endpoints.auth.RbacService.get_user_permission_codes", new=AsyncMock(return_value=[])):
                            with patch("app.api.v1.endpoints.auth.RbacService.get_user_role_codes", new=AsyncMock(return_value=[])):
                                with patch("app.api.v1.endpoints.auth._get_or_init_perm_ver", new=AsyncMock(return_value=1)):
                                    with patch("app.api.v1.endpoints.auth.bump_user_auth_version", new=AsyncMock(return_value=2)):
                                        with patch("app.api.v1.endpoints.auth.set_user_auth_session_info", new=AsyncMock(return_value=None)):
                                            with patch("app.api.v1.endpoints.auth.NotificationService._is_login_email_globally_enabled", new=AsyncMock(return_value=(True, None))) as email_enabled:
                                                with patch("app.api.v1.endpoints.auth.NotificationService.create_site_message", new=AsyncMock(return_value=None)) as create_site_message:
                                                    with patch("app.api.v1.endpoints.auth.asyncio.create_task", side_effect=fake_create_task):
                                                        result = await auth_endpoint.login(
                                                            data=auth_endpoint.LoginForm(username="u", password="p"),
                                                            response=Response(),
                                                            request=self._build_request(),
                                                        )

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(len(create_task_calls), 1)
        self.assertEqual(create_site_message.await_count, 1)
        self.assertEqual(email_enabled.await_count, 1)

    async def test_changed_ip_skips_login_email_when_user_disabled(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        user_row = {
            "id": 7,
            "username": "u",
            "password": "hashed",
            "is_approved": True,
            "email": "u@example.com",
            "is_email_notify": True,
            "is_login_email_notify": False,
        }
        prev_row = {"ip": "10.0.0.8", "device": "Windows · Chrome"}

        auth_endpoint.db.fetch_one = AsyncMock(side_effect=[user_row, prev_row])
        auth_endpoint.db.execute = AsyncMock(return_value=None)

        redis_client = AsyncMock()
        redis_client.delete = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=None)

        create_task_calls = []

        def fake_create_task(coro):
            create_task_calls.append(coro)
            coro.close()
            return None

        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=redis_client):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=False)):
                with patch("app.api.v1.endpoints.auth._should_require_login_captcha", new=AsyncMock(return_value=False)):
                    with patch("app.api.v1.endpoints.auth._verify_password_compat", return_value=True):
                        with patch("app.api.v1.endpoints.auth.RbacService.get_user_permission_codes", new=AsyncMock(return_value=[])):
                            with patch("app.api.v1.endpoints.auth.RbacService.get_user_role_codes", new=AsyncMock(return_value=[])):
                                with patch("app.api.v1.endpoints.auth._get_or_init_perm_ver", new=AsyncMock(return_value=1)):
                                    with patch("app.api.v1.endpoints.auth.bump_user_auth_version", new=AsyncMock(return_value=2)):
                                        with patch("app.api.v1.endpoints.auth.set_user_auth_session_info", new=AsyncMock(return_value=None)):
                                            with patch("app.api.v1.endpoints.auth.NotificationService._is_login_email_globally_enabled", new=AsyncMock(return_value=(True, None))) as email_enabled:
                                                with patch("app.api.v1.endpoints.auth.NotificationService.create_site_message", new=AsyncMock(return_value=None)) as create_site_message:
                                                    with patch("app.api.v1.endpoints.auth.asyncio.create_task", side_effect=fake_create_task):
                                                        result = await auth_endpoint.login(
                                                            data=auth_endpoint.LoginForm(username="u", password="p"),
                                                            response=Response(),
                                                            request=self._build_request(),
                                                        )

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(len(create_task_calls), 0)
        self.assertEqual(create_site_message.await_count, 1)
        self.assertEqual(email_enabled.await_count, 1)

    async def test_changed_ip_skips_login_email_when_email_notifications_disabled(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        user_row = {
            "id": 7,
            "username": "u",
            "password": "hashed",
            "is_approved": True,
            "email": "u@example.com",
            "is_email_notify": False,
            "is_login_email_notify": True,
        }
        prev_row = {"ip": "10.0.0.8", "device": "Windows · Chrome"}

        auth_endpoint.db.fetch_one = AsyncMock(side_effect=[user_row, prev_row])
        auth_endpoint.db.execute = AsyncMock(return_value=None)

        redis_client = AsyncMock()
        redis_client.delete = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=None)

        create_task_calls = []

        def fake_create_task(coro):
            create_task_calls.append(coro)
            coro.close()
            return None

        with patch("app.api.v1.endpoints.auth.redis_manager.get_client", return_value=redis_client):
            with patch("app.api.v1.endpoints.auth._is_login_rate_limited", new=AsyncMock(return_value=False)):
                with patch("app.api.v1.endpoints.auth._should_require_login_captcha", new=AsyncMock(return_value=False)):
                    with patch("app.api.v1.endpoints.auth._verify_password_compat", return_value=True):
                        with patch("app.api.v1.endpoints.auth.RbacService.get_user_permission_codes", new=AsyncMock(return_value=[])):
                            with patch("app.api.v1.endpoints.auth.RbacService.get_user_role_codes", new=AsyncMock(return_value=[])):
                                with patch("app.api.v1.endpoints.auth._get_or_init_perm_ver", new=AsyncMock(return_value=1)):
                                    with patch("app.api.v1.endpoints.auth.bump_user_auth_version", new=AsyncMock(return_value=2)):
                                        with patch("app.api.v1.endpoints.auth.set_user_auth_session_info", new=AsyncMock(return_value=None)):
                                            with patch("app.api.v1.endpoints.auth.NotificationService._is_login_email_globally_enabled", new=AsyncMock(return_value=(True, None))) as email_enabled:
                                                with patch("app.api.v1.endpoints.auth.NotificationService.create_site_message", new=AsyncMock(return_value=None)) as create_site_message:
                                                    with patch("app.api.v1.endpoints.auth.asyncio.create_task", side_effect=fake_create_task):
                                                        result = await auth_endpoint.login(
                                                            data=auth_endpoint.LoginForm(username="u", password="p"),
                                                            response=Response(),
                                                            request=self._build_request(),
                                                        )

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(len(create_task_calls), 0)
        self.assertEqual(create_site_message.await_count, 1)
        self.assertEqual(email_enabled.await_count, 1)


class TestSecuritySettings(unittest.IsolatedAsyncioTestCase):
    async def test_get_security_settings_returns_two_email_switches(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        auth_endpoint.db.fetch_one = AsyncMock(
            return_value={
                "email": "u@example.com",
                "password": "hashed",
                "is_email_notify": True,
                "is_login_email_notify": False,
            }
        )

        result = await auth_endpoint.get_my_security_settings(token_payload={"id": 7})

        self.assertEqual(result.get("code"), 200)
        self.assertTrue(result.get("data", {}).get("is_email_notify"))
        self.assertFalse(result.get("data", {}).get("is_login_email_notify"))

    async def test_update_security_settings_can_update_total_email_switch_only(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        auth_endpoint.db.fetch_one = AsyncMock(
            return_value={"is_email_notify": True, "is_login_email_notify": True}
        )
        auth_endpoint.db.execute = AsyncMock(return_value=None)

        result = await auth_endpoint.update_my_security_settings(
            form=auth_endpoint.UpdateSecurityForm(is_email_notify=False),
            token_payload={"id": 7},
        )

        self.assertEqual(result.get("code"), 200)
        self.assertFalse(result.get("data", {}).get("is_email_notify"))
        self.assertTrue(result.get("data", {}).get("is_login_email_notify"))

    async def test_update_security_settings_can_update_login_switch_only(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        auth_endpoint.db.fetch_one = AsyncMock(
            return_value={"is_email_notify": True, "is_login_email_notify": False}
        )
        auth_endpoint.db.execute = AsyncMock(return_value=None)

        result = await auth_endpoint.update_my_security_settings(
            form=auth_endpoint.UpdateSecurityForm(is_login_email_notify=True),
            token_payload={"id": 7},
        )

        self.assertEqual(result.get("code"), 200)
        self.assertTrue(result.get("data", {}).get("is_email_notify"))
        self.assertTrue(result.get("data", {}).get("is_login_email_notify"))


if __name__ == "__main__":
    unittest.main()
