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


if __name__ == "__main__":
    unittest.main()
