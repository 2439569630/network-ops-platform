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


async def _get_role_code(role_id: int) -> str:
    row = await db.fetch_one("SELECT code FROM roles WHERE id = $1", int(role_id))
    return str((row or {}).get("code") or "").strip().lower()


async def _is_protected_role_id(role_id: int) -> bool:
    return (await _get_role_code(int(role_id))) in _PROTECTED_ROLE_CODES


async def _count_protected_role_users(*, exclude_user_id: int | None = None) -> int:
    """
    Helper: 计算拥有受保护角色 (超级管理员) 的有效用户数量。
    
    用于在删除或降级管理员时进行安全检查，防止系统中没有任何超级管理员。
    
    Args:
        exclude_user_id: 可选，排除指定用户 ID (模拟该用户被移除后的情况)
    """
    codes = sorted(list(_PROTECTED_ROLE_CODES))
    if exclude_user_id is None:
        sql = """
        SELECT COUNT(DISTINCT ur.user_id) AS cnt
        FROM user_roles ur
        INNER JOIN roles r ON r.id = ur.role_id
        INNER JOIN users u ON u.id = ur.user_id
        WHERE LOWER(COALESCE(r.code, '')) = ANY($1::text[])
          AND COALESCE(u.is_deleted, FALSE) = FALSE
        """
        val = await db.fetch_val(sql, codes)
        return int(val or 0)
    sql = """
    SELECT COUNT(DISTINCT ur.user_id) AS cnt
    FROM user_roles ur
    INNER JOIN roles r ON r.id = ur.role_id
    INNER JOIN users u ON u.id = ur.user_id
    WHERE LOWER(COALESCE(r.code, '')) = ANY($1::text[])
      AND COALESCE(u.is_deleted, FALSE) = FALSE
      AND ur.user_id <> $2
    """
    val = await db.fetch_val(sql, codes, int(exclude_user_id))
    return int(val or 0)


async def _target_has_protected_role(user_id: int) -> bool:
    """
    Helper: 检查指定用户是否拥有受保护角色 (超级管理员)。
    
    用于权限控制：普通管理员不能操作超级管理员。
    """
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
    """
    获取所有角色及其关联用户
    
    返回角色列表，每个角色包含其关联的用户列表。
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        data = await RbacService.get_all_roles_with_users()
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}

@router.get("/roles", response_model=dict)
async def list_roles(current_user: dict = Depends(deps.get_current_user)):
    """
    获取角色列表
    
    返回系统中的所有角色基本信息 (ID, 名称, 代码, 描述)。
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        roles = await RbacService.list_roles()
        return {"code": 200, "data": roles}
    except Exception as e:
        return {"code": 500, "message": f"获取角色列表失败: {str(e)}"}


@router.post("/roles", response_model=dict)
async def create_role(role_in: RoleCreate, current_user: dict = Depends(deps.get_current_user)):
    """
    创建新角色
    
    Args:
        name: 角色名称
        code: 角色唯一代码 (英文)
        description: 描述信息
    
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        role_id = await RbacService.create_role(role_in.name, role_in.code, role_in.description)
        return {"code": 200, "message": "创建成功", "data": {"id": role_id}}
    except Exception as e:
        return {"code": 500, "message": f"创建失败: {str(e)}"}


@router.put("/roles/{role_id}", response_model=dict)
async def update_role(role_id: int, role_in: RoleUpdate, current_user: dict = Depends(deps.get_current_user)):
    """
    更新角色信息
    
    更新角色的名称、描述等。
    注意：系统保留角色 (如 superadmin) 可能有修改限制。
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.update_role(role_id, role_in.model_dump())
        return {"code": 200, "message": "更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.delete("/roles/{role_id}", response_model=dict)
async def delete_role(role_id: int, current_user: dict = Depends(deps.get_current_user)):
    """
    删除角色
    
    删除指定 ID 的角色。
    注意：
    1. 系统保留角色不允许删除。
    2. 删除角色会自动解除其与用户和权限的关联。
    
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        await RbacService.delete_role(role_id)
        return {"code": 200, "message": "删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}


@router.get("/permissions", response_model=dict)
async def list_permissions(current_user: dict = Depends(deps.get_current_user)):
    """
    获取所有权限列表
    
    返回系统中定义的所有权限点 (ID, 名称, 代码, 描述)。
    包括系统内置权限和用户自定义权限。
    
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        permissions = await RbacService.list_permissions()
        return {"code": 200, "data": permissions}
    except Exception as e:
        return {"code": 500, "message": f"获取权限列表失败: {str(e)}"}

@router.get("/permissions/directory", response_model=dict)
async def list_permission_directory(current_user: dict = Depends(deps.get_current_user)):
    """
    获取权限目录结构
    
    返回按模块分组的权限树形结构。
    用于前端权限选择器展示 (如角色授权界面)。
    
    包含：
    1. 系统内置模块权限
    2. 自定义权限 (通常归类在 'custom' 模块下)
    
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    try:
        data = await RbacService.list_permission_directory(include_custom=True)
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取权限目录失败: {str(e)}"}


@router.get("/permissions/dependencies", response_model=dict)
async def get_permission_dependencies(current_user: dict = Depends(deps.get_current_user)):
    """
    获取权限依赖关系
    
    返回权限之间的依赖映射 (例如：查看详情 -> 列表查看)。
    前端在勾选权限时，可根据依赖关系自动勾选前置权限。
    
    需要 sys:role:manage 权限。
    """
    if not await _can_manage_rbac(current_user):
        return {"code": 403, "message": "权限不足"}
    deps_map = {str(k): [str(x) for x in (v or [])] for k, v in (RbacService.PERMISSION_DEPENDENCIES or {}).items()}
    return {"code": 200, "data": deps_map}


@router.get("/permissions/disabled", response_model=dict)
async def get_disabled_permissions(current_user: dict = Depends(deps.get_current_user)):
    """
    获取已禁用的权限列表
    
    返回被系统管理员临时禁用的权限代码。
    被禁用的权限即使被授权给用户，也不会生效。
    
    需要 sys:role:manage 权限。
    """
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
    """
    设置禁用权限列表
    
    全量更新被禁用的权限代码列表。
    操作立即生效 (更新 Redis 缓存和数据库配置)。
    
    Args:
        codes: 需要禁用的权限代码列表
    
    需要 sys:role:manage 权限。
    """
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
    """
    恢复系统默认权限
    
    如果在数据库中误删了系统内置权限，可使用此接口尝试恢复。
    
    Args:
        code: 需要恢复的权限代码
        
    需要 sys:role:manage 权限。
    """
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
        if await _is_protected_role_id(int(role_id)) and not user_is_super(current_user):
            return {"code": 403, "message": "仅超级管理员可管理该角色成员"}
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
        # 1. 检查是否涉及受保护角色 (超级管理员)
        if await _is_protected_role_id(int(role_id)):
            # 只有超级管理员才能管理超级管理员角色
            if not user_is_super(current_user):
                return {"code": 403, "message": "仅超级管理员可管理该角色成员"}
            
            # 禁止移除自己 (防止把自己踢出管理员组后无法恢复)
            if int(user_id) == int(current_user.get("id") or 0):
                return {"code": 400, "message": "不允许将自己从超级管理员角色移除"}
            
            # 确保系统中至少保留一个超级管理员
            remaining = await _count_protected_role_users(exclude_user_id=int(user_id))
            if remaining <= 0:
                return {"code": 400, "message": "必须至少保留一个超级管理员账号"}
        
        # 2. 执行移除操作
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
    """
    设置用户的角色
    
    全量替换用户的角色列表。
    会检查是否涉及超级管理员角色的变更（防止权限逃逸或误操作）。
    
    需要 sys:role:assign 权限。
    """
    has_perm = await user_has_permission(current_user, "sys:role:assign")
    if not has_perm:
        return {"code": 403, "message": "权限不足"}
    try:
        # 1. 权限边界检查
        # 如果目标用户已经是超级管理员，则只有超级管理员能修改其角色
        if await _target_has_protected_role(int(user_id)) and not check_super_admin(current_user):
            return {"code": 403, "message": "仅超级管理员可操作该用户"}
            
        actor_id = int(current_user.get("id") or 0)
        new_role_ids = [int(rid) for rid in (data.role_ids or []) if rid is not None]
        new_role_ids = sorted(list(set(new_role_ids)))

        # 2. 检查是否涉及超级管理员权限的变更
        old_has_protected = await _target_has_protected_role(int(user_id))
        new_has_protected = False
        
        # 检查新角色列表中是否包含受保护角色 (superadmin)
        if new_role_ids:
            rows = await db.fetch_all("SELECT code FROM roles WHERE id = ANY($1::int[])", new_role_ids)
            codes = {str((r or {}).get("code") or "").strip().lower() for r in (rows or [])}
            codes = {c for c in codes if c}
            new_has_protected = bool(codes & _PROTECTED_ROLE_CODES)

        # 3. 防止自我降级和误删最后一个管理员
        # 如果用户原本是超管，现在要去掉超管角色
        if old_has_protected and not new_has_protected:
            # 不允许自己取消自己的超管权限
            if int(user_id) == actor_id:
                return {"code": 400, "message": "不允许将自己降级为非超级管理员"}
                
            # 确保还有其他超管存在
            remaining = await _count_protected_role_users(exclude_user_id=int(user_id))
            if remaining <= 0:
                return {"code": 400, "message": "必须至少保留一个超级管理员账号"}

        # 4. 执行角色更新
        await RbacService.set_user_roles(user_id, data.role_ids)
        
        # 5. 记录关键操作审计日志
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
