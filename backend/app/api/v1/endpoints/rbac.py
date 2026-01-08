from fastapi import APIRouter, Depends, Body
import json
from app.api import deps
from app.schemas.rbac import (
    RoleCreate,
    RoleUpdate,
    PermissionCreate,
    PermissionUpdate,
    RolePermissionsSet,
    DisabledPermissionsSet,
)
from app.services.rbac_service import RbacService
from app.core.security import (
    user_is_super,
    get_disabled_permission_codes_cached,
    DISABLED_PERMISSIONS_CONFIG_KEY,
    DISABLED_PERMISSIONS_REDIS_KEY,
)
from app.core.redis import redis_manager
from app.core.system_config import SystemConfig


router = APIRouter()


def check_super_admin(user: dict):
    return user_is_super(user)


@router.get("/roles/with_users", response_model=dict)
async def get_roles_with_users(current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        data = await RbacService.get_all_roles_with_users()
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}

@router.get("/roles", response_model=dict)
async def list_roles(current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        roles = await RbacService.list_roles()
        return {"code": 200, "data": roles}
    except Exception as e:
        return {"code": 500, "message": f"获取角色列表失败: {str(e)}"}


@router.post("/roles", response_model=dict)
async def create_role(role_in: RoleCreate, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        role_id = await RbacService.create_role(role_in.name, role_in.code, role_in.description)
        return {"code": 200, "message": "创建成功", "data": {"id": role_id}}
    except Exception as e:
        return {"code": 500, "message": f"创建失败: {str(e)}"}


@router.put("/roles/{role_id}", response_model=dict)
async def update_role(role_id: int, role_in: RoleUpdate, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.update_role(role_id, role_in.model_dump())
        return {"code": 200, "message": "更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.delete("/roles/{role_id}", response_model=dict)
async def delete_role(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.delete_role(role_id)
        return {"code": 200, "message": "删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}


@router.get("/permissions", response_model=dict)
async def list_permissions(current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        permissions = await RbacService.list_permissions()
        return {"code": 200, "data": permissions}
    except Exception as e:
        return {"code": 500, "message": f"获取权限列表失败: {str(e)}"}

@router.get("/permissions/directory", response_model=dict)
async def list_permission_directory(current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        data = await RbacService.list_permission_directory(include_custom=True)
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取权限目录失败: {str(e)}"}


@router.get("/permissions/disabled", response_model=dict)
async def get_disabled_permissions(current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
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
    if not check_super_admin(current_user):
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


@router.post("/permissions/sync", response_model=dict)
async def sync_system_permissions(current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        result = await RbacService.sync_system_permissions()
        data = await RbacService.list_permission_directory(include_custom=True)
        return {"code": 200, "message": "同步成功", "data": {"result": result, "directory": data}}
    except Exception as e:
        return {"code": 500, "message": f"同步失败: {str(e)}"}


@router.post("/permissions", response_model=dict)
async def create_permission(
    perm_in: PermissionCreate, current_user: dict = Depends(deps.get_current_user)
):
    if not check_super_admin(current_user):
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
    if not check_super_admin(current_user):
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
    if not check_super_admin(current_user):
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


@router.get("/roles/{role_id}/permissions", response_model=dict)
async def get_role_permissions(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
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
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.set_role_permissions(role_id, data.permission_ids)
        return {"code": 200, "message": "保存成功"}
    except Exception as e:
        return {"code": 500, "message": f"保存失败: {str(e)}"}


@router.post("/roles/{role_id}/default", response_model=dict)
async def set_default_role(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.set_default_role(role_id)
        return {"code": 200, "message": "已设为默认角色"}
    except Exception as e:
        return {"code": 500, "message": f"设置失败: {str(e)}"}


@router.get("/roles/{role_id}/users", response_model=dict)
async def get_role_users(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        users = await RbacService.get_role_users(role_id)
        return {"code": 200, "data": users}
    except Exception as e:
        return {"code": 500, "message": f"获取成员失败: {str(e)}"}


@router.get("/roles/{role_id}/available_users", response_model=dict)
async def get_available_users(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        users = await RbacService.get_users_not_in_role(role_id)
        return {"code": 200, "data": users}
    except Exception as e:
        return {"code": 500, "message": f"获取用户失败: {str(e)}"}


@router.post("/roles/{role_id}/users", response_model=dict)
async def add_users_to_role(
    role_id: int,
    user_ids: list[int] = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user),
):
    if not check_super_admin(current_user):
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
    if not check_super_admin(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.remove_user_from_role(role_id, user_id)
        return {"code": 200, "message": "移除成功"}
    except Exception as e:
        return {"code": 500, "message": f"移除失败: {str(e)}"}
