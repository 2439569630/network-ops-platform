from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class RepairOrderCreate(BaseModel):
    """工单创建模型"""
    title: str
    description: str
    priority: str = 'medium'
    device_id: Optional[int] = None
    location_id: Optional[int] = None

class RepairOrderUpdate(BaseModel):
    """工单更新模型"""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    device_id: Optional[int] = None
    assignee_id: Optional[int] = None
    estimated_time: Optional[datetime] = None

class OrderReviewCreate(BaseModel):
    """工单评价创建模型"""
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    response_time_rating: Optional[int] = Field(None, ge=1, le=5)
    service_quality_rating: Optional[int] = Field(None, ge=1, le=5)

class OrderLogResponse(BaseModel):
    """工单日志响应模型"""
    id: int
    order_id: int
    operator_id: int
    action: str
    from_status: str
    to_status: str
    remark: Optional[str]
    created_at: datetime

class OrderReviewResponse(BaseModel):
    """工单评价响应模型"""
    id: int
    order_id: int
    rating: int
    comment: Optional[str]
    response_time_rating: Optional[int]
    service_quality_rating: Optional[int]
    created_at: datetime

class RepairOrderResponse(BaseModel):
    """工单详情响应模型"""
    id: int
    title: str
    description: str
    submitter_id: int
    device_id: Optional[int]
    location_id: Optional[int]
    priority: str
    status: str
    assignee_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    estimated_time: Optional[datetime]
    actual_completion_time: Optional[datetime]
    submitter_name: Optional[str] = None
    assignee_name: Optional[str] = None
    device_name: Optional[str] = None
    location_name: Optional[str] = None
    logs: Optional[List[OrderLogResponse]] = None
    review: Optional[OrderReviewResponse] = None
