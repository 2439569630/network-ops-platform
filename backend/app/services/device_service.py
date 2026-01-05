
import asyncio
import logging
from typing import List, Optional, Dict
from fastapi import HTTPException
from app.core.database import db
from app.core.redis import redis_manager
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.drivers.factory import create_device
from app.workers.monitor.manager import MonitorManager
from netmiko import ConnectHandler

logger = logging.getLogger(__name__)

class DeviceService:
    async def get_device_list(self, type_code: int = 0, search_query: str = None) -> List[dict]:
        logger.info(f"Start get_device_list: type={type_code}, search={search_query}")
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
            where_clauses.append(f"(device_name ILIKE ${param_idx} OR ipv4::text ILIKE ${param_idx} OR location ILIKE ${param_idx})")
            params.append(f"%{search_query}%")
            param_idx += 1
            
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        try:
            logger.info(f"Executing DB query: {sql} params={params}")
            result = await db.fetch_all(sql, *params)
            logger.info(f"DB query result count: {len(result) if result else 0}")
        except Exception as e:
            logger.error(f"DB Fetch Error: {e}", exc_info=True)
            return []
        
        data = []
        if result:
            redis_client = None
            try:
                redis_client = redis_manager.get_client()
                logger.info("Got Redis client successfully")
            except Exception as e:
                logger.error(f"Redis Connection Error: {e}", exc_info=True)

            for row in result:
                try:
                    # 默认值
                    cpu_usage = '0%'
                    memory_usage = '0%'
                    disk_usage = '0%'
                    status = '待加载'

                    # 2. 从 Redis 获取实时状态
                    if redis_client:
                        try:
                            device_id = row['id']
                            redis_key = f"device_status:{device_id}"
                            status_data = await redis_client.hgetall(redis_key)
                            
                            if status_data:
                                cpu_usage = f"{float(status_data.get('cpu_usage', 0))}%"
                                memory_usage = f"{float(status_data.get('memory_usage', 0))}%"
                                disk_usage = f"{float(status_data.get('disk_usage', 0))}%"
                                if status_data.get('status') == 'online':
                                    status = '在线'
                                elif status_data.get('status') == 'offline':
                                    status = '离线'
                        except Exception as e:
                            logger.error(f"Redis get error for device {row['id']}: {e}")

                    # 数据库兜底
                    if status == '待加载' and row.get('online_status'):
                         status = '在线'

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
                    })
                except Exception as e:
                    logger.error(f"Row processing error: {e}", exc_info=True)
                    continue
        
        logger.info(f"Returning {len(data)} devices")
        return data

    async def add_device(self, device: DeviceCreate, user_id: int):
        # 检查IP是否已存在
        check_sql = "SELECT id FROM network_devices WHERE ipv4 = $1"
        exists = await db.fetch_val(check_sql, device.ipv4)
        if exists:
            raise ValueError("该IP地址已存在")

        sql = """
            INSERT INTO network_devices 
            (device_name, ipv4, ipv6, mac, device_type, user_name, password, location, ssh_port, created_by, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
        """
        
        ipv6 = device.ipv6 if device.ipv6 and device.ipv6.strip() else None
        mac = device.mac if device.mac and device.mac.strip() else None
        location = device.location if device.location and device.location.strip() else None

        await db.execute(
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

        # 触发监控加载
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def delete_device(self, device_id: Optional[int] = None, ip: Optional[str] = None):
        if device_id:
            sql = "DELETE FROM network_devices WHERE id = $1"
            await db.execute(sql, device_id)
        elif ip:
            sql = "DELETE FROM network_devices WHERE ipv4 = $1"
            await db.execute(sql, ip)
        else:
             raise ValueError("必须提供设备ID或IP地址")
             
        # 触发监控加载
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def test_connect(self, device: DeviceCreate):
        # 映射设备类型
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
        return True

device_service = DeviceService()
