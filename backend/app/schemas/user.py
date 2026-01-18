from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50)
    nickname: Optional[str] = None
    email: Optional[str] = None

class UserCreate(UserBase):
    """用户创建模型"""
    password: str = Field(..., min_length=6)
    permissions: Optional[List[str]] = None

class UserUpdate(BaseModel):
    """用户更新模型"""
    nickname: Optional[str] = None
    email: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

class RoleUpdate(BaseModel):
    """用户角色/权限更新模型"""
    permissions: Optional[List[str]] = None

class UserStatusUpdate(BaseModel):
    """用户状态更新模型"""
    is_approved: bool

class UserResponse(UserBase):
    """用户响应模型"""
    id: int
    is_approved: bool
    permissions: Optional[List[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
