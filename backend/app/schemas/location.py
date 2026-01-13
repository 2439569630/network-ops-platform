from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel


class LocationNodeBase(BaseModel):
    label: str
    type: str
    code: Optional[str] = None
    managerDept: Optional[str] = None
    manager: Optional[str] = None
    phone: Optional[str] = None
    capacity: Optional[int] = None
    area: Optional[float] = None
    address: Optional[str] = None
    description: Optional[str] = None
    status: bool = True
    roleIds: Optional[List[int]] = None
    userIds: Optional[List[int]] = None


class LocationNodeCreate(LocationNodeBase):
    parent_id: Optional[int] = None


class LocationNodeUpdate(BaseModel):
    label: Optional[str] = None
    type: Optional[str] = None
    code: Optional[str] = None
    managerDept: Optional[str] = None
    manager: Optional[str] = None
    phone: Optional[str] = None
    capacity: Optional[int] = None
    area: Optional[float] = None
    address: Optional[str] = None
    description: Optional[str] = None
    status: Optional[bool] = None
    roleIds: Optional[List[int]] = None
    userIds: Optional[List[int]] = None


class LocationNodeMove(BaseModel):
    parent_id: Optional[int] = None


class LocationNodeResponse(LocationNodeBase):
    id: int
    parent_id: Optional[int] = None
    sortOrder: int = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    children: List["LocationNodeResponse"] = []

    class Config:
        from_attributes = True
