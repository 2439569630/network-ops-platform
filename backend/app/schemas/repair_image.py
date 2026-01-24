from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RepairImageCreateResponse(BaseModel):
    id: int
    url: str


class RepairImageResponse(BaseModel):
    id: int
    order_id: Optional[int] = None
    work_log_id: Optional[int] = None
    uploader_id: int
    storage_provider: str
    object_key: str
    url: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class RepairImageUpdate(BaseModel):
    order_id: Optional[int] = Field(default=None)
    work_log_id: Optional[int] = Field(default=None)

