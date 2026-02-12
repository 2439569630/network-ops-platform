import unittest
from unittest.mock import AsyncMock, patch

from app.constants.user import DELETED_USER_DISPLAY_NAME


class TestLocationBindUsersByIdsFallback(unittest.IsolatedAsyncioTestCase):
    async def test_missing_users_return_deleted_placeholder(self) -> None:
        async def _fetch_all(_sql: str, _ids):
            return [{"id": 1, "username": "u1", "nickname": "U1", "email": "u1@example.com"}]

        with patch("app.api.v1.endpoints.locations.db.fetch_all", new=AsyncMock(side_effect=_fetch_all)):
            from app.api.v1.endpoints.locations import list_bind_users_by_ids

            resp = await list_bind_users_by_ids(ids=[1, 2, 1], user={})

        self.assertEqual(resp["code"], 200)
        data = resp["data"]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], 1)
        self.assertEqual(data[0]["username"], "u1")
        self.assertEqual(data[1]["id"], 2)
        self.assertEqual(data[1]["nickname"], DELETED_USER_DISPLAY_NAME)


class TestNotificationLocationRecipientsFiltering(unittest.IsolatedAsyncioTestCase):
    async def test_location_recipients_filtered_by_existing_active_users(self) -> None:
        node = type("Node", (), {"node_id": 10})()

        class _QS:
            def __init__(self, *, first_value=None, values_list_value=None):
                self.first = AsyncMock(return_value=first_value)
                self.values_list = AsyncMock(return_value=values_list_value)

        with patch("app.services.notification_service.LocationNodeDevice.filter", return_value=_QS(first_value=node)):
            with patch(
                "app.services.notification_service.LocationNodeUser.filter",
                return_value=_QS(values_list_value=[1, 2]),
            ):
                with patch(
                    "app.services.notification_service.LocationNodeRole.filter",
                    return_value=_QS(values_list_value=[]),
                ):
                    with patch(
                        "app.services.notification_service.UserRole.filter",
                        return_value=_QS(values_list_value=[]),
                    ):
                        with patch(
                            "app.services.notification_service.User.filter",
                            return_value=_QS(values_list_value=[2]),
                        ):
                            from app.services.notification_service import NotificationService

                            result = await NotificationService._get_location_recipient_user_ids(device_id=99)

        self.assertEqual(result, {2})


if __name__ == "__main__":
    unittest.main()

