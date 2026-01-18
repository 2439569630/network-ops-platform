from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class User:
    """用户数据类"""
    id: int
    username: str
    password: str
    nickname: str
    is_approved: bool
    permissions: Optional[List[str]] = None
    email: Optional[str] = None
    created_at: Optional[datetime] = None
