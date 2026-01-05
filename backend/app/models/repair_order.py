from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class RepairOrder:
    id: int
    title: str
    description: str
    submitter_id: int
    priority: str  # 'low', 'medium', 'high', 'emergency'
    status: str    # 'pending', 'processing', 'completed', 'closed', 'cancelled', 'need_info'
    created_at: datetime
    updated_at: datetime
    device_id: Optional[int] = None
    assignee_id: Optional[int] = None
    estimated_time: Optional[datetime] = None
    actual_completion_time: Optional[datetime] = None

@dataclass
class OrderLog:
    id: int
    order_id: int
    operator_id: int
    action: str
    from_status: str
    to_status: str
    created_at: datetime
    remark: Optional[str] = None

@dataclass
class OrderReview:
    id: int
    order_id: int
    rating: int
    created_at: datetime
    comment: Optional[str] = None
    response_time_rating: Optional[int] = None
    service_quality_rating: Optional[int] = None
