from dataclasses import dataclass
from typing import Optional

@dataclass
class SystemSetting:
    key: str
    value: str
    group_name: str
    description: Optional[str] = None
