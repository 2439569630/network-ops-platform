from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class AlertRuleBase(BaseModel):
    metric: str
    operator: str
    threshold: float
    severity: str = "warning"
    duration: int = 0
    is_enabled: bool = True
    notification_channels: Optional[List[str]] = None

class AlertRuleCreate(AlertRuleBase):
    device_id: int

class AlertRuleUpdate(BaseModel):
    metric: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    severity: Optional[str] = None
    duration: Optional[int] = None
    is_enabled: Optional[bool] = None
    notification_channels: Optional[List[str]] = None

class AlertRuleOut(AlertRuleBase):
    id: int
    device_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AlertLogOut(BaseModel):
    id: int
    device_id: int
    rule_id: Optional[int]
    metric: str
    value: float
    message: str
    severity: str
    triggered_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True
