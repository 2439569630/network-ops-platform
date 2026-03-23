# -*- coding: utf-8 -*-
#
# 位置管理 API 接口
#
# 此模块负责处理位置（区域/楼栋/机房等）的层级结构管理。
# 支持位置树的增删改查、节点移动、以及设备和用户的绑定管理。
#

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel

from app.core.security import PermissionChecker
from app.schemas.location import LocationNodeCreate, LocationNodeUpdate, LocationNodeMove
from app.services.location_service import LocationService
from app.core.database import db
from app.constants.user import DELETED_USER_DISPLAY_NAME
from app.models.orm.location import LocationNode, LocationNodeDevice
from app.models.orm.device import NetworkDevice


router = APIRouter()


class DeviceBindRequest(BaseModel):
    """设备绑定请求参数"""
    device_ids: List[int]


@router.get("/tree", response_model=dict)
async def get_location_tree(user: dict = Depends(PermissionChecker(["sys:location:view"]))):
    """
    获取完整的位置树结构。
    
    返回嵌套的 JSON 结构，包含所有层级的节点。
    """
    try:
        data = await LocationService.get_tree()
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取位置树失败: {str(e)}"}


@router.post("/", response_model=dict)
async def create_location_node(
    payload: LocationNodeCreate, user: dict = Depends(PermissionChecker(["sys:location:add"]))
):
    """
    创建新的位置节点。
    
    Args:
        payload: 节点创建信息（名称、类型、父节点ID等）
    """
    try:
        node = await LocationService.create_node(payload.model_dump())
        return {"code": 200, "message": "创建成功", "data": node}
    except Exception as e:
        return {"code": 500, "message": f"创建失败: {str(e)}"}


@router.put("/{node_id}", response_model=dict)
async def update_location_node(
    node_id: int, payload: LocationNodeUpdate, user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    """
    更新位置节点信息。
    
    Args:
        node_id: 节点ID
        payload: 更新信息
    """
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
    """
    删除位置节点。
    
    注意：通常需要先清空该节点下的子节点和关联设备/用户才能删除。
    """
    try:
        ok = await LocationService.delete_node(int(node_id), changed_by=str(user.get("id", "")))
        if not ok:
            return {"code": 404, "message": "位置不存在"}
        return {"code": 200, "message": "删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}


@router.post("/{node_id}/move", response_model=dict)
async def move_location_node(
    node_id: int, payload: LocationNodeMove, user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    """
    移动位置节点。
    
    修改节点的父级ID，实现树结构的调整。
    """
    try:
        moved = await LocationService.move_node(int(node_id), payload.parent_id)
        if not moved:
            return {"code": 404, "message": "位置不存在"}
        return {"code": 200, "message": "移动成功", "data": moved}
    except Exception as e:
        return {"code": 500, "message": f"移动失败: {str(e)}"}


@router.get("/bind/roles", response_model=dict)
async def list_bind_roles(user: dict = Depends(PermissionChecker(["sys:location:bind"]))):
    """
    获取可绑定到位置的角色列表。
    
    用于在位置节点上配置基于角色的权限（例如：某角色可管理该位置）。
    """
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
    user: dict = Depends(PermissionChecker(["sys:location:bind"])),
):
    """
    搜索可绑定到位置的用户。
    
    支持按用户名/昵称/邮箱搜索，或按角色筛选。
    
    Args:
        q: 搜索关键字
        role_id: 角色ID过滤
        page: 页码
        page_size: 每页数量
    """
    try:
        q_norm = str(q or "").strip()
        page_norm = max(1, int(page or 1))
        size_norm = max(1, min(200, int(page_size or 50)))
        offset = (page_norm - 1) * size_norm

        where_parts = []
        params = []
        idx = 1

        # 1. 关键字搜索条件
        # 支持按 username, nickname, email 模糊匹配 (ILIKE)
        if q_norm:
            where_parts.append(f"(username ILIKE ${idx} OR nickname ILIKE ${idx} OR email ILIKE ${idx})")
            params.append(f"%{q_norm}%")
            idx += 1
        
        # 2. 角色筛选条件
        # 仅筛选拥有指定角色的用户 (例如：只看"运维人员")
        if role_id:
            where_parts.append(f"EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = users.id AND ur.role_id = ${idx})")
            params.append(role_id)
            idx += 1

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # 3. 计算总数 (用于分页)
        if role_id and not q_norm:
            # 优化：如果只按角色筛选且无关键字，直接查 user_roles 表更快
            total = await db.fetch_val("SELECT COUNT(1) FROM user_roles ur WHERE ur.role_id = $1", int(role_id))
        else:
            total = await db.fetch_val(f"SELECT COUNT(1) FROM users {where_sql}", *params)
            
        # 4. 分页查询用户列表
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
    """
    将设备绑定到指定位置节点。
    
    注意：
    1. 一个设备只能属于一个位置节点。
    2. 如果设备之前绑定了其他节点，会自动转移到新节点。
    3. 某些宽泛类型的节点（如学校/校区/部门）可能不允许直接绑定设备，需绑定到具体位置（如机房）。
    """
    try:
        # 1. 获取目标节点信息
        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return {"code": 404, "message": "位置不存在"}
        
        # 2. 业务规则检查：
        # 某些类型的节点 (如学校、校区、部门) 仅作为逻辑分组，不允许直接绑定物理设备。
        # 设备必须绑定到具体的物理位置 (如机房、办公室、弱电井)。
        if node.type in ('school', 'campus', 'department'):
            return {"code": 400, "message": f"无法在[{node.type}]类型的节点上直接绑定设备，请选择更具体的下级位置"}

        device_ids = payload.device_ids
        if not device_ids:
             return {"code": 200, "message": "未选择设备"}

        # 获取设备旧的位置映射，用于审计日志
        old_mappings = await LocationNodeDevice.filter(device_id__in=device_ids).all()
        old_node_map = {m.device_id: m.node_id for m in old_mappings}

        # 3. 清除这些设备已有的绑定关系
        # 系统设计为：一个设备只能属于一个位置 (1:1 或 N:1，但 device 侧只能指向一个 location)
        # 如果设备之前绑定了其他位置，这里会自动解绑，实现"抢占式"绑定。
        await LocationNodeDevice.filter(device_id__in=device_ids).delete()
        
        # 4. 创建新的绑定关系
        # 批量插入设备与当前节点的关联记录
        for did in device_ids:
            await LocationNodeDevice.create(node_id=node.id, device_id=did)
            
        # 5. 记录审计日志
        # 判断是首次绑定还是迁移 (旧映射是否存在且与新节点不同)
        # 我们可以在 log_device_location_changes 内部通过 action='bind'/'move' 处理，或者简化为一个 action
        # 简化为传递 'move' 如果原来有绑定，'bind' 如果原来没有
        # 这里统一传入，log_device_location_changes 会判断路径是否有实际变更
        action_type = "bind" # log_device_location_changes 会统一处理描述，或者根据是否有旧值自动区分
        await LocationService.log_device_location_changes(
            device_ids=device_ids,
            old_node_map=old_node_map,
            new_node_id=node.id,
            changed_by=str(user.get("id", "")),
            action="bind"
        )
        
        return {"code": 200, "message": "设备添加成功"}
    except Exception as e:
        return {"code": 500, "message": f"添加设备失败: {str(e)}"}


@router.delete("/{node_id}/devices", response_model=dict)
async def remove_devices_from_location(
    node_id: int,
    payload: DeviceBindRequest = Body(...),
    user: dict = Depends(PermissionChecker(["sys:location:edit"]))
):
    """
    从位置节点移除设备。
    
    移除后，设备将不属于任何位置。
    """
    try:
        node = await LocationNode.filter(id=node_id).first()
        if not node:
            return {"code": 404, "message": "位置不存在"}
        
        device_ids = payload.device_ids
        if not device_ids:
             return {"code": 200, "message": "未选择设备"}

        # 获取设备旧的位置映射
        old_mappings = await LocationNodeDevice.filter(node_id=node.id, device_id__in=device_ids).all()
        old_node_map = {m.device_id: m.node_id for m in old_mappings}

        # 仅移除当前节点的绑定关系
        await LocationNodeDevice.filter(node_id=node.id, device_id__in=device_ids).delete()
        
        # 记录审计日志
        if old_node_map:
            await LocationService.log_device_location_changes(
                device_ids=list(old_node_map.keys()),
                old_node_map=old_node_map,
                new_node_id=None,
                changed_by=str(user.get("id", "")),
                action="unbind"
            )
        
        return {"code": 200, "message": "设备移除成功"}
    except Exception as e:
        return {"code": 500, "message": f"移除设备失败: {str(e)}"}


@router.get("/bind/users/by_ids", response_model=dict)
async def list_bind_users_by_ids(
    ids: list[int] = Query(default=[]),
    user: dict = Depends(PermissionChecker(["sys:location:bind"])),
):
    """
    根据ID列表批量获取用户信息。
    
    用于前端回显已绑定的用户列表。
    """
    try:
        norm = [int(x) for x in (ids or []) if x is not None]
        if not norm:
            return {"code": 200, "data": []}
        seen: set[int] = set()
        uniq: list[int] = []
        for uid in norm:
            if uid in seen:
                continue
            seen.add(uid)
            uniq.append(uid)
        rows = await db.fetch_all(
            """
            SELECT id, username, nickname, email
            FROM users
            WHERE id = ANY($1::int[])
            ORDER BY username
            """,
            uniq,
        )
        row_map = {int(r["id"]): dict(r) for r in (rows or []) if r and r.get("id") is not None}
        data: list[dict] = []
        for uid in uniq:
            item = row_map.get(int(uid))
            if item is None:
                item = {"id": int(uid), "username": None, "nickname": DELETED_USER_DISPLAY_NAME, "email": None}
            data.append(item)
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取用户失败: {str(e)}"}
