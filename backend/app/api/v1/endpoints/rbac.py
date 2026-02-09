from fastapi import APIRouter, Depends, Body, Query, Request
import json
from app.api import deps
from app.schemas.rbac import (
    RoleCreate,
    RoleUpdate,
    PermissionCreate,
    PermissionUpdate,
    PermissionRestore,
    RolePermissionsSet,
    DisabledPermissionsSet,
    UserRolesSet,
)
from app.services.rbac_service import RbacService
from app.core.security import (
    user_is_super,
    get_disabled_permission_codes_cached,
    DISABLED_PERMISSIONS_CONFIG_KEY,
    DISABLED_PERMISSIONS_REDIS_KEY,
    user_has_permission,
)
from app.core.redis import redis_manager
from app.core.system_config import SystemConfig
from app.core.database import db
from app.services.user_admin_audit_service import UserAdminAuditService


router = APIRouter()

async def _can_manage_rbac(user: dict) -> bool:
    if user_is_super(user):
        return True
    return bool(await user_has_permission(user, "sys:role:manage"))


def check_super_admin(user: dict):
    return user_is_super(user)


_PROTECTED_ROLE_CODES = {"superadmin", "super_admin", "super-admin"}


async def _target_has_protected_role(user_id: int) -> bool:
    rows = await db.fetch_all(
        """
        SELECT r.code
        FROM roles r
        INNER JOIN user_roles ur ON ur.role_id = r.id
        WHERE ur.user_id = $1
        """,
        int(user_id),
    )
    codes = {str((r or {}).get("code") or "").strip().lower() for r in (rows or [])}
    codes = {c for c in codes if c}
    return bool(codes & _PROTECTED_ROLE_CODES)


@router.get("/roles/with_users", response_model=dict)
async def get_roles_with_users(current_user: dict = Depends(deps.get_current_user)):
    """获取所有角色及其关联用户"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        data = await RbacService.get_all_roles_with_users()
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}

@router.get("/roles", response_model=dict)
async def list_roles(current_user: dict = Depends(deps.get_current_user)):
    """获取角色列表"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        roles = await RbacService.list_roles()
        return {"code": 200, "data": roles}
    except Exception as e:
        return {"code": 500, "message": f"获取角色列表失败: {str(e)}"}


@router.post("/roles", response_model=dict)
async def create_role(role_in: RoleCreate, current_user: dict = Depends(deps.get_current_user)):
    """创建新角色"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        role_id = await RbacService.create_role(role_in.name, role_in.code, role_in.description)
        return {"code": 200, "message": "创建成功", "data": {"id": role_id}}
    except Exception as e:
        return {"code": 500, "message": f"创建失败: {str(e)}"}


@router.put("/roles/{role_id}", response_model=dict)
async def update_role(role_id: int, role_in: RoleUpdate, current_user: dict = Depends(deps.get_current_user)):
    """更新角色信息"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.update_role(role_id, role_in.model_dump())
        return {"code": 200, "message": "更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.delete("/roles/{role_id}", response_model=dict)
async def delete_role(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    """删除角色"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.delete_role(role_id)
        return {"code": 200, "message": "删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}


@router.get("/permissions", response_model=dict)
async def list_permissions(current_user: dict = Depends(deps.get_current_user)):
    """获取所有权限列表"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        permissions = await RbacService.list_permissions()
        return {"code": 200, "data": permissions}
    except Exception as e:
        return {"code": 500, "message": f"获取权限列表失败: {str(e)}"}

@router.get("/permissions/directory", response_model=dict)
async def list_permission_directory(current_user: dict = Depends(deps.get_current_user)):
    """获取权限目录结构"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        data = await RbacService.list_permission_directory(include_custom=True)
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取权限目录失败: {str(e)}"}


@router.get("/permissions/dependencies", response_model=dict)
async def get_permission_dependencies(current_user: dict = Depends(deps.get_current_user)):
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    deps_map = {str(k): [str(x) for x in (v or [])] for k, v in (RbacService.PERMISSION_DEPENDENCIES or {}).items()}
    return {"code": 200, "data": deps_map}


@router.get("/permissions/disabled", response_model=dict)
async def get_disabled_permissions(current_user: dict = Depends(deps.get_current_user)):
    """获取已禁用的权限列表"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        codes = await get_disabled_permission_codes_cached()
        return {"code": 200, "data": {"codes": codes}}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}


@router.put("/permissions/disabled", response_model=dict)
async def set_disabled_permissions(
    data: DisabledPermissionsSet,
    current_user: dict = Depends(deps.get_current_user),
):
    """设置禁用权限列表"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        raw_codes = [str(c).strip() for c in (data.codes or []) if str(c).strip()]
        target = sorted(list(set(raw_codes)))
        existing = set([str(c).strip() for c in (await RbacService.get_all_permission_codes()) if str(c).strip()])
        target = [c for c in target if c in existing]

        await SystemConfig.set(DISABLED_PERMISSIONS_CONFIG_KEY, json.dumps(target))
        try:
            redis_client = redis_manager.get_client()
            await redis_client.set(DISABLED_PERMISSIONS_REDIS_KEY, json.dumps(target), ex=60)
        except Exception:
            pass
        return {"code": 200, "message": "更新成功", "data": {"codes": target}}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.post("/permissions/restore", response_model=dict)
async def restore_system_permission(
    data: PermissionRestore,
    current_user: dict = Depends(deps.get_current_user),
):
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        ok = await RbacService.restore_system_permission(data.code)
        if not ok:
            return {"code": 400, "message": "仅支持系统权限恢复"}
        return {"code": 200, "message": "恢复成功"}
    except Exception as e:
        return {"code": 500, "message": f"恢复失败: {str(e)}"}


@router.post("/permissions", response_model=dict)
async def create_permission(
    perm_in: PermissionCreate, current_user: dict = Depends(deps.get_current_user)
):
    """创建自定义权限"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        if RbacService.is_system_permission_code(perm_in.code):
            return {"code": 400, "message": "系统权限不允许手动创建，请使用同步功能"}
        perm_id = await RbacService.create_permission(perm_in.name, perm_in.code, perm_in.description)
        return {"code": 200, "message": "创建成功", "data": {"id": perm_id}}
    except Exception as e:
        return {"code": 500, "message": f"创建失败: {str(e)}"}


@router.put("/permissions/{permission_id}", response_model=dict)
async def update_permission(
    permission_id: int, perm_in: PermissionUpdate, current_user: dict = Depends(deps.get_current_user)
):
    """更新权限信息"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        existing = await RbacService.get_permission_by_id(permission_id)
        if not existing:
            return {"code": 404, "message": "权限不存在"}
        existing_code = existing.get("code")
        if RbacService.is_system_permission_code(existing_code):
            if perm_in.code is not None and str(perm_in.code) != str(existing_code):
                return {"code": 400, "message": "系统权限不允许修改编码"}
        if perm_in.code is not None:
            new_code = str(perm_in.code)
            if RbacService.is_system_permission_code(new_code) and new_code != str(existing_code):
                return {"code": 400, "message": "不允许将自定义权限改为系统权限编码"}
        await RbacService.update_permission(permission_id, perm_in.model_dump())
        return {"code": 200, "message": "更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.delete("/permissions/{permission_id}", response_model=dict)
async def delete_permission(permission_id: int, current_user: dict = Depends(deps.get_current_user)):
    """删除自定义权限"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        existing = await RbacService.get_permission_by_id(permission_id)
        if not existing:
            return {"code": 404, "message": "权限不存在"}
        if RbacService.is_system_permission_code(existing.get("code")):
            return {"code": 400, "message": "系统权限不允许删除"}
        await RbacService.delete_permission(permission_id)
        return {"code": 200, "message": "删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}


@router.get("/roles/users_distribution", response_model=dict)
async def get_users_distribution(
    q: str = Query("", max_length=200),
    role_id: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(deps.get_current_user),
):
    """获取用户角色分布列表"""
    # 允许 superadmin 或拥有 sys:role:distribution 权限的用户
    has_perm = await user_has_permission(current_user, "sys:role:distribution")
    if not has_perm:
        return {"code": 403, "message": "权限不足"}
    try:
        result = await RbacService.get_users_with_roles_paginated(q=q, role_id=role_id, page=page, page_size=page_size)
        return {"code": 200, "data": result.get("items") or [], "meta": {"total": result.get("total") or 0, "page": result.get("page") or page, "page_size": result.get("page_size") or page_size}}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}


@router.get("/roles/{role_id}/permissions", response_model=dict)
async def get_role_permissions(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    """获取角色拥有的权限"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        permissions = await RbacService.get_role_permissions(role_id)
        return {"code": 200, "data": permissions}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}


@router.put("/roles/{role_id}/permissions", response_model=dict)
async def set_role_permissions(
    role_id: int,
    data: RolePermissionsSet,
    current_user: dict = Depends(deps.get_current_user),
):
    """设置角色的权限"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.set_role_permissions(role_id, data.permission_ids)
        return {"code": 200, "message": "保存成功"}
    except Exception as e:
        return {"code": 500, "message": f"保存失败: {str(e)}"}


@router.post("/roles/{role_id}/default", response_model=dict)
async def set_default_role(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    """设置默认角色"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.set_default_role(role_id)
        return {"code": 200, "message": "已设为默认角色"}
    except Exception as e:
        return {"code": 500, "message": f"设置失败: {str(e)}"}


@router.get("/roles/{role_id}/users", response_model=dict)
async def get_role_users(
    role_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(deps.get_current_user),
):
    """获取角色下的用户列表"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        result = await RbacService.get_role_users(role_id, page=page, page_size=page_size)
        return {"code": 200, "data": result.get("items") or [], "meta": {"total": result.get("total") or 0, "page": result.get("page") or page, "page_size": result.get("page_size") or page_size}}
    except Exception as e:
        return {"code": 500, "message": f"获取成员失败: {str(e)}"}


@router.get("/roles/{role_id}/available_users", response_model=dict)
async def get_available_users(
    role_id: int,
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(deps.get_current_user),
):
    """获取可添加到角色的用户列表"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        result = await RbacService.get_users_not_in_role(role_id, q=q, page=page, page_size=page_size)
        return {"code": 200, "data": result.get("items") or [], "meta": {"total": result.get("total") or 0, "page": result.get("page") or page, "page_size": result.get("page_size") or page_size, "q": result.get("q") or str(q or "").strip()}}
    except Exception as e:
        return {"code": 500, "message": f"获取用户失败: {str(e)}"}


@router.post("/roles/{role_id}/users", response_model=dict)
async def add_users_to_role(
    role_id: int,
    user_ids: list[int] = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user),
):
    """批量添加用户到角色"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.add_users_to_role(role_id, user_ids)
        return {"code": 200, "message": "成员添加成功"}
    except Exception as e:
        return {"code": 500, "message": f"添加失败: {str(e)}"}


@router.delete("/roles/{role_id}/users/{user_id}", response_model=dict)
async def remove_user_from_role(
    role_id: int, user_id: int, current_user: dict = Depends(deps.get_current_user)
):
    """从角色移除用户"""
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.remove_user_from_role(role_id, user_id)
        return {"code": 200, "message": "移除成功"}
    except Exception as e:
        return {"code": 500, "message": f"移除失败: {str(e)}"}


@router.put("/users/{user_id}/roles", response_model=dict)
async def set_user_roles(
    user_id: int,
    data: UserRolesSet,
    request: Request,
    current_user: dict = Depends(deps.get_current_user),
):
    """设置用户的角色"""
    # 允许 superadmin 或拥有 sys:role:distribution 权限的用户 (认为管理分布包含分配角色)
    # 或者我们应该定义一个 sys:role:assign? 暂时复用 distribution
    has_perm = await user_has_permission(current_user, "sys:role:assign") or await user_has_permission(current_user, "sys:role:distribution")
    if not has_perm:
        return {"code": 403, "message": "权限不足"}
    try:
        if await _target_has_protected_role(int(user_id)) and not check_super_admin(current_user):
            return {"code": 403, "message": "仅超级管理员可操作该用户"}
        await RbacService.set_user_roles(user_id, data.role_ids)
        xff = request.headers.get("x-forwarded-for") if request else None
        ip = (xff.split(",")[0].strip() if xff else None) or (request.client.host if request and request.client else None)
        await UserAdminAuditService.log(
            action="user.set_roles",
            actor=current_user,
            target_user_id=int(user_id),
            request_ip=str(ip).strip() if ip else None,
            detail={"role_ids": data.role_ids},
        )
        return {"code": 200, "message": "设置成功"}
    except Exception as e:
        return {"code": 500, "message": f"设置失败: {str(e)}"}
