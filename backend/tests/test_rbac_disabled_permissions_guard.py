import json
import unittest
from unittest.mock import AsyncMock, patch


class _FakeRedisClient:
    def __init__(self, cached_value=None):
        self._cached_value = cached_value
        self.last_set_args = None

    async def get(self, key):
        return self._cached_value

    async def set(self, key, value, ex=None):
        self.last_set_args = (key, value, ex)
        return True


class TestDisabledPermissionsGuard(unittest.IsolatedAsyncioTestCase):
    async def test_set_disabled_permissions_ignores_non_disableable_codes(self):
        from app.api.v1.endpoints import rbac as rbac_endpoint
        from app.schemas.rbac import DisabledPermissionsSet

        fake_redis = _FakeRedisClient()

        with patch.object(rbac_endpoint, "_can_manage_rbac", new=AsyncMock(return_value=True)):
            with patch.object(rbac_endpoint, "get_disabled_permission_codes_cached", new=AsyncMock(return_value=[])):
                with patch.object(
                    rbac_endpoint.RbacService,
                    "get_all_permission_codes",
                    new=AsyncMock(return_value=["sys:notify:email", "sys:notify:test"]),
                ):
                    with patch.object(rbac_endpoint.SystemConfig, "set", new=AsyncMock()) as cfg_set:
                        with patch.object(rbac_endpoint.redis_manager, "get_client", return_value=fake_redis):
                            with patch.object(rbac_endpoint.UserAdminAuditService, "log", new=AsyncMock()):
                                resp = await rbac_endpoint.set_disabled_permissions(
                                    data=DisabledPermissionsSet(codes=["sys:notify:email", "sys:notify:test"]),
                                    request=None,
                                    current_user={"id": 1, "roles": ["superadmin"]},
                                )

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(resp.get("data", {}).get("codes"), ["sys:notify:test"])
        self.assertEqual(resp.get("data", {}).get("ignored_codes"), ["sys:notify:email"])
        self.assertIn("已自动忽略", resp.get("message", ""))
        cfg_set.assert_awaited_once_with("rbac:disabled_permissions", json.dumps(["sys:notify:test"]))

    async def test_get_disabled_permission_codes_cached_filters_non_disableable_codes(self):
        from app.services.rbac_service import RbacService

        cached = json.dumps(["sys:notify:email", "sys:notify:test"])
        fake_redis = _FakeRedisClient(cached_value=cached)

        with patch("app.services.rbac_service.redis_manager.get_client", return_value=fake_redis):
            codes = await RbacService.get_disabled_permission_codes_cached()

        self.assertEqual(codes, ["sys:notify:test"])


if __name__ == "__main__":
    unittest.main()
