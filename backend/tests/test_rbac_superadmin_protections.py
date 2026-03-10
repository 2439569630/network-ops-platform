import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.requests import Request


class TestRbacSuperadminProtections(unittest.IsolatedAsyncioTestCase):
    async def test_set_user_roles_blocks_non_super_promoting_to_superadmin(self):
        from app.api.v1.endpoints import rbac as rbac_endpoint
        from app.schemas.rbac import UserRolesSet

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "PUT",
            "path": "/api/v1/rbac/users/2/roles",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch.object(rbac_endpoint, "user_has_permission", new=AsyncMock(return_value=True)):
            with patch.object(rbac_endpoint, "_target_has_protected_role", new=AsyncMock(return_value=False)):
                rbac_endpoint.db.fetch_all = AsyncMock(return_value=[{"code": "superadmin"}])
                with patch.object(rbac_endpoint.RbacService, "set_user_roles", new=AsyncMock()) as set_roles:
                    resp = await rbac_endpoint.set_user_roles(
                        user_id=2,
                        data=UserRolesSet(role_ids=[1]),
                        request=request,
                        current_user={"id": 1, "roles": ["admin"]},
                    )

        self.assertEqual(resp.get("code"), 403)
        self.assertIn("仅超级管理员可授予超级管理员角色", resp.get("message", ""))
        self.assertEqual(set_roles.await_count, 0)

    async def test_set_user_roles_allows_super_promoting_to_superadmin(self):
        from app.api.v1.endpoints import rbac as rbac_endpoint
        from app.schemas.rbac import UserRolesSet

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "PUT",
            "path": "/api/v1/rbac/users/2/roles",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch.object(rbac_endpoint, "user_has_permission", new=AsyncMock(return_value=True)):
            with patch.object(rbac_endpoint, "_target_has_protected_role", new=AsyncMock(return_value=False)):
                rbac_endpoint.db.fetch_all = AsyncMock(return_value=[{"code": "superadmin"}])
                with patch.object(rbac_endpoint.RbacService, "set_user_roles", new=AsyncMock()) as set_roles:
                    with patch.object(rbac_endpoint, "_get_user_role_ids", new=AsyncMock(side_effect=[[], []])):
                        with patch.object(rbac_endpoint, "_get_user_role_codes", new=AsyncMock(side_effect=[[], []])):
                            with patch.object(rbac_endpoint.UserAdminAuditService, "log", new=AsyncMock()):
                                resp = await rbac_endpoint.set_user_roles(
                                    user_id=2,
                                    data=UserRolesSet(role_ids=[1]),
                                    request=request,
                                    current_user={"id": 1, "roles": ["superadmin"]},
                                )

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(set_roles.await_count, 1)


class TestRbacServiceProtectedCodes(unittest.IsolatedAsyncioTestCase):
    async def test_create_role_rejects_protected_code(self):
        from app.services.rbac_service import RbacService

        with patch("app.services.rbac_service.Role.create", new=AsyncMock()) as create:
            with self.assertRaises(ValueError):
                await RbacService.create_role("x", "superadmin", None)
        self.assertEqual(create.await_count, 0)

    async def test_set_default_role_rejects_protected_role(self):
        from app.services.rbac_service import RbacService

        class QS:
            def __init__(self, *, first_value=None):
                self._first_value = first_value
                self.update = AsyncMock(return_value=None)

            async def first(self):
                return self._first_value

        def filter_side_effect(**kwargs):
            if "id" in kwargs:
                return QS(first_value=SimpleNamespace(code="superadmin"))
            if kwargs.get("is_default") is True:
                return QS(first_value=None)
            return QS(first_value=None)

        with patch("app.services.rbac_service.Role.filter", new=filter_side_effect):
            with self.assertRaises(ValueError):
                await RbacService.set_default_role(1)


class TestUserServiceDefaultRoleProtection(unittest.IsolatedAsyncioTestCase):
    async def test_create_user_skips_protected_default_role(self):
        from app.schemas.user import UserCreate
        from app.services import user_service as user_service_mod

        fake_user = SimpleNamespace(id=123)

        with patch.object(user_service_mod.UserService, "get_user_by_username", new=AsyncMock(return_value=None)):
            with patch.object(user_service_mod.User, "create", new=AsyncMock(return_value=fake_user)):
                user_service_mod.db.fetch_one = AsyncMock(return_value={"id": 5, "code": "superadmin"})
                user_service_mod.db.execute = AsyncMock(return_value=None)

                uid = await user_service_mod.UserService.create_user(
                    UserCreate(username="user1", password="password123", nickname=None, email=None, permissions=None)
                )

        self.assertEqual(uid, 123)
        self.assertEqual(user_service_mod.db.execute.await_count, 0)


class TestRbacAuditLogs(unittest.IsolatedAsyncioTestCase):
    async def test_create_role_writes_audit_log(self):
        from app.api.v1.endpoints import rbac as rbac_endpoint
        from app.schemas.rbac import RoleCreate

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/rbac/roles",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch.object(rbac_endpoint, "_can_manage_rbac", new=AsyncMock(return_value=True)):
            with patch.object(rbac_endpoint.RbacService, "create_role", new=AsyncMock(return_value=9)):
                with patch.object(rbac_endpoint, "_get_role_snapshot", new=AsyncMock(return_value={"id": 9, "code": "ops"})):
                    with patch.object(rbac_endpoint.UserAdminAuditService, "log", new=AsyncMock()) as log:
                        resp = await rbac_endpoint.create_role(
                            RoleCreate(name="运维", code="ops", description=None),
                            request=request,
                            current_user={"id": 1, "roles": ["admin"], "username": "a"},
                        )

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(log.await_count, 1)
        _args, kwargs = log.call_args
        self.assertEqual(kwargs.get("action"), "rbac.role.create")
        self.assertEqual(kwargs.get("actor", {}).get("id"), 1)
        self.assertEqual(kwargs.get("target_type"), "role")
        self.assertEqual(kwargs.get("target_id"), 9)
        self.assertEqual(kwargs.get("target_label"), "ops")
        self.assertTrue(kwargs.get("request_ip"))

    async def test_set_role_permissions_writes_audit_log(self):
        from app.api.v1.endpoints import rbac as rbac_endpoint
        from app.schemas.rbac import RolePermissionsSet

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "PUT",
            "path": "/api/v1/rbac/roles/5/permissions",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch.object(rbac_endpoint, "_can_manage_rbac", new=AsyncMock(return_value=True)):
            with patch.object(rbac_endpoint, "_get_role_permission_ids", new=AsyncMock(side_effect=[[1], [1, 2]])):
                with patch.object(rbac_endpoint, "_get_role_permission_codes", new=AsyncMock(side_effect=[["a"], ["a", "b"]])):
                    with patch.object(rbac_endpoint, "_get_role_snapshot", new=AsyncMock(return_value={"id": 5, "code": "ops"})):
                        with patch.object(rbac_endpoint.RbacService, "set_role_permissions", new=AsyncMock()) as set_perms:
                            with patch.object(rbac_endpoint.UserAdminAuditService, "log", new=AsyncMock()) as log:
                                resp = await rbac_endpoint.set_role_permissions(
                                    role_id=5,
                                    data=RolePermissionsSet(permission_ids=[1, 2]),
                                    request=request,
                                    current_user={"id": 1, "roles": ["admin"], "username": "a"},
                                )

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(set_perms.await_count, 1)
        self.assertEqual(log.await_count, 1)
        _args, kwargs = log.call_args
        self.assertEqual(kwargs.get("action"), "rbac.role.set_permissions")
        self.assertEqual(kwargs.get("target_type"), "role")
        self.assertEqual(kwargs.get("target_id"), 5)
        detail = kwargs.get("detail") or {}
        self.assertEqual(detail.get("role_id"), 5)
        self.assertEqual(detail.get("before_permission_ids"), [1])
        self.assertEqual(detail.get("after_permission_ids"), [1, 2])
        self.assertEqual(detail.get("added_permission_codes"), ["b"])
        self.assertEqual(detail.get("removed_permission_codes"), [])

    async def test_remove_user_from_role_writes_audit_log(self):
        from app.api.v1.endpoints import rbac as rbac_endpoint

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "DELETE",
            "path": "/api/v1/rbac/roles/5/users/8",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
        request = Request(scope)

        with patch.object(rbac_endpoint, "_can_manage_rbac", new=AsyncMock(return_value=True)):
            with patch.object(rbac_endpoint, "_is_protected_role_id", new=AsyncMock(return_value=False)):
                rbac_endpoint.db.fetch_val = AsyncMock(return_value=1)
                with patch.object(rbac_endpoint, "_get_user_role_ids", new=AsyncMock(side_effect=[[5], [1]])):
                    with patch.object(rbac_endpoint, "_get_user_role_codes", new=AsyncMock(side_effect=[["ops"], ["viewer"]])):
                        with patch.object(rbac_endpoint, "_get_role_snapshot", new=AsyncMock(return_value={"id": 5, "code": "ops"})):
                            with patch.object(rbac_endpoint.RbacService, "remove_user_from_role", new=AsyncMock()) as rm:
                                with patch.object(rbac_endpoint.UserAdminAuditService, "log", new=AsyncMock()) as log:
                                    resp = await rbac_endpoint.remove_user_from_role(
                                        role_id=5,
                                        user_id=8,
                                        request=request,
                                        current_user={"id": 1, "roles": ["admin"], "username": "a"},
                                    )

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(rm.await_count, 1)
        self.assertEqual(log.await_count, 1)
        _args, kwargs = log.call_args
        self.assertEqual(kwargs.get("action"), "rbac.role.remove_user")
        self.assertEqual(kwargs.get("target_type"), "role")
        self.assertEqual(kwargs.get("target_id"), 5)


class TestUserAdminAuditServiceSchema(unittest.IsolatedAsyncioTestCase):
    async def test_log_includes_target_columns(self):
        from app.services.user_admin_audit_service import UserAdminAuditService
        from app.services import user_admin_audit_service as svc_mod

        UserAdminAuditService._table_ready = False
        exec_mock = AsyncMock(return_value=None)
        svc_mod.db.execute = exec_mock

        await UserAdminAuditService.log(
            action="rbac.role.update",
            actor={"id": 1, "username": "a"},
            target_type="role",
            target_id=5,
            target_label="ops",
            request_ip="127.0.0.1",
            detail={"x": 1},
        )

        self.assertGreaterEqual(exec_mock.await_count, 2)
        sqls = [str(call.args[0]) for call in exec_mock.call_args_list if call.args]
        self.assertTrue(any("ALTER TABLE user_admin_audit_log ADD COLUMN IF NOT EXISTS target_type" in s for s in sqls))
        self.assertTrue(any("ALTER TABLE user_admin_audit_log ADD COLUMN IF NOT EXISTS target_id" in s for s in sqls))
        self.assertTrue(any("ALTER TABLE user_admin_audit_log ADD COLUMN IF NOT EXISTS target_label" in s for s in sqls))
        self.assertTrue(any("INSERT INTO user_admin_audit_log" in s and "target_type" in s and "target_id" in s for s in sqls))


if __name__ == "__main__":
    unittest.main()
