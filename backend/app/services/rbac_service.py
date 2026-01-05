from typing import List, Optional, Dict, Any
from app.core.database import db


class RbacService:
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
        await db.execute("DELETE FROM roles WHERE id = $1", role_id)

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
    async def get_role_users(role_id: int) -> List[dict]:
        rows = await db.fetch_all(
            """
            SELECT u.id, u.username, u.nickname, u.email, u.permission_level, u.is_approved, u.created_at
            FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE ur.role_id = $1
            ORDER BY u.username
            """,
            role_id,
        )
        return [dict(r) for r in rows] if rows else []

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

    @staticmethod
    async def remove_user_from_role(role_id: int, user_id: int) -> None:
        await db.execute(
            "DELETE FROM user_roles WHERE user_id = $1 AND role_id = $2",
            user_id,
            role_id,
        )

    @staticmethod
    async def get_users_not_in_role(role_id: int) -> List[dict]:
        rows = await db.fetch_all(
            """
            SELECT u.id, u.username, u.nickname, u.email
            FROM users u
            WHERE u.id NOT IN (SELECT ur.user_id FROM user_roles ur WHERE ur.role_id = $1)
            ORDER BY u.username
            """,
            role_id,
        )
        return [dict(r) for r in rows] if rows else []

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
        pool = db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM role_permissions WHERE role_id = $1", role_id)
                if permission_ids:
                    await conn.executemany(
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES ($1, $2)",
                        [(role_id, pid) for pid in permission_ids],
                    )

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
    async def get_all_permission_codes() -> List[str]:
        rows = await db.fetch_all("SELECT code FROM permissions")
        return [r["code"] for r in rows] if rows else []
