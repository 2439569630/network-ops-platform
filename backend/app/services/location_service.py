import re
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from app.core.database import db


class LocationService:
    _tables_ready: bool = False
    _auto_code_re = re.compile(r"^[0-9A-Fa-f]+(\.[0-9A-Fa-f]+)*$")

    @staticmethod
    async def _ensure_tables() -> None:
        if LocationService._tables_ready:
            return

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS location_nodes (
                id BIGSERIAL PRIMARY KEY,
                parent_id BIGINT REFERENCES location_nodes(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                code TEXT,
                manager_dept TEXT,
                manager TEXT,
                phone TEXT,
                capacity INTEGER,
                area DOUBLE PRECISION,
                address TEXT,
                description TEXT,
                status BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS location_node_roles (
                node_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                PRIMARY KEY (node_id, role_id)
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_location_node_roles_node ON location_node_roles(node_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_location_node_roles_role ON location_node_roles(role_id)")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS location_node_users (
                node_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                PRIMARY KEY (node_id, user_id)
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_location_node_users_node ON location_node_users(node_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_location_node_users_user ON location_node_users(user_id)")

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_location_nodes_parent_sort ON location_nodes(parent_id, sort_order, id)"
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_location_nodes_code ON location_nodes(code)")
        await db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_location_nodes_code_nonempty
            ON location_nodes (code)
            WHERE code IS NOT NULL AND btrim(code) <> ''
            """
        )

        LocationService._tables_ready = True

    @staticmethod
    def _normalize_optional_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        return s or None

    @staticmethod
    def _normalize_id_list(value: Any) -> List[int]:
        if value is None:
            return []
        if isinstance(value, (int, float, str)):
            try:
                n = int(value)
                return [n] if n > 0 else []
            except Exception:
                return []
        if isinstance(value, list):
            out: List[int] = []
            for item in value:
                try:
                    n = int(item)
                except Exception:
                    continue
                if n > 0:
                    out.append(n)
            seen = set()
            uniq: List[int] = []
            for n in out:
                if n in seen:
                    continue
                seen.add(n)
                uniq.append(n)
            return uniq
        return []

    @staticmethod
    async def _get_bindings_map(node_ids: List[int]) -> Tuple[Dict[int, List[int]], Dict[int, List[int]]]:
        ids = [int(x) for x in (node_ids or []) if x is not None]
        if not ids:
            return {}, {}

        role_rows = await db.fetch_all(
            """
            SELECT node_id, role_id
            FROM location_node_roles
            WHERE node_id = ANY($1::bigint[])
            ORDER BY node_id, role_id
            """,
            ids,
        )
        user_rows = await db.fetch_all(
            """
            SELECT node_id, user_id
            FROM location_node_users
            WHERE node_id = ANY($1::bigint[])
            ORDER BY node_id, user_id
            """,
            ids,
        )

        role_map: Dict[int, List[int]] = {}
        for r in role_rows or []:
            nid = int(r["node_id"])
            role_map.setdefault(nid, []).append(int(r["role_id"]))

        user_map: Dict[int, List[int]] = {}
        for r in user_rows or []:
            nid = int(r["node_id"])
            user_map.setdefault(nid, []).append(int(r["user_id"]))

        return role_map, user_map

    @staticmethod
    async def _set_node_bindings(*, node_id: int, role_ids: Optional[List[int]] = None, user_ids: Optional[List[int]] = None) -> None:
        nid = int(node_id)
        if role_ids is not None:
            ids = LocationService._normalize_id_list(role_ids)
            await db.execute("DELETE FROM location_node_roles WHERE node_id = $1", nid)
            for rid in ids:
                await db.execute(
                    "INSERT INTO location_node_roles(node_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    nid,
                    int(rid),
                )
        if user_ids is not None:
            ids = LocationService._normalize_id_list(user_ids)
            await db.execute("DELETE FROM location_node_users WHERE node_id = $1", nid)
            for uid in ids:
                await db.execute(
                    "INSERT INTO location_node_users(node_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    nid,
                    int(uid),
                )

    @staticmethod
    def _is_auto_code(code: Optional[str]) -> bool:
        if not code:
            return False
        c = str(code).strip()
        if not c:
            return False
        return bool(LocationService._auto_code_re.fullmatch(c))

    @staticmethod
    def _split_code_segments(code: str) -> List[str]:
        return [seg for seg in str(code).strip().split(".") if seg]

    @staticmethod
    def _join_code_segments(segs: List[str]) -> str:
        return ".".join(segs)

    @staticmethod
    async def _get_node_brief(node_id: int) -> Optional[dict]:
        row = await db.fetch_one(
            "SELECT id, parent_id, code FROM location_nodes WHERE id = $1",
            int(node_id),
        )
        return dict(row) if row else None

    @staticmethod
    async def _next_auto_child_number(*, parent_id: Optional[int], parent_code: Optional[str]) -> int:
        parent_code_norm = LocationService._normalize_optional_str(parent_code)
        parent_depth = len(LocationService._split_code_segments(parent_code_norm)) if parent_code_norm else 0

        rows = await db.fetch_all(
            """
            SELECT code
            FROM location_nodes
            WHERE parent_id IS NOT DISTINCT FROM $1
              AND code IS NOT NULL
              AND btrim(code) <> ''
            """,
            int(parent_id) if parent_id is not None else None,
        )

        max_n = -1
        for r in rows or []:
            code = LocationService._normalize_optional_str(r.get("code"))
            if not code:
                continue
            segs = LocationService._split_code_segments(code)
            if len(segs) != parent_depth + 1:
                continue
            if parent_code_norm:
                if LocationService._join_code_segments(segs[:-1]) != parent_code_norm:
                    continue
            try:
                n = int(segs[-1], 16)
            except Exception:
                continue
            if n > max_n:
                max_n = n
        return max_n + 1

    @staticmethod
    async def _ensure_node_has_code(node_id: int) -> Optional[str]:
        node = await LocationService._get_node_brief(int(node_id))
        if not node:
            return None
        existing = LocationService._normalize_optional_str(node.get("code"))
        if existing:
            return existing

        parent_id = node.get("parent_id")
        parent_code = None
        if parent_id is not None:
            parent_code = await LocationService._ensure_node_has_code(int(parent_id))

        for _ in range(20):
            n = await LocationService._next_auto_child_number(parent_id=int(parent_id) if parent_id is not None else None, parent_code=parent_code)
            seg = format(int(n), "X")
            new_code = seg if not parent_code else f"{parent_code}.{seg}"
            try:
                exists = await db.fetch_val(
                    "SELECT 1 FROM location_nodes WHERE code = $1 AND id <> $2 LIMIT 1",
                    new_code,
                    int(node_id),
                )
                if exists:
                    continue
                await db.execute(
                    "UPDATE location_nodes SET code = $1, updated_at = NOW() WHERE id = $2",
                    new_code,
                    int(node_id),
                )
                return new_code
            except asyncpg.exceptions.UniqueViolationError:
                continue
        raise ValueError("生成位置编码失败：重复冲突过多")

    @staticmethod
    async def _generate_code_for_new_node(parent_id: Optional[int]) -> str:
        parent_code = None
        if parent_id is not None:
            parent_code = await LocationService._ensure_node_has_code(int(parent_id))

        for _ in range(20):
            n = await LocationService._next_auto_child_number(parent_id=int(parent_id) if parent_id is not None else None, parent_code=parent_code)
            seg = format(int(n), "X")
            code = seg if not parent_code else f"{parent_code}.{seg}"
            exists = await db.fetch_val(
                "SELECT 1 FROM location_nodes WHERE code = $1 LIMIT 1",
                code,
            )
            if exists:
                try:
                    await db.execute("SELECT 1")
                except Exception:
                    pass
                continue
            return code
        raise ValueError("生成位置编码失败：可用编码耗尽或冲突过多")

    @staticmethod
    def _row_to_node(row: dict) -> dict:
        return {
            "id": int(row["id"]),
            "parent_id": int(row["parent_id"]) if row.get("parent_id") is not None else None,
            "label": row.get("name"),
            "type": row.get("type"),
            "code": row.get("code"),
            "managerDept": row.get("manager_dept"),
            "manager": row.get("manager"),
            "phone": row.get("phone"),
            "capacity": row.get("capacity"),
            "area": row.get("area"),
            "address": row.get("address"),
            "description": row.get("description"),
            "status": bool(row.get("status")) if row.get("status") is not None else True,
            "sortOrder": int(row.get("sort_order") or 0),
            "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
            "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
            "roleIds": [],
            "userIds": [],
            "children": [],
        }

    @staticmethod
    async def get_tree() -> List[dict]:
        await LocationService._ensure_tables()

        rows = await db.fetch_all(
            """
            SELECT
                id, parent_id, name, type, code,
                manager_dept, manager, phone, capacity, area, address, description,
                status, sort_order, created_at, updated_at
            FROM location_nodes
            ORDER BY COALESCE(parent_id, 0), sort_order, id
            """
        )
        items = [LocationService._row_to_node(dict(r)) for r in (rows or [])]
        node_ids = [int(it["id"]) for it in items if it and it.get("id") is not None]
        role_map, user_map = await LocationService._get_bindings_map(node_ids)
        for it in items:
            nid = int(it["id"])
            it["roleIds"] = role_map.get(nid, [])
            it["userIds"] = user_map.get(nid, [])

        by_id: Dict[int, dict] = {int(it["id"]): it for it in items}
        roots: List[dict] = []
        for it in items:
            pid = it.get("parent_id")
            if pid is None:
                roots.append(it)
                continue
            parent = by_id.get(int(pid))
            if parent is None:
                roots.append(it)
                continue
            parent["children"].append(it)

        return roots

    @staticmethod
    async def create_node(data: Dict[str, Any]) -> dict:
        await LocationService._ensure_tables()

        parent_id = data.get("parent_id")
        parent_id_val = int(parent_id) if parent_id is not None else None

        next_sort = await db.fetch_val(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM location_nodes
            WHERE ($1::bigint IS NULL AND parent_id IS NULL)
               OR (parent_id = $1::bigint)
            """,
            parent_id_val,
        )

        code = await LocationService._generate_code_for_new_node(parent_id_val)
        role_ids = LocationService._normalize_id_list(data.get("roleIds"))
        user_ids = LocationService._normalize_id_list(data.get("userIds"))

        for _ in range(20):
            try:
                row = await db.fetch_one(
                    """
                    INSERT INTO location_nodes
                      (parent_id, name, type, code, manager_dept, manager, phone, capacity, area, address, description, status, sort_order)
                    VALUES
                      ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    RETURNING
                      id, parent_id, name, type, code,
                      manager_dept, manager, phone, capacity, area, address, description,
                      status, sort_order, created_at, updated_at
                    """,
                    parent_id_val,
                    str(data.get("label") or "").strip(),
                    str(data.get("type") or "").strip(),
                    code,
                    LocationService._normalize_optional_str(data.get("managerDept")),
                    LocationService._normalize_optional_str(data.get("manager")),
                    LocationService._normalize_optional_str(data.get("phone")),
                    int(data.get("capacity")) if data.get("capacity") is not None else None,
                    float(data.get("area")) if data.get("area") is not None else None,
                    LocationService._normalize_optional_str(data.get("address")),
                    LocationService._normalize_optional_str(data.get("description")),
                    bool(data.get("status")) if data.get("status") is not None else True,
                    int(next_sort or 0),
                )
                node = LocationService._row_to_node(dict(row)) if row else {}
                if node and node.get("id") is not None:
                    await LocationService._set_node_bindings(
                        node_id=int(node["id"]),
                        role_ids=role_ids,
                        user_ids=user_ids,
                    )
                    node["roleIds"] = role_ids
                    node["userIds"] = user_ids
                return node
            except asyncpg.exceptions.UniqueViolationError:
                code = await LocationService._generate_code_for_new_node(parent_id_val)
                continue
        raise ValueError("创建失败：编码冲突过多")

    @staticmethod
    async def update_node(node_id: int, patch: Dict[str, Any]) -> Optional[dict]:
        await LocationService._ensure_tables()

        role_ids_patch = patch.get("roleIds") if "roleIds" in patch else None
        user_ids_patch = patch.get("userIds") if "userIds" in patch else None

        fields = []
        values: List[Any] = []
        idx = 1

        mapping = {
            "label": "name",
            "type": "type",
            "managerDept": "manager_dept",
            "manager": "manager",
            "phone": "phone",
            "capacity": "capacity",
            "area": "area",
            "address": "address",
            "description": "description",
            "status": "status",
        }

        for k, col in mapping.items():
            if k not in patch or patch.get(k) is None:
                continue
            val = patch.get(k)
            if k in {"label", "type"}:
                val = str(val).strip()
            elif k in {"managerDept", "manager", "phone", "address", "description"}:
                val = (str(val).strip() if val is not None else None) or None
            elif k == "capacity":
                val = int(val) if val is not None else None
            elif k == "area":
                val = float(val) if val is not None else None
            elif k == "status":
                val = bool(val)
            fields.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

        if not fields:
            row = await db.fetch_one(
                """
                SELECT
                  id, parent_id, name, type, code,
                  manager_dept, manager, phone, capacity, area, address, description,
                  status, sort_order, created_at, updated_at
                FROM location_nodes
                WHERE id = $1
                """,
                int(node_id),
            )
            node = LocationService._row_to_node(dict(row)) if row else None
            if node and node.get("id") is not None:
                role_map, user_map = await LocationService._get_bindings_map([int(node["id"])])
                node["roleIds"] = role_map.get(int(node["id"]), [])
                node["userIds"] = user_map.get(int(node["id"]), [])
            if role_ids_patch is not None or user_ids_patch is not None:
                await LocationService._set_node_bindings(
                    node_id=int(node_id),
                    role_ids=role_ids_patch if role_ids_patch is not None else None,
                    user_ids=user_ids_patch if user_ids_patch is not None else None,
                )
                if node:
                    if role_ids_patch is not None:
                        node["roleIds"] = LocationService._normalize_id_list(role_ids_patch)
                    if user_ids_patch is not None:
                        node["userIds"] = LocationService._normalize_id_list(user_ids_patch)
            return node

        fields.append("updated_at = NOW()")
        values.append(int(node_id))

        row = await db.fetch_one(
            f"""
            UPDATE location_nodes
            SET {', '.join(fields)}
            WHERE id = ${idx}
            RETURNING
              id, parent_id, name, type, code,
              manager_dept, manager, phone, capacity, area, address, description,
              status, sort_order, created_at, updated_at
            """,
            *values,
        )
        updated = LocationService._row_to_node(dict(row)) if row else None
        if not updated:
            return None

        if role_ids_patch is not None or user_ids_patch is not None:
            await LocationService._set_node_bindings(
                node_id=int(node_id),
                role_ids=role_ids_patch if role_ids_patch is not None else None,
                user_ids=user_ids_patch if user_ids_patch is not None else None,
            )

        role_map, user_map = await LocationService._get_bindings_map([int(node_id)])
        updated["roleIds"] = role_map.get(int(node_id), [])
        updated["userIds"] = user_map.get(int(node_id), [])
        return updated

    @staticmethod
    async def delete_node(node_id: int) -> bool:
        await LocationService._ensure_tables()
        res = await db.execute("DELETE FROM location_nodes WHERE id = $1", int(node_id))
        return "DELETE" in str(res or "").upper()

    @staticmethod
    async def move_node(node_id: int, parent_id: Optional[int]) -> Optional[dict]:
        await LocationService._ensure_tables()

        parent_id_val = int(parent_id) if parent_id is not None else None
        next_sort = await db.fetch_val(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM location_nodes
            WHERE ($1::bigint IS NULL AND parent_id IS NULL)
               OR (parent_id = $1::bigint)
            """,
            parent_id_val,
        )

        row = await db.fetch_one(
            """
            UPDATE location_nodes
            SET parent_id = $1, sort_order = $2, updated_at = NOW()
            WHERE id = $3
            RETURNING
              id, parent_id, name, type, code,
              manager_dept, manager, phone, capacity, area, address, description,
              status, sort_order, created_at, updated_at
            """,
            parent_id_val,
            int(next_sort or 0),
            int(node_id),
        )
        moved = LocationService._row_to_node(dict(row)) if row else None
        if not moved:
            return None

        await LocationService._regenerate_codes_if_needed(int(node_id))

        row3 = await db.fetch_one(
            """
            SELECT
              id, parent_id, name, type, code,
              manager_dept, manager, phone, capacity, area, address, description,
              status, sort_order, created_at, updated_at
            FROM location_nodes
            WHERE id = $1
            """,
            int(node_id),
        )
        return LocationService._row_to_node(dict(row3)) if row3 else moved

    @staticmethod
    async def _regenerate_codes_if_needed(root_id: int) -> None:
        await LocationService._ensure_tables()

        rows = await db.fetch_all(
            """
            WITH RECURSIVE sub AS (
                SELECT id, parent_id, code, sort_order, 0 AS depth
                FROM location_nodes
                WHERE id = $1
                UNION ALL
                SELECT n.id, n.parent_id, n.code, n.sort_order, s.depth + 1
                FROM location_nodes n
                JOIN sub s ON n.parent_id = s.id
            )
            SELECT id, parent_id, code, sort_order, depth
            FROM sub
            ORDER BY depth, sort_order, id
            """,
            int(root_id),
        )
        if not rows:
            return

        code_map: Dict[int, Optional[str]] = {}
        next_n_cache: Dict[Optional[int], int] = {}

        def should_regen(code_val: Any) -> bool:
            c = LocationService._normalize_optional_str(code_val)
            return (c is None) or LocationService._is_auto_code(c)

        for r in rows:
            node_id = int(r["id"])
            parent_id = int(r["parent_id"]) if r.get("parent_id") is not None else None
            existing_code = LocationService._normalize_optional_str(r.get("code"))

            if not should_regen(existing_code):
                code_map[node_id] = existing_code
                continue

            parent_code = None
            if parent_id is not None:
                parent_code = code_map.get(parent_id)
                if not parent_code:
                    parent_code = await LocationService._ensure_node_has_code(int(parent_id))

            key = parent_id
            if key not in next_n_cache:
                next_n_cache[key] = await LocationService._next_auto_child_number(
                    parent_id=parent_id,
                    parent_code=parent_code,
                )
            n = next_n_cache[key]
            next_n_cache[key] = n + 1

            seg = format(int(n), "X")
            new_code = seg if not parent_code else f"{parent_code}.{seg}"

            for _ in range(20):
                try:
                    await db.execute(
                        "UPDATE location_nodes SET code = $1, updated_at = NOW() WHERE id = $2",
                        new_code,
                        node_id,
                    )
                    code_map[node_id] = new_code
                    break
                except asyncpg.exceptions.UniqueViolationError:
                    n = next_n_cache[key]
                    next_n_cache[key] = n + 1
                    seg = format(int(n), "X")
                    new_code = seg if not parent_code else f"{parent_code}.{seg}"
                    continue
