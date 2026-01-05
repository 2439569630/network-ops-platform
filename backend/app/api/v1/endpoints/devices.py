
import asyncio
import logging
import json
from fastapi import APIRouter, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect
from typing import List
from app.core.security import verify_token, verify_token_ws
from app.core.redis import redis_manager
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse, DeviceTest, DeviceDelete
from app.services.device_service import device_service

router = APIRouter()
logger = logging.getLogger(__name__)

# 获取设备列表
@router.get("/get", response_model=List[DeviceResponse])
async def get_device(response: Response, type: int = 0, user_data = Depends(verify_token)):
    return await device_service.get_device_list(type)

# 添加设备
@router.post("/add")
async def add_device(device: DeviceCreate, user_data = Depends(verify_token)):
    try:
        user_id = user_data.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="无法获取用户信息")
            
        await device_service.add_device(device, user_id)
        return {"message": "设备添加成功", "code": 200}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"添加设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 删除设备
@router.post("/delete")
async def delete_device(data: DeviceDelete, user_data = Depends(verify_token)):
    try:
        await device_service.delete_device(data.id, data.ip)
        return {"message": "设备删除成功", "code": 200}
    except ValueError as e:
         raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 测试连接
@router.post("/test_connect")
async def test_connect(device: DeviceTest, user_data = Depends(verify_token)):
    try:
        await device_service.test_connect(device)
        return {"message": "连接测试成功", "code": 200}
    except Exception as e:
        logger.error(f"连接测试失败: {e}")
        return {"message": f"连接失败: {str(e)}", "code": 500}

# WebSocket 详情 (重构：使用 app.core.redis)
@router.websocket("/ws/detail/{device_id}")
async def websocket_device_detail(websocket: WebSocket, device_id: int):
    await websocket.accept()
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return

    redis_client = redis_manager.get_client()
    pubsub = redis_client.pubsub()
    
    try:
        channel = f"device_update:{device_id}"
        await pubsub.subscribe(channel)
        
        # 初始数据
        current_data = await redis_client.hgetall(f"device_status:{device_id}")
        if current_data:
             response = format_ws_data(current_data)
             await websocket.send_json(response)

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                current_data = await redis_client.hgetall(f"device_status:{device_id}")
                if current_data:
                    response = format_ws_data(current_data)
                    await websocket.send_json(response)
            await asyncio.sleep(0.1) 
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device {device_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()

@router.websocket("/ws/list")
async def websocket_device_list(websocket: WebSocket):
    """
    WebSocket 设备列表实时更新 (双向通信)
    """
    logger.info("New WebSocket connection request to /ws/list")
    await websocket.accept()
    logger.info("WebSocket accepted")
    
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        logger.warning("WebSocket authentication failed")
        return
    logger.info(f"WebSocket authenticated for user: {user.get('id')}")

    try:
        redis_client = redis_manager.get_client()
        pubsub = redis_client.pubsub()
        logger.info("Redis client obtained")
    except Exception as e:
        logger.error(f"Failed to get Redis client: {e}", exc_info=True)
        await websocket.close()
        return
    
    # WebSocket 发送锁
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        async with ws_lock:
            await websocket.send_json(data)

    # Redis 推送任务
    async def redis_listener():
        try:
            logger.info("Starting Redis listener")
            await pubsub.psubscribe("device_update:*")
            logger.info("Subscribed to device_update:*")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'pmessage':
                    try:
                        channel = message['channel']
                        if isinstance(channel, bytes):
                            channel = channel.decode('utf-8')
                            
                        device_id = int(channel.split(':')[-1])
                        
                        redis_key = f"device_status:{device_id}"
                        status_data = await redis_client.hgetall(redis_key)
                        
                        if status_data:
                            status = '离线'
                            if status_data.get('status') == 'online':
                                status = '在线'
                            
                            update_data = {
                                'id': device_id,
                                'status': status,
                                'cpu_usage': f"{float(status_data.get('cpu_usage', 0))}%",
                                'memory_usage': f"{float(status_data.get('memory_usage', 0))}%",
                                'disk_usage': f"{float(status_data.get('disk_usage', 0))}%"
                            }
                            await send_safe_json({"type": "update", "data": update_data})
                    except Exception as e:
                        logger.error(f"Redis Update Error: {e}", exc_info=True)
                
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Redis Listener Error: {e}", exc_info=True)

    # 启动 Redis 监听
    listener_task = asyncio.create_task(redis_listener())
    
    try:
        logger.info("Entering WS main loop")
        while True:
            # 接收前端指令
            logger.info("Waiting for WS message...")
            data = await websocket.receive_json()
            logger.info(f"Received WS message: {data}")
            command = data.get("command")
            
            if command == "get_list":
                req_type = int(data.get("type", 0))
                search_kw = data.get("search", "")
                logger.info(f"WS Command: get_list type={req_type}, search='{search_kw}'")
                try:
                    # 获取列表并发送
                    initial_data = await device_service.get_device_list(req_type, search_kw)
                    logger.info(f"Got device list data, len: {len(initial_data)}")
                    await send_safe_json({"type": "list", "data": initial_data})
                    logger.info("Sent list data to WS")
                except Exception as e:
                    logger.error(f"Error processing get_list: {e}", exc_info=True)
                
            elif command == "ping":
                await send_safe_json({"type": "pong"})
                
    except WebSocketDisconnect:
        logger.info("WS Disconnected")
    except Exception as e:
        logger.error(f"WS Main Loop Error: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up WS resources")
        listener_task.cancel()
        await pubsub.close()

def format_ws_data(status_data: dict) -> dict:
    status = 'offline'
    if status_data.get('status') == 'online':
        status = 'online'
    elif status_data.get('online_status'):
        status = 'online'
        
    return {
        'status': status,
        'cpuUsage': float(status_data.get('cpu_usage', 0)),
        'memoryUsage': float(status_data.get('memory_usage', 0)),
        'diskUsage': float(status_data.get('disk_usage', 0)),
        'uptime': status_data.get('uptime', '未知'),
        'lastConnect': status_data.get('last_updated', ''),
        'osVersion': status_data.get('os_version', status_data.get('kernel', 'Unknown')),
    }
