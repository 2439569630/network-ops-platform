from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class User:
    id: int
    username: str
    password: str
    nickname: str
    permission_level: int
    is_approved: bool
    permissions: Optional[List[str]] = None
    email: Optional[str] = None
    created_at: Optional[datetime] = None
