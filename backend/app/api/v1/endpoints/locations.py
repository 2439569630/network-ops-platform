from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel

from app.core.security import PermissionChecker
from app.schemas.location import LocationNodeCreate, LocationNodeUpdate, LocationNodeMove
from app.services.location_service import LocationService
from app.core.database import db
from app.models.orm.location import LocationNode, LocationNodeDevice
from app.models.orm.device import NetworkDevice


router = APIRouter()


class DeviceBindRequest(BaseModel):
    device_ids: List[int]


@router.get("/tree", response_model=dict)
async def get_location_tree(user: dict = Depends(PermissionChecker(["sys:location:view"]))):
    try:
        data = await LocationService.get_tree()
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取位置树失败: {str(e)}"}


@router.post("/", response_model=dict)
async def create_location_node(
    payload: LocationNodeCreate, user: dict = Depends(PermissionChecker(["sys:location:add"]))
):
    try:
        node = await LocationService.create_node(payload.model_dump())
        return {"code": 200, "message": "创建成功", "data": node}
    except Exception as e:
        return {"code": 500, "message": f"创建失败: {str(e)}"}


@router.put("/{node_id}", response_model=dict)
async def update_location_node(
    node_id: int, payload: LocationNodeUpdate, user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    try:
        updated = await LocationService.update_node(int(node_id), payload.model_dump(exclude_unset=True))
        if not updated:
            return {"code": 404, "message": "位置不存在"}
        return {"code": 200, "message": "更新成功", "data": updated}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.delete("/{node_id}", response_model=dict)
async def delete_location_node(
    node_id: int, user: dict = Depends(PermissionChecker(["sys:location:del"]))
):
    try:
        ok = await LocationService.delete_node(int(node_id))
        if not ok:
            return {"code": 404, "message": "位置不存在"}
        return {"code": 200, "message": "删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}


@router.post("/{node_id}/move", response_model=dict)
async def move_location_node(
    node_id: int, payload: LocationNodeMove, user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    try:
        moved = await LocationService.move_node(int(node_id), payload.parent_id)
        if not moved:
            return {"code": 404, "message": "位置不存在"}
        return {"code": 200, "message": "移动成功", "data": moved}
    except Exception as e:
        return {"code": 500, "message": f"移动失败: {str(e)}"}


@router.get("/bind/roles", response_model=dict)
async def list_bind_roles(user: dict = Depends(PermissionChecker(["sys:location:manage"]))):
    try:
        rows = await db.fetch_all("SELECT id, name, code FROM roles ORDER BY id")
        data = [{"id": int(r["id"]), "name": r.get("name"), "code": r.get("code")} for r in (rows or [])]
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取角色失败: {str(e)}"}


@router.get("/bind/users", response_model=dict)
async def search_bind_users(
    q: str = Query("", max_length=200),
    role_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(PermissionChecker(["sys:location:manage"])),
):
    try:
        q_norm = str(q or "").strip()
        page_norm = max(1, int(page or 1))
        size_norm = max(1, min(200, int(page_size or 50)))
        offset = (page_norm - 1) * size_norm

        where_parts = []
        params = []
        idx = 1

        if q_norm:
            where_parts.append(f"(username ILIKE ${idx} OR nickname ILIKE ${idx} OR email ILIKE ${idx})")
            params.append(f"%{q_norm}%")
            idx += 1
        
        if role_id:
            where_parts.append(f"EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = users.id AND ur.role_id = ${idx})")
            params.append(role_id)
            idx += 1

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        if role_id and not q_norm:
            total = await db.fetch_val("SELECT COUNT(1) FROM user_roles ur WHERE ur.role_id = $1", int(role_id))
        else:
            total = await db.fetch_val(f"SELECT COUNT(1) FROM users {where_sql}", *params)
        rows = await db.fetch_all(
            f"""
            SELECT id, username, nickname, email
            FROM users
            {where_sql}
            ORDER BY username
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
            size_norm,
            offset,
        )
        items = [dict(r) for r in (rows or [])]
        return {
            "code": 200,
            "data": items,
            "meta": {"total": int(total or 0), "page": page_norm, "page_size": size_norm, "q": q_norm},
        }
    except Exception as e:
        return {"code": 500, "message": f"获取用户失败: {str(e)}"}


@router.post("/{node_id}/devices", response_model=dict)
async def add_devices_to_location(
    node_id: int,
    payload: DeviceBindRequest,
    user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    try:
        # Get location node info (need name for the device location field)
        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return {"code": 404, "message": "位置不存在"}
        
        # Check node type
        # Allow binding only for specific types or deny broad types
        # Policy: Deny 'school', 'campus', 'department'
        # Let's deny broad types.
        if node.type in ('school', 'campus', 'department'):
            return {"code": 400, "message": f"无法在[{node.type}]类型的节点上直接绑定设备，请选择更具体的下级位置"}

        device_ids = payload.device_ids
        if not device_ids:
             return {"code": 200, "message": "未选择设备"}

        # Update devices
        # 1. Clear existing mappings for these devices (enforce 1:1)
        await LocationNodeDevice.filter(device_id__in=device_ids).delete()
        
        # 2. Add new mappings
        # Using bulk create? Or simple loop? Loop is safer for small batches.
        for did in device_ids:
            # Upsert not needed since we deleted above.
            await LocationNodeDevice.create(node_id=node.id, device_id=did)
        
        return {"code": 200, "message": "设备添加成功"}
    except Exception as e:
        return {"code": 500, "message": f"添加设备失败: {str(e)}"}


@router.delete("/{node_id}/devices", response_model=dict)
async def remove_devices_from_location(
    node_id: int,
    payload: DeviceBindRequest = Body(...),
    user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    try:
        # Get location node info
        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return {"code": 404, "message": "位置不存在"}
        
        device_ids = payload.device_ids
        if not device_ids:
             return {"code": 200, "message": "未选择设备"}

        # Remove devices from THIS location
        await LocationNodeDevice.filter(node_id=node.id, device_id__in=device_ids).delete()
        
        return {"code": 200, "message": "设备移除成功"}
    except Exception as e:
        return {"code": 500, "message": f"移除设备失败: {str(e)}"}


@router.get("/bind/users/by_ids", response_model=dict)
async def list_bind_users_by_ids(
    ids: list[int] = Query(default=[]),
    user: dict = Depends(PermissionChecker(["sys:location:manage"])),
):
    try:
        norm = [int(x) for x in (ids or []) if x is not None]
        if not norm:
            return {"code": 200, "data": []}
        rows = await db.fetch_all(
            """
            SELECT id, username, nickname, email
            FROM users
            WHERE id = ANY($1::int[])
            ORDER BY username
            """,
            norm,
        )
        return {"code": 200, "data": [dict(r) for r in (rows or [])]}
    except Exception as e:
        return {"code": 500, "message": f"获取用户失败: {str(e)}"}
