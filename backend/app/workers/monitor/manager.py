import asyncio
import logging
import random
import time
from typing import Dict, Set, Optional
from app.core.database import db
from app.core.redis import redis_manager
from app.drivers.factory import create_device
from app.drivers.base import BaseDevice
from app.core.config import settings

logger = logging.getLogger(__name__)

class MonitorManager:
    _instance = None
    
    def __new__(cls):
        # 使用单例模式创建实例，确保类只有一个实例
        if cls._instance is None:
            cls._instance = super(MonitorManager, cls).__new__(cls)
            # 初始化设备字典，用于存储设备ID到设备对象的映射
            cls._instance.devices: Dict[int, BaseDevice] = {} 
            # 存储监控任务：device_id -> asyncio.Task
            cls._instance.tasks: Dict[int, asyncio.Task] = {} 
            # 运行状态标志
            cls._instance.running = False
            # 初始化Redis管理器
            cls._instance.redis = redis_manager
            # 后台热更新任务
            cls._instance.loader_task: Optional[asyncio.Task] = None
        return cls._instance

    async def start(self):
        """启动监控服务"""
        if self.running:
            return
        
        self.running = True
        logger.info("正在启动监控服务...")
        
        # 清空 Redis 设备状态数据 (防止前端显示旧缓存)
        try:
            redis_client = self.redis.get_client()
            # 使用 keys 获取所有相关 key
            keys = await redis_client.keys("device_status:*")
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"初始化清理: 已删除 {len(keys)} 条旧设备状态缓存")
            else:
                logger.info("初始化清理: 无旧设备状态缓存")
                
            # 同时重置数据库中的设备在线状态，防止 Redis 为空时回退到数据库旧状态
            await db.execute("UPDATE network_devices SET online_status = false")
            logger.info("初始化清理: 已重置所有设备数据库在线状态为离线")
            
        except Exception as e:
            logger.error(f"初始化清理状态失败: {e}")

        # 启动后台设备加载任务（实现数据库热更新）
        # 不再只执行一次 load_devices，而是启动一个循环任务
        self.loader_task = asyncio.create_task(self._device_loader_loop())

    async def stop(self):
        """停止监控服务"""
        self.running = False
        logger.info("正在停止监控服务...")
        
        # 1. 取消热更新任务
        if self.loader_task:
            self.loader_task.cancel()
            try:
                await self.loader_task
            except asyncio.CancelledError:
                pass
        
        # 2. 取消所有设备监控任务
        for task in self.tasks.values():
            task.cancel()
        
        # 等待所有任务结束
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

        # 3. 断开所有设备连接
        for device in self.devices.values():
            await device.disconnect()
        self.devices.clear()

    async def _device_loader_loop(self):
        """
        后台死循环任务：
        每隔 60 秒检查数据库，自动同步设备列表（热更新）。
        """
        logger.info("启动设备列表热更新守护任务")
        while self.running:
            try:
                await self.load_devices()
            except Exception as e:
                logger.error(f"热更新设备列表失败: {e}")
            
            # 等待 60 秒再次检查
            await asyncio.sleep(60)

    async def load_devices(self):
        """从数据库加载设备，并处理新增和删除逻辑"""
        # 查询设备（SSH/Telnet设备）
        sql = """
            SELECT id, device_name, ipv4, user_name, password, device_type 
            FROM network_devices 
        """
        devices_data = await db.fetch_all(sql)
        
        # 记录当前数据库中存在的设备 ID
        db_device_ids: Set[int] = set()
        
        if devices_data:
            # 获取全局配置
            # 默认采集间隔从 60s 调整为 10s，以提供更好的实时体验
            monitor_interval = settings.MONITOR_INTERVAL
            online_check_interval = settings.ONLINE_CHECK_INTERVAL
            
            for d in devices_data:
                device_id = d['id']
                db_device_ids.add(device_id)
                
                # 如果是新设备，则初始化并启动监控
                if device_id not in self.devices:
                    # 使用工厂模式创建设备实例
                    device = create_device(d)
                    
                    # 应用配置
                    device.interval = monitor_interval
                    device.monitor_interval = online_check_interval
                    
                    self.devices[device_id] = device
                    # 启动独立的监控协程
                    task = asyncio.create_task(self._monitor_device_loop(device_id, device))
                    self.tasks[device_id] = task
                    logger.info(f"发现新设备并启动监控: {d['device_name']} ({d['ipv4']})")
        
        # 处理已删除的设备
        # 找出当前内存中有，但数据库中已不存在的设备
        current_ids = set(self.devices.keys())
        remove_ids = current_ids - db_device_ids
        
        for did in remove_ids:
            logger.info(f"设备已删除，停止监控任务: Device ID {did}")
            # 1. 取消任务
            if did in self.tasks:
                self.tasks[did].cancel()
                del self.tasks[did]
            
            # 2. 断开连接并移除对象
            if did in self.devices:
                await self.devices[did].disconnect()
                del self.devices[did]
            
            # 3. 清除 Redis 中的状态
            await self._clear_redis_status(did)

    async def _monitor_device_loop(self, device_id: int, device: BaseDevice):
        """
        单个设备的监控循环
        包含：惊群效应处理、时间漂移消除、异常处理
        """
        # 1. 解决惊群效应：
        # 启动时增加随机延迟 (0-10秒)，避免数百个设备同时发起 SSH 连接冲击服务器
        jitter = random.uniform(0, 10)
        await asyncio.sleep(jitter)
        
        logger.info(f"设备 {device_id} ({device.ip}) 开始监控循环 (Jitter: {jitter:.2f}s)")
        
        # 初始连接尝试
        if not await device.connect():
             logger.warning(f"设备 {device_id} ({device.ip}) 初始连接失败，将在循环中重试")

        # 首次连接成功后，执行一次性静态信息采集
        if device.connected:
             static_info = await device.collect_once()
             if static_info:
                 logger.info(f"设备 {device_id} 静态信息采集成功: {static_info}")
                 # 将静态信息更新到数据库
                 await self._update_device_static_info(device_id, static_info)

        # 记录上一次全量采集的时间点 (使用 monotonic 保证时间单调递增)
        # 初始化为 0，确保进入循环后立即执行一次全量采集
        last_collection_time = 0

        while self.running:
            # 记录循环开始时间，用于消除时间漂移
            loop_start_time = time.monotonic()
            
            try:
                # 1. 快速在线检测
                is_online = await device.check_online()
                
                if is_online:
                    # 2. 检查是否达到全量采集时间间隔
                    current_time = time.monotonic()
                    if current_time - last_collection_time >= device.interval:
                        # 确定使用的协议类型 (根据对象类型推断，或者增加属性)
                        protocol = "SNMP" if hasattr(device, 'snmp_community') and device.snmp_community else "SSH"
                        logger.info(f"开始巡检设备: {device.ip} (协议: {protocol})")
                        
                        data = await device.collect_status()
                        
                        if device.connected and data:
                            # 采集成功，保存数据
                            # logger.debug(f"设备 {device_id} 采集数据: {data}") # 数据仅在 DEBUG 模式显示
                            await self._save_data_redis(device_id, data)
                            last_collection_time = current_time
                        elif not device.connected:
                            logger.warning(f"设备 {device_id} 在采集过程中断开")
                            await self._set_device_offline(device_id)
                    else:
                        # 未到采集时间，仅更新心跳，保持在线状态
                        await self._update_heartbeat(device_id)
                else:
                    # 设备离线处理
                    await self._set_device_offline(device_id)
                    # check_online 内部通常会尝试重连，这里无需额外操作
            
            except asyncio.CancelledError:
                logger.info(f"设备 {device_id} 监控任务被取消")
                break
            except Exception as e:
                logger.error(f"设备 {device_id} 监控循环发生未捕获异常: {e}")
                await self._set_device_offline(device_id)
            
            # 4. 消除时间漂移：
            # 计算本次业务逻辑执行耗时
            elapsed = time.monotonic() - loop_start_time
            # 动态调整休眠时间 = 目标间隔 - 执行耗时
            # device.monitor_interval 是在线检测的频率 (例如 10s)
            sleep_time = max(0, device.monitor_interval - elapsed)
            
            await asyncio.sleep(sleep_time)

    async def _update_device_static_info(self, device_id: int, info: dict):
        """更新设备静态信息到数据库"""
        try:
            # 构建更新 SQL，动态处理字段
            fields = []
            values = []
            idx = 1
            
            # 映射采集字段到数据库字段
            # static_info keys: 'os_version', 'kernel', 'vendor', 'model', 'serial_number'
            # db columns: 'description' (for os_version/kernel), 'vendor', 'model', 'serial_number'
            
            # 目前数据库没有 os_version/kernel 字段，暂时存入 description 或忽略
            # 或者如果之后加了字段再修改这里。
            # 这里先更新已存在的字段
            
            if 'vendor' in info:
                fields.append(f"vendor = ${idx}")
                values.append(info['vendor'])
                idx += 1
            
            if 'model' in info:
                fields.append(f"model = ${idx}")
                values.append(info['model'])
                idx += 1
                
            if 'serial_number' in info:
                fields.append(f"serial_number = ${idx}")
                values.append(info['serial_number'])
                idx += 1
            
            # 特殊处理：将 os_version 存入 Redis 以便前端展示 (因为数据库暂无字段)
            # 或者更新到 description
            redis_updates = {}
            if 'os_version' in info:
                 redis_updates['os_version'] = info['os_version']
            if 'kernel' in info:
                 redis_updates['kernel'] = info['kernel']
            
            if redis_updates:
                 redis_client = self.redis.get_client()
                 key = f"device_status:{device_id}"
                 await redis_client.hset(key, mapping=redis_updates)
                 # 设置过期时间，与 status 一致
                 await redis_client.expire(key, 60) # 注意：这里过期时间可能太短，静态信息应该持久化或长久缓存

            if fields:
                sql = f"UPDATE network_devices SET {', '.join(fields)} WHERE id = ${idx}"
                values.append(device_id)
                await db.execute(sql, *values)
                logger.info(f"更新设备 {device_id} 静态信息到数据库成功")
                
        except Exception as e:
            logger.error(f"更新设备 {device_id} 静态信息失败: {e}")

    async def _update_heartbeat(self, device_id: int):
        """
        仅更新设备的心跳时间
        使用 Redis Pipeline 优化网络 I/O
        """
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            
            # 3. Redis 性能优化：使用 Pipeline 合并指令
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping={
                    "status": "online",
                    "last_updated": str(time.time()) # 使用 wall clock time 供前端显示
                })
                # 续期 key
                await pipe.expire(key, 60)
                # 发布更新事件 (即便是心跳也需要推送，以便前端感知在线状态)
                await pipe.publish(f"device_update:{device_id}", "heartbeat")
                # 批量执行
                await pipe.execute()
                
        except Exception as e:
            logger.error(f"更新设备 {device_id} 心跳失败: {e}")

    async def _save_data_redis(self, device_id: int, data: dict):
        """
        保存详细采集数据到 Redis
        使用 Redis Pipeline 优化
        """
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            
            mapping = {
                "cpu_usage": str(data.get('cpu_usage', 0)),
                "memory_usage": str(data.get('memory_usage', 0)),
                "disk_usage": str(data.get('disk_usage', 0)),
                "status": "online",
                "last_updated": str(time.time())
            }
            if data.get('uptime'):
                 mapping['uptime'] = str(data['uptime'])
            
            expire_seconds = 60 # Default retention
            
            # 使用 Pipeline
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping=mapping)
                await pipe.expire(key, expire_seconds)
                # 发布更新事件
                await pipe.publish(f"device_update:{device_id}", "update")
                await pipe.execute()
            
        except Exception as e:
            logger.error(f"保存设备 {device_id} 数据到 Redis 失败: {e}")

    async def _set_device_offline(self, device_id: int):
        """将设备标记为离线"""
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            await redis_client.hset(key, "status", "offline")
            # 发布更新事件
            await redis_client.publish(f"device_update:{device_id}", "offline")
        except Exception as e:
            logger.error(f"更新设备 {device_id} 离线状态失败: {e}")

    async def _clear_redis_status(self, device_id: int):
        """清除设备的 Redis 数据（用于设备删除时）"""
        try:
            redis_client = self.redis.get_client()
            await redis_client.delete(f"device_status:{device_id}")
        except Exception as e:
            logger.error(f"清除设备 {device_id} Redis 状态失败: {e}")
