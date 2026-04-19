from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime

AlertOperator = Literal[">", ">=", "<", "<=", "="]
AlertSeverity = Literal["info", "warning", "critical"]
AlertSubscriptionScope = Literal["device", "location", "rule"]  
AlertSubscriptionChannel = Literal["site", "email"]
ALLOWED_ALERT_METRICS = {
    "cpu_usage",
    "memory_usage",
    "disk_usage",
    "online_status",
    "if_phy_down_count",
    "if_protocol_down_count",
}


def _validate_metric_name(metric: Optional[str]) -> str:
    m = str(metric or "").strip()
    if not m:
        raise ValueError("metric 不能为空")
    if m in ALLOWED_ALERT_METRICS:
        return m
    if m.startswith("if_phy_down:") or m.startswith("if_protocol_down:"):
        return m
    raise ValueError("仅支持 CPU/内存/磁盘/在线状态/接口 Down 相关指标")

class AlertRuleBase(BaseModel):
    metric: str
    operator: AlertOperator
    threshold: float
    severity: AlertSeverity = "warning"
    duration: int = Field(default=0, ge=0)
    cooldown: int = Field(default=0, ge=0)
    is_enabled: bool = True
    notification_channels: Optional[List[str]] = None

class AlertRuleCreate(AlertRuleBase):
    device_id: int

    @model_validator(mode="after")
    def _validate_create(self):
        m = _validate_metric_name(self.metric)
        if m == "online_status":
            try:
                v = float(self.threshold)
            except Exception:
                raise ValueError("online_status 的阈值必须为 0 或 1")
            if v not in (0.0, 1.0):
                raise ValueError("online_status 的阈值必须为 0 或 1")
        return self

class AlertRuleUpdate(BaseModel):
    metric: Optional[str] = None
    operator: Optional[AlertOperator] = None
    threshold: Optional[float] = None
    severity: Optional[AlertSeverity] = None
    duration: Optional[int] = Field(default=None, ge=0)
    cooldown: Optional[int] = Field(default=None, ge=0)
    is_enabled: Optional[bool] = None
    notification_channels: Optional[List[str]] = None

    @model_validator(mode="after")
    def _validate_update(self):
        m = _validate_metric_name(self.metric) if self.metric is not None else None
        if m == "online_status" and self.threshold is not None:
            try:
                v = float(self.threshold)
            except Exception:
                raise ValueError("online_status 的阈值必须为 0 或 1")
            if v not in (0.0, 1.0):
                raise ValueError("online_status 的阈值必须为 0 或 1")
        return self

class AlertRuleOut(AlertRuleBase):
    id: int
    device_id: int
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _normalize_out(self):
        m = str(self.metric or "").strip()
        if m == "online_status":
            try:
                v = float(self.threshold)
            except Exception:
                v = 0.0
            if v not in (0.0, 1.0):
                self.threshold = 0.0 if v < 0.5 else 1.0
        return self

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

class AlertLogPagination(BaseModel):
    total: int
    items: List[AlertLogOut]


class AlertSubscriptionBase(BaseModel):
    scope_type: AlertSubscriptionScope
    scope_id: int
    channels: List[AlertSubscriptionChannel] = Field(default_factory=lambda: ["site"])
    severities: Optional[List[AlertSeverity]] = None
    is_enabled: bool = True

    @model_validator(mode="after")
    def _validate_subscription(self):
        ch = [str(x).strip().lower() for x in (self.channels or []) if str(x).strip()]
        allowed = {"site", "email"}
        if not ch:
            raise ValueError("channels 不能为空")
        if any(x not in allowed for x in ch):
            raise ValueError("channels 仅支持 site/email")
        if self.severities is not None:
            sevs = [str(x).strip().lower() for x in (self.severities or []) if str(x).strip()]
            allowed_sev = {"info", "warning", "critical"}
            if any(x not in allowed_sev for x in sevs):
                raise ValueError("severities 仅支持 info/warning/critical")
        return self


class AlertSubscriptionCreate(AlertSubscriptionBase):
    pass


class AlertSubscriptionUpdate(BaseModel):
    channels: Optional[List[AlertSubscriptionChannel]] = None
    severities: Optional[List[AlertSeverity]] = None
    is_enabled: Optional[bool] = None


class AlertSubscriptionOut(AlertSubscriptionBase):
    id: int
    subscriber_user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
