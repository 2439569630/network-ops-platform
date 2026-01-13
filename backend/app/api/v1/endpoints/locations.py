from fastapi import APIRouter, Depends, Query

from app.core.security import PermissionChecker
from app.schemas.location import LocationNodeCreate, LocationNodeUpdate, LocationNodeMove
from app.services.location_service import LocationService
from app.core.database import db


router = APIRouter()


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
async def list_bind_roles(user: dict = Depends(PermissionChecker(["sys:location:add", "sys:location:edit"]))):
    try:
        rows = await db.fetch_all("SELECT id, name, code FROM roles ORDER BY id")
        data = [{"id": int(r["id"]), "name": r.get("name"), "code": r.get("code")} for r in (rows or [])]
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取角色失败: {str(e)}"}


@router.get("/bind/users", response_model=dict)
async def search_bind_users(
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(PermissionChecker(["sys:location:add", "sys:location:edit"])),
):
    try:
        q_norm = str(q or "").strip()
        page_norm = max(1, int(page or 1))
        size_norm = max(1, min(200, int(page_size or 50)))
        offset = (page_norm - 1) * size_norm

        where_sql = ""
        params = []
        idx = 1
        if q_norm:
            where_sql = f"WHERE (username ILIKE ${idx} OR nickname ILIKE ${idx} OR email ILIKE ${idx})"
            params.append(f"%{q_norm}%")
            idx += 1

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


@router.get("/bind/users/by_ids", response_model=dict)
async def list_bind_users_by_ids(
    ids: list[int] = Query(default=[]),
    user: dict = Depends(PermissionChecker(["sys:location:add", "sys:location:edit"])),
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
