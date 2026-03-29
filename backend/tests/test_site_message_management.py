import unittest
from unittest.mock import AsyncMock, patch


class TestSiteMessageManagement(unittest.IsolatedAsyncioTestCase):
    async def test_create_targeted_site_message_allows_publish_permission(self):
        from app.api.v1.endpoints import notifications as notifications_endpoint
        from app.schemas.notification import SiteMessageCreate

        with patch("app.api.v1.endpoints.notifications.user_is_super", return_value=False):
            with patch(
                "app.api.v1.endpoints.notifications.user_has_permission",
                new=AsyncMock(side_effect=lambda _user, perm: perm == "sys:message:publish"),
            ):
                with patch(
                    "app.api.v1.endpoints.notifications.NotificationService.create_site_message",
                    new=AsyncMock(return_value={"id": 11, "title": "t"}),
                ) as create_message:
                    resp = await notifications_endpoint.create_site_message(
                        data=SiteMessageCreate(title="t", content="c", is_global=False, target_user_id=2),
                        user={"id": 1, "username": "admin"},
                    )

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(resp.get("message"), "发布成功")
        create_message.assert_awaited_once()

    async def test_create_global_site_message_requires_global_permission(self):
        from app.api.v1.endpoints import notifications as notifications_endpoint
        from app.schemas.notification import SiteMessageCreate

        with patch("app.api.v1.endpoints.notifications.user_is_super", return_value=False):
            with patch(
                "app.api.v1.endpoints.notifications.user_has_permission",
                new=AsyncMock(side_effect=lambda _user, perm: perm == "sys:message:publish"),
            ):
                resp = await notifications_endpoint.create_site_message(
                    data=SiteMessageCreate(title="t", content="c", is_global=True, target_user_id=None),
                    user={"id": 1, "username": "admin"},
                )

        self.assertEqual(resp.get("code"), 403)
        self.assertEqual(resp.get("message"), "缺少全站通知权限")

    async def test_list_site_messages_forwards_limit_and_offset(self):
        from app.api.v1.endpoints import notifications as notifications_endpoint

        with patch(
            "app.api.v1.endpoints.notifications.NotificationService.list_site_messages",
            new=AsyncMock(return_value=[]),
        ) as list_messages:
            resp = await notifications_endpoint.list_site_messages(
                limit=50,
                offset=20,
                unread_only=True,
                user={"id": 8},
            )

        self.assertEqual(resp.get("code"), 200)
        list_messages.assert_awaited_once_with(user_id=8, limit=50, offset=20, unread_only=True)


if __name__ == "__main__":
    unittest.main()
