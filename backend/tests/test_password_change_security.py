import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request


class TestPasswordChangeSecurity(unittest.IsolatedAsyncioTestCase):
    async def test_request_password_change_code_uses_service(self):
        from app.api.v1.endpoints import users as users_endpoint

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/users/profile/password/code/request",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch(
            "app.api.v1.endpoints.users.UserService.request_password_change_email_code",
            new=AsyncMock(return_value={"cooldown_seconds": 60, "expires_in_minutes": 10}),
        ) as request_code:
            resp = await users_endpoint.request_password_change_code(
                request=request,
                current_user={"id": 7},
            )

        self.assertEqual(resp.get("code"), 200)
        request_code.assert_awaited_once_with(user_id=7, request_ip="127.0.0.1")

    async def test_update_profile_password_change_sends_security_notification(self):
        from app.api.v1.endpoints import users as users_endpoint
        from app.schemas.user import UserUpdate

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/users/profile/update",
            "headers": [(b"user-agent", b"Mozilla/5.0 Chrome/123.0")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch(
            "app.api.v1.endpoints.users.UserService.update_profile",
            new=AsyncMock(return_value={"password_changed": True}),
        ) as update_profile:
            with patch(
                "app.api.v1.endpoints.users.UserService.send_password_changed_notification",
                new=AsyncMock(return_value=None),
            ) as send_notice:
                with patch(
                    "app.api.v1.endpoints.users.UserAdminAuditService.log",
                    new=AsyncMock(return_value=None),
                ):
                    resp = await users_endpoint.update_profile(
                        data=UserUpdate(old_password="oldpass", new_password="newpass123", email_code="123456"),
                        request=request,
                        current_user={"id": 9, "username": "demo"},
                    )

        self.assertEqual(resp.get("code"), 200)
        update_profile.assert_awaited_once()
        send_notice.assert_awaited_once_with(
            9,
            request_ip="127.0.0.1",
            user_agent="Mozilla/5.0 Chrome/123.0",
        )


if __name__ == "__main__":
    unittest.main()
