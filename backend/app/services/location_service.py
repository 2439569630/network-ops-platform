
import re
from typing import Any, Dict, List, Optional, Tuple
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.constants.user import DELETED_USER_DISPLAY_NAME
from app.core.database import db
from app.models.orm.location import LocationNode, LocationNodeRole, LocationNodeUser, LocationNodeDevice

class LocationService:
    """
    位置服务类
    处理位置节点的树形结构管理、编码生成、设备/用户/角色绑定等业务逻辑。
    """
    _auto_code_re = re.compile(r"^[0-9A-Fa-f]+(\.[0-9A-Fa-f]+)*$")

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

        # ORM fetch
        role_rows = await LocationNodeRole.filter(node_id__in=ids).all()
        user_rows = await LocationNodeUser.filter(node_id__in=ids).all()

        role_map: Dict[int, List[int]] = {}
        for r in role_rows:
            nid = int(r.node_id)
            role_map.setdefault(nid, []).append(int(r.role_id))

        user_map: Dict[int, List[int]] = {}
        for r in user_rows:
            nid = int(r.node_id)
            user_map.setdefault(nid, []).append(int(r.user_id))

        return role_map, user_map

    @staticmethod
    async def _get_user_briefs(user_ids: List[int]) -> Dict[int, dict]:
        ids = [int(x) for x in (user_ids or []) if x is not None]
        if not ids:
            return {}

        uniq: List[int] = []
        seen: set[int] = set()
        for uid in ids:
            if uid in seen:
                continue
            seen.add(uid)
            uniq.append(uid)

        rows = await db.fetch_all(
            """
            SELECT id, username, nickname, email
            FROM users
            WHERE id = ANY($1::int[])
            """,
            uniq,
        )
        row_map = {
            int(r["id"]): {
                "id": int(r["id"]),
                "username": r.get("username"),
                "nickname": r.get("nickname"),
                "email": r.get("email"),
            }
            for r in (rows or [])
            if r and r.get("id") is not None
        }

        for uid in uniq:
            row_map.setdefault(
                int(uid),
                {"id": int(uid), "username": None, "nickname": DELETED_USER_DISPLAY_NAME, "email": None},
            )
        return row_map

    @staticmethod
    async def _set_node_bindings(*, node_id: int, role_ids: Optional[List[int]] = None, user_ids: Optional[List[int]] = None) -> None:
        nid = int(node_id)
        if role_ids is not None:
            ids = LocationService._normalize_id_list(role_ids)
            await LocationNodeRole.filter(node_id=nid).delete()
            for rid in ids:
                # Use get_or_create to avoid unique constraint violation if race condition, 
                # but we just deleted, so create should be fine.
                await LocationNodeRole.create(node_id=nid, role_id=int(rid))
                
        if user_ids is not None:
            ids = LocationService._normalize_id_list(user_ids)
            await LocationNodeUser.filter(node_id=nid).delete()
            for uid in ids:
                await LocationNodeUser.create(node_id=nid, user_id=int(uid))

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
        node = await LocationNode.filter(id=node_id).only("id", "parent_id", "code").first()
        return dict(node) if node else None

    @staticmethod
    async def _next_auto_child_number(*, parent_id: Optional[int], parent_code: Optional[str]) -> int:
        parent_code_norm = LocationService._normalize_optional_str(parent_code)
        parent_depth = len(LocationService._split_code_segments(parent_code_norm)) if parent_code_norm else 0

        # Fetch codes of children
        if parent_id is not None:
            nodes = await LocationNode.filter(parent_id=parent_id).exclude(code__isnull=True).exclude(code="").all()
        else:
            nodes = await LocationNode.filter(parent_id__isnull=True).exclude(code__isnull=True).exclude(code="").all()

        max_n = -1
        for r in nodes:
            code = LocationService._normalize_optional_str(r.code)
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
    async def get_descendant_ids(root_id: int) -> List[int]:
        """
        获取所有后代节点的 ID 列表
        """
        return await LocationService._get_descendant_ids(root_id)

    @staticmethod
    async def _get_descendant_ids(root_id: int) -> List[int]:
        conn = Tortoise.get_connection("default")
        sql = """
            WITH RECURSIVE sub AS (
                SELECT id
                FROM location_nodes
                WHERE parent_id = $1
                UNION ALL
                SELECT n.id
                FROM location_nodes n
                JOIN sub s ON n.parent_id = s.id
            )
            SELECT id FROM sub
        """
        _, rows = await conn.execute_query(sql, [root_id])
        return [int(r["id"]) for r in rows]

    @staticmethod
    async def _ensure_node_has_code(node_id: int) -> Optional[str]:
        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return None
        existing = LocationService._normalize_optional_str(node.code)
        if existing:
            return existing

        parent_id = node.parent_id
        parent_code = None
        if parent_id is not None:
            parent_code = await LocationService._ensure_node_has_code(int(parent_id))

        for _ in range(20):
            n = await LocationService._next_auto_child_number(parent_id=int(parent_id) if parent_id is not None else None, parent_code=parent_code)
            seg = format(int(n), "X")
            new_code = seg if not parent_code else f"{parent_code}.{seg}"
            
            exists = await LocationNode.filter(code=new_code).exclude(id=node_id).exists()
            if exists:
                continue
            
            node.code = new_code
            try:
                await node.save()
                return new_code
            except Exception: # Unique violation likely
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
            
            exists = await LocationNode.filter(code=code).exists()
            if exists:
                continue
            return code
        raise ValueError("生成位置编码失败：可用编码耗尽或冲突过多")

    @staticmethod
    async def get_node_paths() -> Dict[int, str]:
        """获取所有节点的完整路径"""
        nodes = await LocationNode.all().values("id", "parent_id", "name")
        node_map = {n["id"]: n for n in nodes}
        paths = {}
        for nid, node in node_map.items():
            path_parts = []
            curr = node
            while curr:
                path_parts.append(curr["name"])
                curr = node_map.get(curr["parent_id"]) if curr.get("parent_id") else None
            paths[nid] = " / ".join(reversed(path_parts))
        return paths

    @staticmethod
    async def log_device_location_changes(
        device_ids: List[int],
        old_node_map: Dict[int, int],
        new_node_id: Optional[int],
        changed_by: str,
        action: str
    ):
        """
        记录设备位置变更审计日志
        :param action: "bind", "unbind", "move", "delete_node"
        """
        if not device_ids:
            return

        from app.models.orm.audit import DeviceChangeLog
        from app.services.device_event_service import DeviceEventService
        
        paths = await LocationService.get_node_paths()
        new_path = paths.get(new_node_id, "未分配位置") if new_node_id else "未分配位置"
        
        logs_to_create = []
        changed_devices = []
        for did in device_ids:
            old_nid = old_node_map.get(did)
            old_path = paths.get(old_nid, "未分配位置") if old_nid else "未分配位置"
            
            # 跳过无意义的重复操作
            if old_path == new_path:
                continue

            desc = "修改设备位置"
            if action == "delete_node":
                desc = "因位置节点删除而解绑"
            else:
                if old_path == "未分配位置" and new_path != "未分配位置":
                    desc = "绑定设备位置"
                elif old_path != "未分配位置" and new_path != "未分配位置":
                    desc = "迁移设备位置"
                elif old_path != "未分配位置" and new_path == "未分配位置":
                    desc = "解绑设备位置"

            logs_to_create.append(
                DeviceChangeLog(
                    device_id=did,
                    change_type="update_location",
                    change_description=desc,
                    changed_by=changed_by,
                    old_values={"location": old_path},
                    new_values={"location": new_path},
                )
            )
            changed_devices.append(did)
            
        if logs_to_create:
            await DeviceChangeLog.bulk_create(logs_to_create)
            for did in changed_devices:
                await DeviceEventService.publish_device_event("update_location", did)

    @staticmethod
    def _model_to_dict(node: LocationNode) -> dict:
        return {
            "id": int(node.id),
            "parent_id": int(node.parent_id) if node.parent_id is not None else None,
            "label": node.name,
            "type": node.type,
            "code": node.code,
            "address": node.address,
            "description": node.description,
            "status": bool(node.status),
            "sortOrder": int(node.sort_order),
            "createdAt": node.created_at.isoformat() if node.created_at else None,
            "updatedAt": node.updated_at.isoformat() if node.updated_at else None,
            "roleIds": [],
            "userIds": [],
            "users": [],
            "children": [],
        }

    @staticmethod
    async def get_tree() -> List[dict]:
        """
        获取完整的位置树结构
        """
        nodes = await LocationNode.all().order_by("parent_id", "sort_order", "id")
        
        items = [LocationService._model_to_dict(n) for n in nodes]
        node_ids = [int(it["id"]) for it in items if it and it.get("id") is not None]
        role_map, user_map = await LocationService._get_bindings_map(node_ids)
        user_brief_map = await LocationService._get_user_briefs(
            [uid for ids in user_map.values() for uid in (ids or [])]
        )
        for it in items:
            nid = int(it["id"])
            it["roleIds"] = role_map.get(nid, [])
            it["userIds"] = user_map.get(nid, [])
            it["users"] = [user_brief_map[uid] for uid in it["userIds"] if uid in user_brief_map]

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

        # Cleanup empty children for frontend components (e.g. Cascader)
        for it in items:
            if not it["children"]:
                del it["children"]

        return roots

    @staticmethod
    async def create_node(data: Dict[str, Any]) -> dict:
        """
        创建新的位置节点
        自动生成编码，处理绑定关系
        """
        parent_id = data.get("parent_id")
        parent_id_val = int(parent_id) if parent_id is not None else None

        # Max sort order
        conn = Tortoise.get_connection("default")
        # Raw SQL for max sort order is cleaner
        sql = """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM location_nodes
            WHERE ($1::bigint IS NULL AND parent_id IS NULL)
               OR (parent_id = $1::bigint)
        """
        _, rows = await conn.execute_query(sql, [parent_id_val])
        next_sort = rows[0][0] if rows else 0

        code = await LocationService._generate_code_for_new_node(parent_id_val)
        role_ids = LocationService._normalize_id_list(data.get("roleIds"))
        user_ids = LocationService._normalize_id_list(data.get("userIds"))

        for _ in range(20):
            try:
                node = await LocationNode.create(
                    parent_id=parent_id_val,
                    name=str(data.get("label") or "").strip(),
                    type=str(data.get("type") or "").strip(),
                    code=code,
                    address=LocationService._normalize_optional_str(data.get("address")),
                    description=LocationService._normalize_optional_str(data.get("description")),
                    status=bool(data.get("status")) if data.get("status") is not None else True,
                    sort_order=int(next_sort or 0)
                )
                
                res = LocationService._model_to_dict(node)
                await LocationService._set_node_bindings(
                    node_id=int(node.id),
                    role_ids=role_ids,
                    user_ids=user_ids,
                )
                res["roleIds"] = role_ids
                res["userIds"] = user_ids
                user_brief_map = await LocationService._get_user_briefs(user_ids)
                res["users"] = [user_brief_map[uid] for uid in user_ids if uid in user_brief_map]
                return res
            except Exception as e:
                # Check for unique violation on code
                if "unique" in str(e).lower() and "code" in str(e).lower():
                    code = await LocationService._generate_code_for_new_node(parent_id_val)
                    continue
                raise e
        raise ValueError("创建失败：编码冲突过多")

    @staticmethod
    async def update_node(node_id: int, patch: Dict[str, Any]) -> Optional[dict]:
        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return None

        role_ids_patch = patch.get("roleIds") if "roleIds" in patch else None
        user_ids_patch = patch.get("userIds") if "userIds" in patch else None

        mapping = {
            "label": "name",
            "type": "type",
            "address": "address",
            "description": "description",
            "status": "status",
        }

        updated = False
        for k, col in mapping.items():
            if k not in patch or patch.get(k) is None:
                continue
            val = patch.get(k)
            if k in {"label", "type"}:
                val = str(val).strip()
            elif k in {"address", "description"}:
                val = (str(val).strip() if val is not None else None) or None
            elif k == "status":
                val = bool(val)
            
            setattr(node, col, val)
            updated = True

        if updated:
            await node.save()

        # Update bindings
        if role_ids_patch is not None or user_ids_patch is not None:
            await LocationService._set_node_bindings(
                node_id=int(node_id),
                role_ids=role_ids_patch if role_ids_patch is not None else None,
                user_ids=user_ids_patch if user_ids_patch is not None else None,
            )

            # Inheritance Logic
            if user_ids_patch is not None and patch.get("inherit_users"):
                descendants = await LocationService._get_descendant_ids(int(node_id))
                uids = LocationService._normalize_id_list(user_ids_patch)
                if descendants and uids:
                    # Fetch existing bindings to avoid conflicts
                    existing = await LocationNodeUser.filter(node_id__in=descendants, user_id__in=uids).all()
                    existing_set = {(r.node_id, r.user_id) for r in existing}
                    
                    to_create = []
                    for did in descendants:
                        for uid in uids:
                            if (did, uid) not in existing_set:
                                to_create.append(LocationNodeUser(node_id=did, user_id=uid))
                    
                    if to_create:
                        await LocationNodeUser.bulk_create(to_create)

        # Return updated structure
        res = LocationService._model_to_dict(node)
        role_map, user_map = await LocationService._get_bindings_map([int(node_id)])
        res["roleIds"] = role_map.get(int(node_id), [])
        res["userIds"] = user_map.get(int(node_id), [])
        user_brief_map = await LocationService._get_user_briefs(res["userIds"])
        res["users"] = [user_brief_map[uid] for uid in res["userIds"] if uid in user_brief_map]
        return res

    @staticmethod
    async def delete_node(node_id: int, changed_by: str = "") -> bool:
        # Get all descendant IDs to delete the whole subtree
        ids = await LocationService._get_descendant_ids(node_id)
        ids.append(node_id)
        
        # 1. Delete device mappings (with logging)
        mappings = await LocationNodeDevice.filter(node_id__in=ids).all()
        if mappings:
            device_ids = [m.device_id for m in mappings]
            old_node_map = {m.device_id: m.node_id for m in mappings}
            await LocationNodeDevice.filter(node_id__in=ids).delete()
            await LocationService.log_device_location_changes(
                device_ids=device_ids,
                old_node_map=old_node_map,
                new_node_id=None,
                changed_by=changed_by,
                action="delete_node"
            )
        
        # 2. Delete role mappings
        await LocationNodeRole.filter(node_id__in=ids).delete()
        
        # 3. Delete user mappings
        await LocationNodeUser.filter(node_id__in=ids).delete()
        
        # 4. Delete nodes
        count = await LocationNode.filter(id__in=ids).delete()
        return count > 0

    @staticmethod
    async def move_node(node_id: int, parent_id: Optional[int]) -> Optional[dict]:
        """
        移动节点到新的父节点下
        自动重新生成编码
        """
        parent_id_val = int(parent_id) if parent_id is not None else None
        
        conn = Tortoise.get_connection("default")
        sql = """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM location_nodes
            WHERE ($1::bigint IS NULL AND parent_id IS NULL)
               OR (parent_id = $1::bigint)
        """
        _, rows = await conn.execute_query(sql, [parent_id_val])
        next_sort = rows[0][0] if rows else 0

        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return None
            
        node.parent_id = parent_id_val
        node.sort_order = next_sort
        await node.save()

        await LocationService._regenerate_codes_if_needed(int(node_id))
        
        # Reload
        node = await LocationNode.filter(id=node_id).first()
        return LocationService._model_to_dict(node)

    @staticmethod
    async def _regenerate_codes_if_needed(root_id: int) -> None:
        conn = Tortoise.get_connection("default")
        sql = """
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
        """
        _, rows = await conn.execute_query(sql, [root_id])
        if not rows:
            return

        # rows is list of tuples/records.
        # id=0, parent_id=1, code=2, sort_order=3, depth=4
        
        code_map: Dict[int, Optional[str]] = {}
        next_n_cache: Dict[Optional[int], int] = {}

        def should_regen(code_val: Any) -> bool:
            c = LocationService._normalize_optional_str(code_val)
            return (c is None) or LocationService._is_auto_code(c)

        for r in rows:
            node_id = int(r["id"])
            parent_id = int(r["parent_id"]) if r["parent_id"] is not None else None
            existing_code = LocationService._normalize_optional_str(r["code"])

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
                    await LocationNode.filter(id=node_id).update(code=new_code)
                    code_map[node_id] = new_code
                    break
                except Exception:
                    n = next_n_cache[key]
                    next_n_cache[key] = n + 1
                    seg = format(int(n), "X")
                    new_code = seg if not parent_code else f"{parent_code}.{seg}"
                    continue
