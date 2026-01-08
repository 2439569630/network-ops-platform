from pydantic import BaseModel
from typing import Optional, List


class RoleBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class RoleOut(RoleBase):
    id: int
    created_at: Optional[str] = None


class PermissionBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class PermissionOut(PermissionBase):
    id: int
    created_at: Optional[str] = None


class RolePermissionsSet(BaseModel):
    permission_ids: List[int]


class DisabledPermissionsSet(BaseModel):
    codes: List[str]
