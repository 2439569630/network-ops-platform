import random
from os.path import join

from fastapi import APIRouter, Depends, Response
import asyncio
from fastapi.responses import StreamingResponse
from pydantic.v1 import BaseModel
from starlette.routing import Match

from auth.security import verify_token

router = APIRouter()

# 添加设备
@router.post("/user/device/add")
async def add_device():
    async def generate():
        for i in range(20):
            yield f"第{i+1}部分数据\n"
            await asyncio.sleep(0.3)
    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
            "responseType": 'stream'
        }
    )

class DeviceType(BaseModel):
    type: int

# 获取设备 从redis里读取
@router.get("/user/device/get")
async def get_device(response: Response, user_data = Depends(verify_token)):
    date = []
    for i in range(random.randint(1, 200)):
        date.append({
            'device_name': '日志服务器'+ join(str(i)),
            'ipv4': '192.168.1.18',
            'ipv6': '2001:0db8:85a3:0000:0000:8a2e:0370:7353',
            'mac': '00:1A:2B:3C:4D:71',
            'status': '在线',
            'type': '服务器',
            'location': '无锡',
            'cpu_usage': '35%',
            'memory_usage': '55%',
            'disk_usage': '80%',
            'network_traffic': '70Mbps',
            'network_connections': '160'
        })
    return date
