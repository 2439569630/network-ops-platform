from pydantic import BaseModel
from typing import Optional, List


class RoleBase(BaseModel):
    """角色基础模型"""
    name: str
    code: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    """角色创建模型"""
    pass


class RoleUpdate(BaseModel):
    """角色更新模型"""
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class RoleOut(RoleBase):
    """角色响应模型"""
    id: int
    created_at: Optional[str] = None


class PermissionBase(BaseModel):
    """权限基础模型"""
    name: str
    code: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    """权限创建模型"""
    pass


class PermissionUpdate(BaseModel):
    """权限更新模型"""
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class PermissionOut(PermissionBase):
    """权限响应模型"""
    id: int
    created_at: Optional[str] = None


class RolePermissionsSet(BaseModel):
    """角色权限设置模型"""
    permission_ids: List[int]


class DisabledPermissionsSet(BaseModel):
    """禁用权限设置模型"""
    codes: List[str]


class UserRolesSet(BaseModel):
    """用户角色设置模型"""
    role_ids: List[int]
