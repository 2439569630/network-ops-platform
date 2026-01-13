from typing import List, Optional, Dict, Any
from app.core.database import db
from app.core.redis import redis_manager


class RbacService:
    """
    基于角色的访问控制(RBAC)服务类
    提供权限管理、角色管理以及用户权限验证等功能
    """
    # 权限依赖关系字典，定义了某些权限所需的前置权限
    PERMISSION_DEPENDENCIES: Dict[str, List[str]] = {
        "sys:location:add": ["sys:location:view"],
        "sys:location:edit": ["sys:location:view"],
        "sys:location:del": ["sys:location:view"],
        "sys:device:add": ["sys:device:list"],
        "sys:device:edit": ["sys:device:list"],
        "sys:device:del": ["sys:device:list"],
        "sys:device:audit": ["sys:device:list"],
        "sys:user:manage": ["sys:user:view"],
        "sys:user:import": ["sys:user:manage"],
        "sys:config:edit": ["sys:config:view"],
        "sys:repair:create": ["sys:repair:view"],
        "sys:repair:handle": ["sys:repair:view"],
        "sys:repair:manage": ["sys:repair:view", "sys:repair:handle"],
    }

    # 系统预定义权限列表
    SYSTEM_PERMISSIONS: List[Dict[str, str]] = [
        {"name": "登录", "code": "sys:auth:login", "description": ""},
        {"name": "注册", "code": "sys:auth:register", "description": ""},
        {"name": "邮箱验证", "code": "sys:email:verify", "description": ""},
        {"name": "系统概览", "code": "sys:dashboard:view", "description": ""},
        {"name": "查看监控", "code": "sys:monitor:view", "description": ""},
        {"name": "消息中心", "code": "sys:message:access", "description": ""},
        {"name": "订阅实时告警", "code": "sys:alert:subscribe", "description": ""},
        {"name": "查看通知历史", "code": "sys:notify:history", "description": ""},
        {"name": "查看通知配置", "code": "sys:notify:config:view", "description": ""},
        {"name": "编辑通知配置", "code": "sys:notify:config:edit", "description": ""},
        {"name": "测试通知推送", "code": "sys:notify:test", "description": ""},
        {"name": "查看位置", "code": "sys:location:view", "description": ""},
        {"name": "新增位置", "code": "sys:location:add", "description": ""},
        {"name": "编辑位置", "code": "sys:location:edit", "description": ""},
        {"name": "删除位置", "code": "sys:location:del", "description": ""},
        {"name": "查看设备", "code": "sys:device:list", "description": ""},
        {"name": "新增设备", "code": "sys:device:add", "description": ""},
        {"name": "编辑设备", "code": "sys:device:edit", "description": ""},
        {"name": "删除设备", "code": "sys:device:del", "description": ""},
        {"name": "设备审计", "code": "sys:device:audit", "description": "查看设备操作审计日志"},
        {"name": "SSH连接", "code": "sys:ssh:connect", "description": ""},
        {"name": "查看用户", "code": "sys:user:view", "description": ""},
        {"name": "管理用户", "code": "sys:user:manage", "description": ""},
        {"name": "批量导入用户", "code": "sys:user:import", "description": ""},
        {"name": "查看配置", "code": "sys:config:view", "description": ""},
        {"name": "编辑配置", "code": "sys:config:edit", "description": ""},
        {"name": "全局通知", "code": "sys:notify:global", "description": ""},
        {"name": "提交工单", "code": "sys:repair:create", "description": ""},
        {"name": "查看工单", "code": "sys:repair:view", "description": ""},
        {"name": "处理工单", "code": "sys:repair:handle", "description": ""},
        {"name": "管理工单", "code": "sys:repair:manage", "description": ""},
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
        row = await db.fetch_one(
            "SELECT id, name, code, description, created_at FROM permissions WHERE id = $1",
            permission_id,
        )
        return dict(row) if row else None

    @staticmethod
    async def list_permission_directory(include_custom: bool = True) -> List[dict]:
        db_rows = await db.fetch_all(
            "SELECT id, name, code, description, created_at FROM permissions ORDER BY id"
        )
        db_perms = [dict(r) for r in db_rows] if db_rows else []
        by_code: Dict[str, dict] = {str(p.get("code") or ""): p for p in db_perms if p.get("code")}

        directory: List[dict] = []
        system_codes = set()
        for sp in RbacService.SYSTEM_PERMISSIONS:
            code = str(sp["code"])
            system_codes.add(code)
            existing = by_code.get(code)
            if existing:
                directory.append(
                    {
                        **existing,
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
                code = str(p.get("code") or "")
                if code and code not in system_codes:
                    directory.append({**p, "exists": True, "in_directory": False})

        return directory

    @staticmethod
    async def sync_system_permissions() -> dict:
        existing_codes = set(await RbacService.get_all_permission_codes())
        missing = [p for p in RbacService.SYSTEM_PERMISSIONS if p["code"] not in existing_codes]

        for p in RbacService.SYSTEM_PERMISSIONS:
            await db.execute(
                """
                INSERT INTO permissions (name, code, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
                """,
                p["name"],
                p["code"],
                p.get("description") or "",
            )

        return {"total": len(RbacService.SYSTEM_PERMISSIONS), "missing_inserted": len(missing)}

    @staticmethod
    async def list_roles() -> List[dict]:
        rows = await db.fetch_all(
            "SELECT id, name, code, description, created_at, is_default FROM roles ORDER BY id"
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def create_role(name: str, code: str, description: Optional[str]) -> int:
        return await db.fetch_val(
            "INSERT INTO roles (name, code, description) VALUES ($1, $2, $3) RETURNING id",
            name,
            code,
            description,
        )

    @staticmethod
    async def update_role(role_id: int, data: Dict[str, Any]) -> None:
        fields = []
        values: List[Any] = []
        idx = 1
        for key in ["name", "code", "description"]:
            if data.get(key) is not None:
                fields.append(f"{key} = ${idx}")
                values.append(data[key])
                idx += 1
        if not fields:
            return
        values.append(role_id)
        await db.execute(f"UPDATE roles SET {', '.join(fields)} WHERE id = ${idx}", *values)

    @staticmethod
    async def delete_role(role_id: int) -> None:
        rows = await db.fetch_all("SELECT DISTINCT user_id FROM user_roles WHERE role_id = $1", role_id)
        user_ids = [int(r["user_id"]) for r in (rows or []) if r and r.get("user_id") is not None]
        await db.execute("DELETE FROM roles WHERE id = $1", role_id)
        if user_ids:
            await RbacService.bump_users_perm_version(user_ids)

    @staticmethod
    async def get_all_roles_with_users() -> List[dict]:
        # 1. 获取所有角色
        roles = await RbacService.list_roles()
        
        # 2. 获取所有 role-user 映射 (包括用户信息)
        rows = await db.fetch_all(
            """
            SELECT ur.role_id, u.id, u.username, u.nickname
            FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            ORDER BY u.username
            """
        )
        
        # 3. 组装数据
        role_map = {r["id"]: {**r, "users": []} for r in roles}
        
        for row in rows:
            rid = row["role_id"]
            if rid in role_map:
                role_map[rid]["users"].append({
                    "id": row["id"],
                    "username": row["username"],
                    "nickname": row["nickname"]
                })
                
        return list(role_map.values())

    @staticmethod
    async def set_default_role(role_id: int) -> None:
        pool = db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE roles SET is_default = FALSE WHERE is_default = TRUE")
                await conn.execute("UPDATE roles SET is_default = TRUE WHERE id = $1", role_id)

    @staticmethod
    async def get_role_users(role_id: int, page: int = 1, page_size: int = 20) -> dict:
        page_norm = max(1, int(page or 1))
        page_size_norm = max(1, min(200, int(page_size or 20)))
        offset = (page_norm - 1) * page_size_norm

        total = await db.fetch_val(
            "SELECT COUNT(*) FROM user_roles ur WHERE ur.role_id = $1",
            role_id,
        )
        rows = await db.fetch_all(
            """
            SELECT u.id, u.username, u.nickname, u.email, u.is_approved, u.created_at
            FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE ur.role_id = $1
            ORDER BY u.username
            LIMIT $2 OFFSET $3
            """,
            role_id,
            page_size_norm,
            offset,
        )
        items = [dict(r) for r in rows] if rows else []
        return {"items": items, "total": int(total or 0), "page": page_norm, "page_size": page_size_norm}

    @staticmethod
    async def add_users_to_role(role_id: int, user_ids: List[int]) -> None:
        if not user_ids:
            return
        pool = db.get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                [(uid, role_id) for uid in user_ids],
            )
        await RbacService.bump_users_perm_version(user_ids)

    @staticmethod
    async def remove_user_from_role(role_id: int, user_id: int) -> None:
        await db.execute(
            "DELETE FROM user_roles WHERE user_id = $1 AND role_id = $2",
            user_id,
            role_id,
        )
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

        where_clauses = [
            "u.id NOT IN (SELECT ur.user_id FROM user_roles ur WHERE ur.role_id = $1)"
        ]
        values: List[Any] = [role_id]
        idx = 2

        q_norm = str(q or "").strip()
        if q_norm:
            where_clauses.append(
                f"(u.username ILIKE ${idx} OR u.nickname ILIKE ${idx} OR u.email ILIKE ${idx})"
            )
            values.append(f"%{q_norm}%")
            idx += 1

        where_sql = " AND ".join(where_clauses)

        total = await db.fetch_val(
            f"SELECT COUNT(*) FROM users u WHERE {where_sql}",
            *values,
        )

        values_with_page = [*values, page_size_norm, offset]
        rows = await db.fetch_all(
            f"""
            SELECT u.id, u.username, u.nickname, u.email
            FROM users u
            WHERE {where_sql}
            ORDER BY u.username
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *values_with_page,
        )
        items = [dict(r) for r in rows] if rows else []
        return {"items": items, "total": int(total or 0), "page": page_norm, "page_size": page_size_norm, "q": q_norm}

    @staticmethod
    async def list_permissions() -> List[dict]:
        rows = await db.fetch_all(
            "SELECT id, name, code, description, created_at FROM permissions ORDER BY id"
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def create_permission(name: str, code: str, description: Optional[str]) -> int:
        return await db.fetch_val(
            "INSERT INTO permissions (name, code, description) VALUES ($1, $2, $3) RETURNING id",
            name,
            code,
            description,
        )

    @staticmethod
    async def update_permission(permission_id: int, data: Dict[str, Any]) -> None:
        fields = []
        values: List[Any] = []
        idx = 1
        for key in ["name", "code", "description"]:
            if data.get(key) is not None:
                fields.append(f"{key} = ${idx}")
                values.append(data[key])
                idx += 1
        if not fields:
            return
        values.append(permission_id)
        await db.execute(
            f"UPDATE permissions SET {', '.join(fields)} WHERE id = ${idx}",
            *values,
        )

    @staticmethod
    async def delete_permission(permission_id: int) -> None:
        await db.execute("DELETE FROM permissions WHERE id = $1", permission_id)

    @staticmethod
    async def get_role_permissions(role_id: int) -> List[dict]:
        rows = await db.fetch_all(
            """
            SELECT p.id, p.name, p.code, p.description, p.created_at
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = $1
            ORDER BY p.id
            """,
            role_id,
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def set_role_permissions(role_id: int, permission_ids: List[int]) -> None:
        ids = [int(pid) for pid in (permission_ids or []) if pid is not None]
        if ids:
            rows = await db.fetch_all(
                "SELECT id, code FROM permissions WHERE id = ANY($1::int[])",
                ids,
            )
            codes = [str(r.get("code")) for r in (rows or []) if r and r.get("code")]
            expanded_codes = RbacService.expand_permission_codes(codes)
            if expanded_codes:
                expanded_rows = await db.fetch_all(
                    "SELECT id FROM permissions WHERE code = ANY($1::text[])",
                    expanded_codes,
                )
                ids = [int(r["id"]) for r in (expanded_rows or []) if r and r.get("id") is not None]
        ids = sorted(list({int(pid) for pid in (ids or []) if pid is not None}))

        pool = db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM role_permissions WHERE role_id = $1", role_id)
                if ids:
                    await conn.executemany(
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES ($1, $2)",
                        [(role_id, pid) for pid in ids],
                    )
        await RbacService.bump_role_users_perm_version(role_id)

    @staticmethod
    async def get_user_permission_codes(user_id: int) -> List[str]:
        rows = await db.fetch_all(
            """
            SELECT DISTINCT p.code
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = $1
            """,
            user_id,
        )
        return [r["code"] for r in rows] if rows else []

    @staticmethod
    async def get_user_role_codes(user_id: int) -> List[str]:
        rows = await db.fetch_all(
            """
            SELECT DISTINCT r.code
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = $1
            """,
            user_id,
        )
        codes = [str(r["code"]) for r in rows if r and r.get("code")] if rows else []
        return sorted(list({c for c in codes if str(c).strip()}))

    @staticmethod
    async def get_all_permission_codes() -> List[str]:
        rows = await db.fetch_all("SELECT code FROM permissions")
        return [r["code"] for r in rows] if rows else []

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
        rows = await db.fetch_all("SELECT DISTINCT user_id FROM user_roles WHERE role_id = $1", int(role_id))
        user_ids = [int(r["user_id"]) for r in (rows or []) if r and r.get("user_id") is not None]
        await RbacService.bump_users_perm_version(user_ids)
