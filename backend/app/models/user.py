from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class User:
    """用户数据类"""
    id: int
    username: str
    password: str
    nickname: str
    is_approved: bool
    email: Optional[str] = None
    created_at: Optional[datetime] = None
