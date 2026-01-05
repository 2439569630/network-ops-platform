import asyncio
from fastapi import APIRouter, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from auth.security import verify_token, verify_token_ws
from DataBase import PostgreSQL
from DataBase.Redis import RedisManager
from netmiko import ConnectHandler
from Monitor.manager import MonitorManager
import logging
import json
import asyncio

router = APIRouter()
redis_manager = RedisManager()
logger = logging.getLogger(__name__)

# ... existing code ...

@router.websocket("/user/device/ws/detail/{device_id}")
async def websocket_device_detail(
    websocket: WebSocket, 
    device_id: int,
):
    """
    WebSocket 实时设备详情
    """
    # 1. 鉴权
    # 注意：FastAPI WebSocket 路由中 Depends 的使用有些限制，
    # 这里我们手动调用 verify_token_ws 或者在 accept 之前处理
    await websocket.accept()
    
    # 获取 token
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return # 连接已在 verify_token_ws 中关闭

    logger.info(f"User {user.get('id')} connected to device {device_id} via WebSocket")

    redis_client = await redis_manager.get_redis()
    pubsub = redis_client.pubsub()
    
    try:
        # 2. 订阅 Redis 频道
        channel = f"device_update:{device_id}"
        await pubsub.subscribe(channel)
        
        # 3. 初始发送一次当前状态
        current_data = await redis_client.hgetall(f"device_status:{device_id}")
        if current_data:
             # 格式化数据
             response = format_ws_data(current_data)
             await websocket.send_json(response)

        # 4. 监听循环
        while True:
            # 等待 Redis 消息
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            
            if message:
                # 收到更新信号，获取最新数据
                current_data = await redis_client.hgetall(f"device_status:{device_id}")
                if current_data:
                    response = format_ws_data(current_data)
                    await websocket.send_json(response)
            
            # 保持连接活跃，并检查客户端是否断开
            # 这里简单通过 sleep 防止死循环占用 CPU，
            # 实际上 pubsub.get_message timeout 已经起到了 yield 的作用
            await asyncio.sleep(0.1) 
            
            # 检测客户端是否还在线? 
            # WebSocket 的 receive_text 会阻塞，不能用在这里因为我们是被动推模式。
            # FastAPI 会在 send_json 失败时抛出 WebSocketDisconnect
            
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

def format_ws_data(status_data: dict) -> dict:
    """格式化 Redis 数据为前端所需格式"""
    status = 'offline'
    if status_data.get('status') == 'online':
        status = 'online'
    elif status_data.get('online_status'): # 兼容旧字段
        status = 'online'
        
    return {
        'status': status,
        'cpuUsage': float(status_data.get('cpu_usage', 0)),
        'memoryUsage': float(status_data.get('memory_usage', 0)),
        'diskUsage': float(status_data.get('disk_usage', 0)),
        'uptime': status_data.get('uptime', '未知'),
        'lastConnect': status_data.get('last_updated', ''),
        # 动态更新的静态信息（如果有）
        'osVersion': status_data.get('os_version', status_data.get('kernel', 'Unknown')),
    }


class DeviceAdd(BaseModel):
    device_name: str
    user_name: str
    password: str
    type: str
    ipv4: str
    ipv6: Optional[str] = None
    mac: Optional[str] = None
    location: Optional[str] = None
    ssh_port: int = 22

class DeviceTest(BaseModel):
    ipv4: str
    ssh_port: int = 22
    user_name: str
    password: str
    type: str

class DeviceDelete(BaseModel):
    id: Optional[int] = None
    ip: Optional[str] = None

# 添加设备
@router.post("/user/device/add")
async def add_device(device: DeviceAdd, user_data = Depends(verify_token)):
    try:
        # 检查IP是否已存在
        check_sql = "SELECT id FROM network_devices WHERE ipv4 = $1"
        exists = await PostgreSQL.execute(check_sql, device.ipv4, fetch_val=True)
        if exists:
            raise HTTPException(status_code=400, detail="该IP地址已存在")

        sql = """
            INSERT INTO network_devices 
            (device_name, ipv4, ipv6, mac, device_type, user_name, password, location, ssh_port, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
        """
        # 处理空字符串为None
        ipv6 = device.ipv6 if device.ipv6 and device.ipv6.strip() else None
        mac = device.mac if device.mac and device.mac.strip() else None
        location = device.location if device.location and device.location.strip() else None

        # 获取当前用户ID
        user_id = user_data.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="无法获取用户信息")

        logger.info(f"添加设备参数处理后: ipv6={ipv6!r}, mac={mac!r}, location={location!r}, user_id={user_id}")

        sql = """
            INSERT INTO network_devices 
            (device_name, ipv4, ipv6, mac, device_type, user_name, password, location, ssh_port, created_by, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
        """

        await PostgreSQL.execute(
            sql,
            device.device_name,
            device.ipv4,
            ipv6,
            mac,
            device.type,
            device.user_name,
            device.password,
            location,
            device.ssh_port,
            str(user_id)
        )

        # 触发监控服务加载新设备
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

        return {"message": "设备添加成功", "code": 200}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"添加设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 测试连接
@router.post("/user/device/test_connect")
async def test_connect(device: DeviceTest, user_data = Depends(verify_token)):
    try:
        # 映射设备类型到 Netmiko device_type
        netmiko_device_type = 'linux'
        if device.type in ['路由器', '交换机', '防火墙', 'huawei']:
            netmiko_device_type = 'huawei'
        elif device.type == '服务器':
            netmiko_device_type = 'linux'
            
        params = {
            'device_type': netmiko_device_type,
            'host': device.ipv4,
            'port': device.ssh_port,
            'username': device.user_name,
            'password': device.password,
            'timeout': 10
        }
        
        def _connect():
            conn = ConnectHandler(**params)
            conn.disconnect()
            return True

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _connect)
        
        return {"message": "连接测试成功", "code": 200}
    except Exception as e:
        logger.error(f"连接测试失败: {e}")
        return {"message": f"连接失败: {str(e)}", "code": 500}

# 删除设备
@router.post("/user/device/delete")
async def delete_device(data: DeviceDelete, user_data = Depends(verify_token)):
    try:
        if data.id:
            sql = "DELETE FROM network_devices WHERE id = $1"
            await PostgreSQL.execute(sql, data.id)
        elif data.ip:
            sql = "DELETE FROM network_devices WHERE ipv4 = $1"
            await PostgreSQL.execute(sql, data.ip)
        else:
             raise HTTPException(status_code=400, detail="必须提供设备ID或IP地址")
             
        # 触发监控服务加载新设备
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")
            
        return {"message": "设备删除成功", "code": 200}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"删除设备失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 获取设备 从数据库和Redis读取
@router.get("/user/device/get")
async def get_device(response: Response, type: int = 0, user_data = Depends(verify_token)):
    return await fetch_device_list_data(type)

async def fetch_device_list_data(type_code: int = 0, search_query: str = None):
    # 1. 获取基础信息
    sql = """
        SELECT 
            id, device_name, ipv4, ipv6, mac, online_status, device_type, location, ssh_port
        FROM network_devices
    """
    
    where_clauses = []
    params = []
    param_idx = 1

    if type_code == 1: # Router
        where_clauses.append("device_type IN ('router', '路由器', 'huawei')")
    elif type_code == 2: # Switch
        where_clauses.append("device_type IN ('switch', '交换机')")
    elif type_code == 3: # Firewall
        where_clauses.append("device_type IN ('firewall', '防火墙')")
    elif type_code == 4: # Server
        where_clauses.append("device_type IN ('server', '服务器', 'linux')")
    
    if search_query:
        # 支持搜索设备名、IP、位置
        where_clauses.append(f"(device_name ILIKE ${param_idx} OR ipv4::text ILIKE ${param_idx} OR location ILIKE ${param_idx})")
        params.append(f"%{search_query}%")
        param_idx += 1
        
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    try:
        result = await PostgreSQL.execute(sql, *params, fetch=True)
        logger.info(f"Fetched {len(result) if result else 0} devices from DB for type {type_code}, search '{search_query}'")
    except Exception as e:
        logger.error(f"DB Fetch Error: {e}")
        return []
    
    data = []
    if result:
        redis_client = None
        try:
            redis_client = await redis_manager.get_redis()
        except Exception as e:
            logger.error(f"Redis Connection Error: {e}")
            # Redis 连接失败，继续执行，但无法获取实时状态

        for row in result:
            try:
                # 默认值
                cpu_usage = '0%'
                memory_usage = '0%'
                disk_usage = '0%'
                status = '待加载' # 默认为待加载，等待 Redis 数据确认

                # 2. 从 Redis 获取实时状态
                if redis_client:
                    try:
                        device_id = row['id']
                        redis_key = f"device_status:{device_id}"
                        status_data = await redis_client.hgetall(redis_key)
                        
                        # 优先使用 Redis 中的实时状态
                        if status_data:
                            cpu_usage = f"{float(status_data.get('cpu_usage', 0))}%"
                            memory_usage = f"{float(status_data.get('memory_usage', 0))}%"
                            disk_usage = f"{float(status_data.get('disk_usage', 0))}%"
                            if status_data.get('status') == 'online':
                                status = '在线'
                            elif status_data.get('status') == 'offline':
                                status = '离线'
                        # 如果 Redis 中没有数据，且数据库标记为离线（可能是刚启动重置的），则保持“待加载”
                        # 只有当明确知道是离线时（Redis中有记录），才显示离线。
                        # 或者，如果 Redis 为空，我们认为它还没被检测到。
                        
                    except Exception as e:
                        logger.error(f"Redis get error for device {row['id']}: {e}")

                # 数据库兜底状态
                if status == '待加载' and row.get('online_status'):
                     status = '在线'
                # 如果数据库说是离线，且 Redis 为空，那么它就是“待加载”（因为我们刚启动时重置了数据库）
                # 如果是运行很久后，Redis key过期，也会变回待加载，这其实是合理的，说明监控数据断档了。
                # 但如果用户希望看到最后已知状态，可能需要数据库持久化最后一次离线时间。
                # 目前逻辑：Redis无数据 -> 待加载。
                
                # 特殊处理：如果 Redis 没连接上，回退到离线？不，待加载也行。

                data.append({
                    'id': row['id'],
                    'device_name': row['device_name'],
                    'ipv4': str(row['ipv4']) if row['ipv4'] else '',
                    'ipv6': str(row['ipv6']) if row['ipv6'] else '',
                    'mac': str(row['mac']) if row['mac'] else '',
                    'status': status,
                    'type': row['device_type'],
                    'location': row['location'],
                    'ssh_port': row['ssh_port'],
                    'cpu_usage': cpu_usage,
                    'memory_usage': memory_usage,
                    'disk_usage': disk_usage,
                    'network_traffic': '0Mbps', 
                    'network_connections': '0'
                })
            except Exception as e:
                logger.error(f"Row processing error: {e}")
                continue
             
    return data

@router.websocket("/user/device/ws/list")
async def websocket_device_list(websocket: WebSocket):
    """
    WebSocket 设备列表实时更新 (双向通信)
    """
    await websocket.accept()
    
    token = websocket.query_params.get("token")
    # type_code = int(websocket.query_params.get("type", 0)) # 移除 URL 参数依赖，改用指令
    
    user = await verify_token_ws(websocket, token)
    if not user:
        return

    redis_client = await redis_manager.get_redis()
    pubsub = redis_client.pubsub()
    
    # WebSocket 发送锁，防止并发写入冲突
    ws_lock = asyncio.Lock()

    async def send_safe_json(data):
        async with ws_lock:
            await websocket.send_json(data)

    # Redis 推送任务
    async def redis_listener():
        try:
            await pubsub.psubscribe("device_update:*")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'pmessage':
                    try:
                        channel = message['channel']
                        # Redis 的 Python 客户端返回的 channel 可能是 bytes 也可能是 str，取决于 decode_responses 配置
                        # 如果没有配置 decode_responses=True，则默认为 bytes
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
                        logger.error(f"Redis Update Error: {e}")
                
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Redis Listener Error: {e}")

    # 启动 Redis 监听
    listener_task = asyncio.create_task(redis_listener())
    
    try:
        while True:
            # 接收前端指令
            data = await websocket.receive_json()
            command = data.get("command")
            
            if command == "get_list":
                req_type = int(data.get("type", 0))
                search_kw = data.get("search", "")
                logger.info(f"WS Command: get_list type={req_type}, search='{search_kw}'")
                # 获取列表并发送
                initial_data = await fetch_device_list_data(req_type, search_kw)
                await send_safe_json({"type": "list", "data": initial_data})
                
            elif command == "ping":
                await send_safe_json({"type": "pong"})
                
    except WebSocketDisconnect:
        logger.info("WS Disconnected")
    except Exception as e:
        logger.error(f"WS Main Loop Error: {e}")
    finally:
        listener_task.cancel()
        await pubsub.close()

# 获取单个设备详情
@router.get("/user/device/detail/{device_id}")
async def get_device_detail(device_id: int, user_data = Depends(verify_token)):
    # 1. 获取数据库基础信息
    sql = """
        SELECT 
            id, device_name, ipv4, ipv6, mac, online_status, device_type, location, 
            ssh_port, user_name, created_at, snmp_version, vendor, model, serial_number
        FROM network_devices
        WHERE id = $1
    """
    row = await PostgreSQL.execute(sql, device_id, fetch_row=True)
    
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")
        
    # 2. 获取 Redis 实时状态
    redis_client = await redis_manager.get_redis()
    redis_key = f"device_status:{device_id}"
    status_data = await redis_client.hgetall(redis_key)
    
    # 默认值
    cpu_usage = 0
    memory_usage = 0
    disk_usage = 0
    uptime = '未知'
    status = 'offline'
    last_updated = ''
    os_version = 'Unknown' # 数据库中暂无此字段
    
    if status_data:
        cpu_usage = float(status_data.get('cpu_usage', 0))
        memory_usage = float(status_data.get('memory_usage', 0))
        disk_usage = float(status_data.get('disk_usage', 0))
        uptime = status_data.get('uptime', '未知')
        if status_data.get('status') == 'online':
            status = 'online'
        last_updated = status_data.get('last_updated', '')
        # 如果 Redis 中有采集到的版本信息，也可以用
        if status_data.get('os_version'):
             os_version = status_data.get('os_version')
        elif status_data.get('kernel'):
             os_version = status_data.get('kernel')

    elif row['online_status']:
        status = 'online'
        
    # 构造返回数据
    return {
        'id': row['id'],
        'name': row['device_name'],
        'type': row['device_type'],
        'ip': str(row['ipv4']) if row['ipv4'] else '',
        'status': status,
        'vendor': row['vendor'] or 'Unknown',
        'model': row['model'] or 'Unknown',
        'serialNumber': row['serial_number'] or 'Unknown',
        'location': row['location'] or '未知',
        'snmpVersion': row['snmp_version'] or 'v2c',
        'osVersion': os_version,
        'cpuUsage': cpu_usage,
        'memoryUsage': memory_usage,
        'diskUsage': disk_usage,
        'uptime': uptime,
        'sshPort': row['ssh_port'],
        'sshUser': row['user_name'],
        'lastConnect': last_updated,
        # 下面是 Mock 数据，后续可从数据库读取
        'interfaces': [
            { 'name': 'GigabitEthernet0/0/1', 'status': 'Up', 'ip': str(row['ipv4']), 'inTraffic': '120 Mbps', 'outTraffic': '300 Mbps' },
            { 'name': 'GigabitEthernet0/0/2', 'status': 'Down', 'ip': '--', 'inTraffic': '0 Mbps', 'outTraffic': '0 Mbps' }
        ],
        'alerts': []
    }
