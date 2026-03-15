from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50)
    nickname: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None

class UserCreate(UserBase):
    """用户创建模型"""
    password: str = Field(..., min_length=6)
    role_ids: Optional[List[int]] = None

class UserUpdate(BaseModel):
    """用户更新模型"""
    nickname: Optional[str] = None
    email: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

class RoleUpdate(BaseModel):
    """用户角色更新模型"""
    pass

class UserStatusUpdate(BaseModel):
    """用户状态更新模型"""
    is_approved: bool

class AdminUserUpdate(BaseModel):
    """管理员更新用户信息模型"""
    nickname: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    is_email_notify: Optional[bool] = None
    is_approved: Optional[bool] = None
    role_ids: Optional[List[int]] = None

class UserResponse(UserBase):
    """用户响应模型"""
    id: int
    is_approved: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
