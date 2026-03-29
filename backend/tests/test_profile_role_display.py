import unittest
from unittest.mock import AsyncMock, patch


class TestProfileRoleDisplay(unittest.IsolatedAsyncioTestCase):
    async def test_get_user_by_id_returns_real_roles(self):
        from app.services.user_service import UserService

        user = type(
            "UserStub",
            (),
            {
                "id": 7,
                "username": "demo",
                "nickname": "演示用户",
                "email": "demo@example.com",
                "avatar_url": None,
                "is_approved": True,
                "created_at": "2026-03-24T00:00:00Z",
            },
        )()

        with patch("app.services.user_service.User.filter") as filter_mock:
            filter_mock.return_value.first = AsyncMock(return_value=user)
            with patch.object(
                UserService,
                "_get_user_roles",
                new=AsyncMock(return_value=[{"id": 2, "name": "资产管理员", "code": "asset_admin"}]),
            ):
                result = await UserService.get_user_by_id(7)

        self.assertEqual(result.get("username"), "demo")
        self.assertEqual(result.get("roles"), [{"id": 2, "name": "资产管理员", "code": "asset_admin"}])

    async def test_update_user_roles_bumps_perm_version(self):
        from app.services.user_service import UserService

        delete_mock = AsyncMock(return_value=None)
        bulk_create_mock = AsyncMock(return_value=None)

        with patch("app.services.user_service.UserRole.filter") as filter_mock:
            filter_mock.return_value.delete = delete_mock
            with patch("app.services.user_service.UserRole.bulk_create", new=bulk_create_mock):
                with patch("app.services.rbac_service.RbacService.bump_user_perm_version", new=AsyncMock(return_value=3)) as bump_mock:
                    await UserService.update_user_roles(7, [1, 2])

        self.assertEqual(delete_mock.await_count, 1)
        self.assertEqual(bulk_create_mock.await_count, 1)
        bump_mock.assert_awaited_once_with(7)


if __name__ == "__main__":
    unittest.main()
