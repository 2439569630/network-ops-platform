from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    nickname: Optional[str] = None
    email: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    permission_level: int = 2  # 默认普通用户
    permissions: Optional[List[str]] = None

class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

class RoleUpdate(BaseModel):
    permission_level: Optional[int] = None
    permissions: Optional[List[str]] = None

class UserStatusUpdate(BaseModel):
    is_approved: bool

class UserResponse(UserBase):
    id: int
    permission_level: int
    is_approved: bool
    permissions: Optional[List[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
