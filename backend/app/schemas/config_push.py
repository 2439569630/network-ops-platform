from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ConfigPushJobCreateRequest(BaseModel):
    title: Optional[str] = None
    device_ids: List[int]
    commands: Optional[List[str]] = None
    commands_text: Optional[str] = None


class ConfigPushJobCreateResponse(BaseModel):
    job_id: int
    status: str


class ConfigPushJobItemRow(BaseModel):
    id: int
    device_id: int
    device_name: str
    device_ip: str
    status: str
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ConfigPushJobRow(BaseModel):
    id: int
    title: str
    creator_id: int
    status: str
    command_list: List[str]
    device_count: int
    success_count: int
    fail_count: int
    created_at: datetime
    finished_at: Optional[datetime] = None
    items: List[ConfigPushJobItemRow] = []
