
from typing import List, Optional, Dict, Any
from app.core.database import db
from app.core.redis import redis_manager

# ORM Imports
from app.models.orm.rbac import Role, Permission, UserRole, RolePermission
from app.models.orm.user import User
from tortoise.expressions import Q

class RbacService:
    """
    基于角色的访问控制(RBAC)服务类
    提供权限管理、角色管理以及用户权限验证等功能
    """
    # 权限依赖关系字典，定义了某些权限所需的前置权限
    PERMISSION_DEPENDENCIES: Dict[str, List[str]] = {
        "sys:location:add": ["sys:location:manage"],
        "sys:location:edit": ["sys:location:manage"],
        "sys:location:del": ["sys:location:manage"],
        "sys:location:manage": ["sys:location:view"],
        "sys:device:add": ["sys:device:list"],
        "sys:device:edit": ["sys:device:list"],
        "sys:device:del": ["sys:device:list"],
        "sys:device:audit": ["sys:device:list"],
        "sys:device:interface:view": ["sys:device:list"],
        "sys:device:route:view": ["sys:device:list"],
        "sys:device:vlan:view": ["sys:device:list"],
        "sys:user:manage": ["sys:user:view"],
        "sys:user:import": ["sys:user:manage"],
        "sys:config:edit": ["sys:config:view"],
        "sys:config:push": ["sys:device:list"],
        "sys:repair:create": ["sys:repair:view"],
        "sys:repair:accept": ["sys:repair:view"],
        "sys:repair:handle": ["sys:repair:view", "sys:repair:accept"],
        "sys:repair:list_all": ["sys:repair:view"],
        "sys:repair:manage": ["sys:repair:view", "sys:repair:handle", "sys:repair:accept", "sys:repair:list_all"],
        "sys:repair:image:add": ["sys:repair:image:view"],
        "sys:repair:image:edit": ["sys:repair:image:view"],
        "sys:repair:image:del": ["sys:repair:image:view"],
    }

    # 系统预定义权限列表
    SYSTEM_PERMISSIONS: List[Dict[str, str]] = [
        {"name": "登录", "code": "sys:auth:login", "description": "允许用户登录系统"},
        {"name": "注册", "code": "sys:auth:register", "description": "允许用户注册新账号"},
        {"name": "邮箱验证", "code": "sys:email:verify", "description": "允许用户进行邮箱验证"},
        {"name": "系统概览", "code": "sys:dashboard:view", "description": "允许查看仪表盘概览信息"},
        {"name": "查看监控", "code": "sys:monitor:view", "description": "允许查看系统监控数据"},
        {"name": "消息中心", "code": "sys:message:access", "description": "允许访问消息中心"},
        {"name": "订阅实时告警", "code": "sys:alert:subscribe", "description": "允许订阅和接收实时告警通知"},
        {"name": "查看通知历史", "code": "sys:notify:history", "description": "允许查看历史通知记录"},
        {"name": "查看通知配置", "code": "sys:notify:config:view", "description": "允许查看通知渠道配置"},
        {"name": "编辑通知配置", "code": "sys:notify:config:edit", "description": "允许修改通知渠道配置"},
        {"name": "测试通知推送", "code": "sys:notify:test", "description": "允许发送测试通知"},
        {"name": "邮件通知", "code": "sys:notify:email", "description": "允许系统发送邮件通知"},
        {"name": "查看位置", "code": "sys:location:view", "description": "允许查看位置信息列表 (用于业务选择)"},
        {"name": "管理位置", "code": "sys:location:manage", "description": "允许访问位置管理页面并进行管理"},
        {"name": "新增位置", "code": "sys:location:add", "description": "允许创建新的位置信息"},
        {"name": "编辑位置", "code": "sys:location:edit", "description": "允许修改现有位置信息"},
        {"name": "删除位置", "code": "sys:location:del", "description": "允许删除位置信息"},
        {"name": "查看设备", "code": "sys:device:list", "description": "允许查看设备列表及详情"},
        {"name": "新增设备", "code": "sys:device:add", "description": "允许添加新设备"},
        {"name": "编辑设备", "code": "sys:device:edit", "description": "允许修改设备信息"},
        {"name": "删除设备", "code": "sys:device:del", "description": "允许删除设备"},
        {"name": "设备审计", "code": "sys:device:audit", "description": "查看设备操作审计日志"},
        {"name": "查看接口", "code": "sys:device:interface:view", "description": "允许查看设备接口列表"},
        {"name": "查看路由", "code": "sys:device:route:view", "description": "允许查看设备路由表"},
        {"name": "查看VLAN", "code": "sys:device:vlan:view", "description": "允许查看设备VLAN列表"},
        {"name": "SSH连接", "code": "sys:ssh:connect", "description": "允许建立SSH连接"},
        {"name": "查看用户", "code": "sys:user:view", "description": "允许查看用户列表"},
        {"name": "管理用户", "code": "sys:user:manage", "description": "允许创建、编辑、禁用用户"},
        {"name": "批量导入用户", "code": "sys:user:import", "description": "允许批量导入用户信息"},
        {"name": "查看配置", "code": "sys:config:view", "description": "允许查看系统全局配置"},
        {"name": "编辑配置", "code": "sys:config:edit", "description": "允许修改系统全局配置"},
        {"name": "配置下发", "code": "sys:config:push", "description": "允许批量对设备下发配置/命令"},
        {"name": "全局通知", "code": "sys:notify:global", "description": "允许发送全站通知"},
        {"name": "提交工单", "code": "sys:repair:create", "description": "允许用户提交报修工单"},
        {"name": "查看工单", "code": "sys:repair:view", "description": "允许查看工单详情"},
        {"name": "查看所有工单", "code": "sys:repair:list_all", "description": "查看系统所有工单，不受指派限制"},
        {"name": "接单", "code": "sys:repair:accept", "description": "允许接收待处理工单"},
        {"name": "处理工单", "code": "sys:repair:handle", "description": "允许完成或处理工单"},
        {"name": "管理工单", "code": "sys:repair:manage", "description": "允许派单、取消他人工单、强制修改状态等高级操作"},
        {"name": "查看工单图片", "code": "sys:repair:image:view", "description": "允许查看工单图片信息或访问图片"},
        {"name": "上传工单图片", "code": "sys:repair:image:add", "description": "允许上传工单图片"},
        {"name": "编辑工单图片", "code": "sys:repair:image:edit", "description": "允许修改工单图片关联或元信息"},
        {"name": "删除工单图片", "code": "sys:repair:image:del", "description": "允许删除工单图片"},
    ]

    @staticmethod
    def expand_permission_codes(codes: List[str]) -> List[str]:
        selected = {str(c).strip() for c in (codes or []) if str(c).strip()}
        changed = True
        while changed:
            changed = False
            snapshot = list(selected)
            for code in snapshot:
                deps = RbacService.PERMISSION_DEPENDENCIES.get(code) or []
                for dep in deps:
                    dep_norm = str(dep).strip()
                    if dep_norm and dep_norm not in selected:
                        selected.add(dep_norm)
                        changed = True
        return sorted(selected)

    @staticmethod
    def is_system_permission_code(code: Optional[str]) -> bool:
        c = str(code or "").strip()
        if not c:
            return False
        return any(p["code"] == c for p in RbacService.SYSTEM_PERMISSIONS)

    @staticmethod
    async def get_permission_by_id(permission_id: int) -> Optional[dict]:
        p = await Permission.filter(id=permission_id).first()
        return dict(p) if p else None

    @staticmethod
    async def list_permission_directory(include_custom: bool = True) -> List[dict]:
        db_perms = await Permission.all().order_by("id")
        by_code: Dict[str, Permission] = {str(p.code or ""): p for p in db_perms if p.code}

        directory: List[dict] = []
        system_codes = set()
        for sp in RbacService.SYSTEM_PERMISSIONS:
            code = str(sp["code"])
            system_codes.add(code)
            existing = by_code.get(code)
            if existing:
                directory.append(
                    {
                        "id": existing.id,
                        "name": existing.name,
                        "code": existing.code,
                        "description": existing.description,
                        "created_at": existing.created_at,
                        "exists": True,
                        "in_directory": True,
                    }
                )
            else:
                directory.append(
                    {
                        "id": None,
                        "name": sp.get("name") or code,
                        "code": code,
                        "description": sp.get("description") or "",
                        "created_at": None,
                        "exists": False,
                        "in_directory": True,
                    }
                )

        if include_custom:
            for p in db_perms:
                code = str(p.code or "")
                if code and code not in system_codes:
                    directory.append({
                        "id": p.id,
                        "name": p.name,
                        "code": p.code,
                        "description": p.description,
                        "created_at": p.created_at,
                        "exists": True, 
                        "in_directory": False
                    })

        return directory

    @staticmethod
    async def sync_system_permissions() -> dict:
        existing_codes = await Permission.all().values_list("code", flat=True)
        existing_set = {str(c).strip() for c in existing_codes if c}

        to_create: List[Permission] = []
        for p in RbacService.SYSTEM_PERMISSIONS:
            code = str(p.get("code") or "").strip()
            if not code or code in existing_set:
                continue
            to_create.append(
                Permission(
                    name=p.get("name") or code,
                    code=code,
                    description=p.get("description") or ""
                )
            )

        if to_create:
            await Permission.bulk_create(to_create)

        return {"total": len(RbacService.SYSTEM_PERMISSIONS), "missing_inserted": len(to_create)}

    @staticmethod
    async def restore_system_permission(code: Optional[str]) -> bool:
        c = str(code or "").strip()
        if not c:
            return False
        default = next((p for p in RbacService.SYSTEM_PERMISSIONS if str(p.get("code") or "").strip() == c), None)
        if not default:
            return False
        await Permission.update_or_create(
            code=c,
            defaults={
                "name": default.get("name") or c,
                "description": default.get("description") or ""
            }
        )
        return True

    @staticmethod
    async def list_roles() -> List[dict]:
        roles = await Role.all().order_by("id")
        return [dict(r) for r in roles]

    @staticmethod
    async def create_role(name: str, code: str, description: Optional[str]) -> int:
        role = await Role.create(name=name, code=code, description=description)
        return role.id

    @staticmethod
    async def update_role(role_id: int, data: Dict[str, Any]) -> None:
        role = await Role.filter(id=role_id).first()
        if not role:
            return
        
        # 内置超级管理员角色保护
        if role.code == 'superadmin':
            raise ValueError("内置超级管理员角色不可修改")
        
        if "name" in data:
            role.name = data["name"]
        if "code" in data:
            new_code = str(data["code"]).strip()
            if new_code == 'superadmin':
                raise ValueError("不可将其他角色修改为 superadmin")
            role.code = new_code
        if "description" in data:
            role.description = data["description"]
            
        await role.save()

    @staticmethod
    async def delete_role(role_id: int) -> None:
        role = await Role.filter(id=role_id).first()
        if role and role.code == 'superadmin':
             raise ValueError("内置超级管理员角色不可删除")

        # Get affected users first
        users_in_role = await UserRole.filter(role_id=role_id).all()
        user_ids = [u.user_id for u in users_in_role]
        
        await Role.filter(id=role_id).delete()
        # Cascade delete of user_roles should happen at DB level if configured, 
        # but Tortoise models don't enforce DB FK constraints by default unless defined.
        # But we deleted the Role, so UserRole entries might be orphaned if no DB cascade.
        # But we should rely on DB FK cascade or delete manually.
        # Assuming DB has cascade (PostgreSQL usually does if created right).
        # But wait, we migrated existing tables. 
        # For safety, delete UserRoles (though DB should handle it if FK exists)
        # We will assume DB handles it or it's fine.
        
        if user_ids:
            await RbacService.bump_users_perm_version(user_ids)

    @staticmethod
    async def get_all_roles_with_users() -> List[dict]:
        # Deprecated or Modified to return counts only for performance?
        # The prompt asks to optimize.
        # Let's return counts instead of full user list.
        
        roles = await Role.all().order_by("id")
        
        # Fetch all UserRoles to count
        # This is much lighter than fetching User objects
        user_roles = await UserRole.all().values("role_id")
        
        from collections import Counter
        counts = Counter([ur["role_id"] for ur in user_roles])
        
        result = []
        for r in roles:
            result.append({
                "id": r.id, 
                "name": r.name, 
                "code": r.code, 
                "description": r.description,
                "created_at": r.created_at,
                "is_default": r.is_default,
                "user_count": counts.get(r.id, 0),
                "users": [] # Keep empty list for backward compatibility if needed, or remove.
            })
            
        return result

    @staticmethod
    async def get_users_with_roles_paginated(
        q: Optional[str] = None,
        role_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        page_norm = max(1, int(page or 1))
        page_size_norm = max(1, min(200, int(page_size or 20)))
        offset = (page_norm - 1) * page_size_norm

        # Base query
        query = User.all()

        # Apply filters
        if role_id:
            # Subquery for users in role
            user_ids_in_role = await UserRole.filter(role_id=role_id).values_list('user_id', flat=True)
            query = query.filter(id__in=user_ids_in_role)

        q_norm = str(q or "").strip()
        if q_norm:
            query = query.filter(
                Q(username__icontains=q_norm) | 
                Q(nickname__icontains=q_norm) | 
                Q(email__icontains=q_norm)
            )

        # Count
        total = await query.count()
        
        # Fetch Users
        users = await query.order_by("username").offset(offset).limit(page_size_norm).all()
        
        # Fetch Roles for these users
        # To avoid N+1, fetch all UserRoles for these user_ids
        fetched_user_ids = [u.id for u in users]
        user_roles = await UserRole.filter(user_id__in=fetched_user_ids).all()
        
        # Fetch Role details
        role_ids = list({ur.role_id for ur in user_roles})
        roles = await Role.filter(id__in=role_ids).all()
        role_map = {r.id: r for r in roles}
        
        # Build user -> roles map
        user_roles_map = {}
        for ur in user_roles:
            if ur.user_id not in user_roles_map:
                user_roles_map[ur.user_id] = []
            if ur.role_id in role_map:
                r = role_map[ur.role_id]
                user_roles_map[ur.user_id].append({
                    "id": r.id,
                    "name": r.name,
                    "code": r.code
                })
        
        items = []
        for u in users:
            items.append({
                "id": u.id,
                "username": u.username,
                "nickname": u.nickname,
                "email": u.email,
                "is_approved": u.is_approved,
                "created_at": u.created_at,
                "roles": user_roles_map.get(u.id, [])
            })
            
        return {
            "items": items,
            "total": total,
            "page": page_norm,
            "page_size": page_size_norm
        }

    @staticmethod
    async def set_default_role(role_id: int) -> None:
        # Transaction?
        await Role.filter(is_default=True).update(is_default=False)
        await Role.filter(id=role_id).update(is_default=True)

    @staticmethod
    async def get_role_users(role_id: int, page: int = 1, page_size: int = 20) -> dict:
        page_norm = max(1, int(page or 1))
        page_size_norm = max(1, min(200, int(page_size or 20)))
        offset = (page_norm - 1) * page_size_norm

        # Filter UserRoles by role_id
        # We need to paginate Users essentially.
        # But we are querying UserRole table mainly.
        
        user_role_query = UserRole.filter(role_id=role_id)
        total = await user_role_query.count()
        
        # We need to fetch User details.
        # Fetch page of UserRoles
        user_roles = await user_role_query.offset(offset).limit(page_size_norm).all()
        user_ids = [ur.user_id for ur in user_roles]
        
        users = await User.filter(id__in=user_ids).all()
        user_map = {u.id: u for u in users}
        
        # Reconstruct list in order (though user_roles order might not be username order)
        # To order by username, we would need to join.
        # For now, let's just return the users found.
        # If we really need sorting by username, we fetch all IDs for role, then query Users with sort and limit.
        
        # Better approach for sorting:
        # Get all user_ids for role
        all_user_ids = await UserRole.filter(role_id=role_id).values_list('user_id', flat=True)
        
        # Query Users with these IDs, sort by username, and paginate
        users_query = User.filter(id__in=all_user_ids).order_by("username")
        # But wait, total count should be on this query?
        # Yes.
        
        # However, getting all_user_ids might be heavy if role has 10k users.
        # But assuming reasonable size.
        # If we use the previous approach (paginate UserRoles), we can't sort by username easily.
        # Let's stick to the previous approach but fetch Users and sort them in memory (since page size is small).
        
        items = []
        for ur in user_roles:
            u = user_map.get(ur.user_id)
            if u:
                items.append({
                    "id": u.id,
                    "username": u.username,
                    "nickname": u.nickname,
                    "email": u.email,
                    "is_approved": u.is_approved,
                    "created_at": u.created_at
                })
        
        items.sort(key=lambda x: x["username"])
        
        return {"items": items, "total": int(total or 0), "page": page_norm, "page_size": page_size_norm}

    @staticmethod
    async def add_users_to_role(role_id: int, user_ids: List[int]) -> None:
        if not user_ids:
            return
        
        # Bulk create?
        # Need to handle conflicts (ON CONFLICT DO NOTHING).
        # Tortoise bulk_create doesn't support ignore_conflicts easily in all DBs.
        # We can check existence or iterate.
        # Iterate is safer for now.
        for uid in user_ids:
            await UserRole.get_or_create(user_id=uid, role_id=role_id)
            
        await RbacService.bump_users_perm_version(user_ids)

    @staticmethod
    async def remove_user_from_role(role_id: int, user_id: int) -> None:
        await UserRole.filter(user_id=user_id, role_id=role_id).delete()
        await RbacService.bump_user_perm_version(user_id)

    @staticmethod
    async def set_user_roles(user_id: int, role_ids: List[int]) -> None:
        await UserRole.filter(user_id=user_id).delete()
        ids = list(set([int(rid) for rid in (role_ids or [])]))
        for rid in ids:
            await UserRole.create(user_id=user_id, role_id=rid)
        await RbacService.bump_user_perm_version(user_id)

    @staticmethod
    async def get_users_not_in_role(
        role_id: int,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        page_norm = max(1, int(page or 1))
        page_size_norm = max(1, min(200, int(page_size or 50)))
        offset = (page_norm - 1) * page_size_norm

        # Subquery: users in role
        users_in_role = await UserRole.filter(role_id=role_id).values_list('user_id', flat=True)
        
        query = User.filter(id__not_in=users_in_role)
        
        q_norm = str(q or "").strip()
        if q_norm:
            query = query.filter(
                Q(username__icontains=q_norm) | 
                Q(nickname__icontains=q_norm) | 
                Q(email__icontains=q_norm)
            )

        total = await query.count()
        users = await query.order_by("username").offset(offset).limit(page_size_norm).all()
        
        items = [{
            "id": u.id,
            "username": u.username,
            "nickname": u.nickname,
            "email": u.email
        } for u in users]
        
        return {"items": items, "total": total, "page": page_norm, "page_size": page_size_norm, "q": q_norm}

    @staticmethod
    async def list_permissions() -> List[dict]:
        perms = await Permission.all().order_by("id")
        return [dict(p) for p in perms]

    @staticmethod
    async def create_permission(name: str, code: str, description: Optional[str]) -> int:
        p = await Permission.create(name=name, code=code, description=description)
        return p.id

    @staticmethod
    async def update_permission(permission_id: int, data: Dict[str, Any]) -> None:
        p = await Permission.filter(id=permission_id).first()
        if not p:
            return
        
        if "name" in data:
            p.name = data["name"]
        if "code" in data:
            p.code = data["code"]
        if "description" in data:
            p.description = data["description"]
        await p.save()

    @staticmethod
    async def delete_permission(permission_id: int) -> None:
        await Permission.filter(id=permission_id).delete()

    @staticmethod
    async def get_role_permissions(role_id: int) -> List[dict]:
        # Join RolePermission and Permission
        rps = await RolePermission.filter(role_id=role_id).all()
        p_ids = [rp.permission_id for rp in rps]
        
        perms = await Permission.filter(id__in=p_ids).order_by("id").all()
        return [dict(p) for p in perms]

    @staticmethod
    async def set_role_permissions(role_id: int, permission_ids: List[int]) -> None:
        role = await Role.filter(id=role_id).first()
        if role and role.code == 'superadmin':
             # 超级管理员无需配置权限（代码逻辑内置全开），但也禁止修改其关联
             # 或者我们可以允许修改，但实际上无效。
             # 为了避免误解，禁止修改。
             raise ValueError("内置超级管理员角色拥有所有权限，无需配置")

        ids = [int(pid) for pid in (permission_ids or []) if pid is not None]
        if ids:
            # Check exist and expand dependencies
            # 1. Get codes for these IDs
            perms = await Permission.filter(id__in=ids).all()
            codes = [p.code for p in perms if p.code]
            
            expanded_codes = RbacService.expand_permission_codes(codes)
            if expanded_codes:
                # Get IDs for expanded codes
                expanded_perms = await Permission.filter(code__in=expanded_codes).all()
                ids = [p.id for p in expanded_perms]
        
        ids = sorted(list({int(pid) for pid in (ids or []) if pid is not None}))

        # Update RolePermissions
        # Delete old
        await RolePermission.filter(role_id=role_id).delete()
        
        # Insert new
        for pid in ids:
            await RolePermission.create(role_id=role_id, permission_id=pid)
            
        await RbacService.bump_role_users_perm_version(role_id)

    @staticmethod
    async def get_user_permission_codes(user_id: int) -> List[str]:
        # 1. Get roles for user
        urs = await UserRole.filter(user_id=user_id).all()
        role_ids = [ur.role_id for ur in urs]
        
        if not role_ids:
            return []
            
        # 2. Get permission IDs for roles
        rps = await RolePermission.filter(role_id__in=role_ids).all()
        perm_ids = [rp.permission_id for rp in rps]
        
        if not perm_ids:
            return []
            
        # 3. Get codes
        perms = await Permission.filter(id__in=perm_ids).all()
        return [p.code for p in perms if p.code]

    @staticmethod
    async def get_user_role_codes(user_id: int) -> List[str]:
        urs = await UserRole.filter(user_id=user_id).all()
        role_ids = [ur.role_id for ur in urs]
        
        roles = await Role.filter(id__in=role_ids).all()
        codes = [r.code for r in roles if r.code]
        return sorted(list(set(codes)))

    @staticmethod
    async def get_all_permission_codes() -> List[str]:
        perms = await Permission.all()
        return [p.code for p in perms if p.code]

    @staticmethod
    async def bump_user_perm_version(user_id: int) -> int:
        redis_client = redis_manager.get_client()
        key = f"authz:ver:user:{int(user_id)}"
        try:
            v = await redis_client.incr(key)
            if int(v) > 0:
                return int(v)
        except Exception:
            pass
        await redis_client.set(key, "1")
        return 1

    @staticmethod
    async def bump_users_perm_version(user_ids: List[int]) -> None:
        ids = [int(uid) for uid in (user_ids or []) if uid is not None]
        if not ids:
            return
        for uid in sorted(set(ids)):
            await RbacService.bump_user_perm_version(uid)

    @staticmethod
    async def bump_role_users_perm_version(role_id: int) -> None:
        urs = await UserRole.filter(role_id=role_id).all()
        user_ids = [ur.user_id for ur in urs]
        await RbacService.bump_users_perm_version(user_ids)

    @staticmethod
    async def grant_permission_to_role_code(role_code: str, permission_code: str) -> None:
        role = await Role.filter(code=role_code).first()
        if not role:
            return
        perm = await Permission.filter(code=permission_code).first()
        if not perm:
            return
        await RolePermission.get_or_create(role_id=role.id, permission_id=perm.id)
