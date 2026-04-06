from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel


class LocationNodeBase(BaseModel):
    """位置节点基础模型"""
    label: str
    type: str
    code: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    status: bool = True
    roleIds: Optional[List[int]] = None
    userIds: Optional[List[int]] = None


class LocationNodeCreate(LocationNodeBase):
    """位置节点创建模型"""
    parent_id: Optional[int] = None
    inherit_users: Optional[bool] = False


class LocationNodeUpdate(BaseModel):
    """位置节点更新模型"""
    label: Optional[str] = None
    type: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    status: Optional[bool] = None
    roleIds: Optional[List[int]] = None
    userIds: Optional[List[int]] = None
    inherit_users: Optional[bool] = None


class LocationNodeMove(BaseModel):
    """位置节点移动模型"""
    parent_id: Optional[int] = None


class LocationNodeResponse(LocationNodeBase):
    """位置节点响应模型"""
    id: int
    parent_id: Optional[int] = None
    sortOrder: int = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    children: List["LocationNodeResponse"] = []

    class Config:
        from_attributes = True
