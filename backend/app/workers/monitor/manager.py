import asyncio
import json
import logging
import random
import time
from typing import Dict, Set, Optional
from app.core.database import db
from app.core.redis import redis_manager
from app.drivers.factory import create_device
from app.drivers.base import BaseDevice
from app.core.config import settings
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class MonitorManager:
    _instance = None
    BOOST_SET_KEY = "device:boost:set"
    BOOST_KEY_PREFIX = "device:boost:"
    _deleted_at_capable: Optional[bool] = None
    _deleted_at_checked_at: float = 0.0
    
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
            cls._instance.prime_task: Optional[asyncio.Task] = None
            cls._instance.boost_task: Optional[asyncio.Task] = None
            cls._instance._boost_original: Dict[int, dict] = {}
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
            deleted = 0
            batch: list[str] = []
            async for key in redis_client.scan_iter(match="device_status:*", count=1000):
                batch.append(key)
                if len(batch) >= 500:
                    await redis_client.delete(*batch)
                    deleted += len(batch)
                    batch.clear()
            if batch:
                await redis_client.delete(*batch)
                deleted += len(batch)
            if deleted:
                logger.info(f"初始化清理: 已删除 {deleted} 条旧设备状态缓存")
            else:
                logger.info("初始化清理: 无旧设备状态缓存")
                
            # 同时重置数据库中的设备在线状态，防止 Redis 为空时回退到数据库旧状态
            await db.execute("UPDATE network_devices SET online_status = false")
            logger.info("初始化清理: 已重置所有设备数据库在线状态为离线")
            
        except Exception as e:
            logger.error(f"初始化清理状态失败: {e}")

        try:
            await self.load_devices()
        except Exception as e:
            logger.error(f"启动时同步设备列表失败: {e}", exc_info=True)

        try:
            if self.prime_task:
                self.prime_task.cancel()
            self.prime_task = asyncio.create_task(self._prime_startup_statuses())
        except Exception as e:
            logger.error(f"启动时预热设备状态失败: {e}", exc_info=True)

        # 启动后台设备加载任务（实现数据库热更新）
        # 不再只执行一次 load_devices，而是启动一个循环任务
        self.loader_task = asyncio.create_task(self._device_loader_loop())
        try:
            if self.boost_task:
                self.boost_task.cancel()
            self.boost_task = asyncio.create_task(self._boost_loop())
        except Exception as e:
            logger.error(f"启动加速刷新守护任务失败: {e}", exc_info=True)

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

        if self.prime_task:
            self.prime_task.cancel()
            try:
                await self.prime_task
            except asyncio.CancelledError:
                pass
            self.prime_task = None

        if self.boost_task:
            self.boost_task.cancel()
            try:
                await self.boost_task
            except asyncio.CancelledError:
                pass
            self.boost_task = None

        for device in self.devices.values():
            try:
                device.request_shutdown()
            except Exception:
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

    async def _boost_loop(self):
        while self.running:
            try:
                redis_client = self.redis.get_client()
                raw_ids = await redis_client.smembers(self.BOOST_SET_KEY)
                ids: list[int] = []
                for v in raw_ids or []:
                    try:
                        if isinstance(v, bytes):
                            v = v.decode("utf-8")
                        ids.append(int(v))
                    except Exception:
                        continue

                for device_id in ids:
                    key = f"{self.BOOST_KEY_PREFIX}{device_id}"
                    raw = await redis_client.get(key)
                    if not raw:
                        await redis_client.srem(self.BOOST_SET_KEY, device_id)
                        self._restore_device_intervals(device_id)
                        continue
                    try:
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        payload = json.loads(raw)
                    except Exception:
                        payload = None
                    if not isinstance(payload, dict):
                        continue
                    self._apply_device_intervals(device_id, payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(1)

    def _apply_device_intervals(self, device_id: int, payload: dict):
        device = self.devices.get(int(device_id))
        if not device:
            return
        if device_id not in self._boost_original:
            self._boost_original[device_id] = {
                "interval": float(getattr(device, "interval", settings.MONITOR_INTERVAL) or settings.MONITOR_INTERVAL),
                "monitor_interval": float(getattr(device, "monitor_interval", settings.ONLINE_CHECK_INTERVAL) or settings.ONLINE_CHECK_INTERVAL),
            }

        try:
            interval = payload.get("interval")
            monitor_interval = payload.get("monitor_interval")
            if interval is not None:
                device.interval = float(interval)
            if monitor_interval is not None:
                device.monitor_interval = float(monitor_interval)
        except Exception:
            pass

    def _restore_device_intervals(self, device_id: int):
        device = self.devices.get(int(device_id))
        original = self._boost_original.pop(int(device_id), None)
        if not device or not original:
            return
        try:
            device.interval = float(original.get("interval") or settings.MONITOR_INTERVAL)
            device.monitor_interval = float(original.get("monitor_interval") or settings.ONLINE_CHECK_INTERVAL)
        except Exception:
            pass

    async def load_devices(self):
        """从数据库加载设备，并处理新增和删除逻辑"""
        now = time.time()
        if self._deleted_at_capable is None or now - float(self._deleted_at_checked_at or 0.0) >= 60:
            try:
                exists = await db.fetch_val(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'network_devices'
                          AND column_name = 'deleted_at'
                    )
                    """
                )
                self._deleted_at_capable = bool(exists)
            except Exception:
                self._deleted_at_capable = False
            self._deleted_at_checked_at = now

        # 查询设备（SSH/Telnet设备）
        sql = """
            SELECT
                nd.id,
                nd.device_name,
                nd.user_name,
                nd.password,
                nd.ipv4,
                nd.ipv6,
                nd.mac,
                nd.online_status,
                nd.device_type,
                nd.location,
                nd.ssh_port,
                nd.created_by,
                u.username AS created_by_name
            FROM network_devices nd
            LEFT JOIN users u ON u.id::text = nd.created_by
            WHERE COALESCE(nd.is_active, true) = true
        """
        if self._deleted_at_capable:
            sql += " AND nd.deleted_at IS NULL"
        devices_data = await db.fetch_all(sql)

        await self._refresh_device_list_cache(devices_data)
        
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
                try:
                    self.devices[did].request_shutdown()
                except Exception:
                    pass
                await self.devices[did].disconnect()
                del self.devices[did]
            
            # 3. 清除 Redis 中的状态
            await self._clear_redis_status(did)

    async def _refresh_device_list_cache(self, devices_data):
        try:
            if not devices_data:
                return
            redis_client = self.redis.get_client()
            payload = []
            for d in devices_data:
                row = dict(d)
                payload.append(
                    {
                        "id": row.get("id"),
                        "device_name": row.get("device_name") or "",
                        "user_name": row.get("user_name") or "",
                        "ipv4": str(row.get("ipv4") or ""),
                        "ipv6": str(row.get("ipv6") or ""),
                        "mac": str(row.get("mac") or ""),
                        "online_status": bool(row.get("online_status") or False),
                        "device_type": row.get("device_type") or "",
                        "location": row.get("location") or "",
                        "ssh_port": int(row.get("ssh_port") or 22),
                        "created_by": str(row.get("created_by") or ""),
                        "created_by_name": str(row.get("created_by_name") or ""),
                        "ops_admin_name": str(row.get("created_by_name") or ""),
                    }
                )
            await redis_client.set("cache:device_list:v1", json.dumps(payload, ensure_ascii=False), ex=120)
        except Exception as e:
            logger.error(f"刷新设备列表缓存失败: {e}", exc_info=True)

    async def _monitor_device_loop(self, device_id: int, device: BaseDevice):
        """
        单个设备的监控循环
        包含：惊群效应处理、时间漂移消除、异常处理
        """
        # 1. 解决惊群效应：
        # 启动时增加随机延迟 (0-10秒)，避免数百个设备同时发起 SSH 连接冲击服务器
        jitter = random.uniform(0, 2)
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
        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

        while self.running:
            # 记录循环开始时间，用于消除时间漂移
            loop_start_time = time.monotonic()
            
            try:
                # 1. 快速在线检测
                is_online = await device.check_online()
                
                if is_online:
                    changed = device.record_success()
                    if changed and device.fsm_state != "online":
                        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

                    # 2. 检查是否达到全量采集时间间隔
                    current_time = time.monotonic()
                    if device.fsm_state == "online" and current_time - last_collection_time >= device.interval:
                        # 确定使用的协议类型 (根据对象类型推断，或者增加属性)
                        protocol = "SNMP" if hasattr(device, 'snmp_community') and device.snmp_community else "SSH"
                        logger.info(f"开始巡检设备: {device.ip} (协议: {protocol})")
                        
                        data = await device.collect_status()
                        
                        if device.connected and data:
                            # 采集成功，保存数据
                            # logger.debug(f"设备 {device_id} 采集数据: {data}") # 数据仅在 DEBUG 模式显示
                            await self._save_data_redis(device_id, data, fsm_state=device.fsm_state)
                            last_collection_time = current_time
                        elif not device.connected:
                            logger.warning(f"设备 {device_id} 在采集过程中断开")
                            changed, should_offline = device.record_failure("采集过程中断开")
                            if changed:
                                await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                            if should_offline:
                                await self._set_device_offline(device_id, device.fsm_reason)
                    else:
                        # 未到采集时间，仅更新心跳，保持在线状态
                        if device.fsm_state == "online":
                            await self._update_heartbeat(device_id, fsm_state=device.fsm_state)
                else:
                    changed, should_offline = device.record_failure("在线检测失败")
                    if changed:
                        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                    if should_offline:
                        await self._set_device_offline(device_id, device.fsm_reason)
            
            except asyncio.CancelledError:
                logger.info(f"设备 {device_id} 监控任务被取消")
                break
            except Exception as e:
                logger.error(f"设备 {device_id} 监控循环发生未捕获异常: {e}")
                reason = str(e).splitlines()[0] if str(e) else "未捕获异常"
                changed, should_offline = device.record_failure(reason)
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                if should_offline:
                    await self._set_device_offline(device_id, device.fsm_reason)
            
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

    async def _update_fsm_meta(self, device_id: int, fsm_state: str, reason: Optional[str] = None):
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"

            mapping = {
                "fsm_state": str(fsm_state),
                "fsm_updated": str(time.time()),
            }
            if reason is not None:
                mapping["fsm_reason"] = str(reason)

            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping=mapping)
                await pipe.expire(key, 60)
                await pipe.execute()
        except Exception as e:
            logger.error(f"更新设备 {device_id} 状态机元数据失败: {e}")

    async def _update_heartbeat(self, device_id: int, fsm_state: Optional[str] = None):
        """
        仅更新设备的心跳时间
        使用 Redis Pipeline 优化网络 I/O
        """
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            state = fsm_state or "online"
            
            # 3. Redis 性能优化：使用 Pipeline 合并指令
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping={
                    "status": "online",
                    "ever_online": "1",
                    "fsm_state": state,
                    "fsm_reason": "",
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

    async def _save_data_redis(self, device_id: int, data: dict, fsm_state: Optional[str] = None):
        """
        保存详细采集数据到 Redis
        使用 Redis Pipeline 优化
        """
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            state = fsm_state or "online"
            
            mapping = {
                "cpu_usage": str(data.get('cpu_usage', 0)),
                "memory_usage": str(data.get('memory_usage', 0)),
                "disk_usage": str(data.get('disk_usage', 0)),
                "status": "online",
                "ever_online": "1",
                "fsm_state": state,
                "fsm_reason": "",
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

    async def _set_device_offline(self, device_id: int, reason: Optional[str] = None):
        """将设备标记为离线"""
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            current_status = await redis_client.hget(key, "status")
            if current_status == "offline":
                return

            ever_online = await redis_client.hget(key, "ever_online")
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping={
                    "status": "offline",
                    "fsm_state": "offline",
                    "fsm_reason": str(reason) if reason else "",
                    "offline_reason": str(reason) if reason else "",
                    "last_updated": str(time.time())
                })
                await pipe.expire(key, 60)
                await pipe.publish(f"device_update:{device_id}", "offline")
                await pipe.execute()

            if ever_online == "1":
                await NotificationService.notify_device_offline(device_id, reason)
        except Exception as e:
            logger.error(f"更新设备 {device_id} 离线状态失败: {e}")

    async def _clear_redis_status(self, device_id: int):
        """清除设备的 Redis 数据（用于设备删除时）"""
        try:
            redis_client = self.redis.get_client()
            await redis_client.delete(f"device_status:{device_id}")
        except Exception as e:
            logger.error(f"清除设备 {device_id} Redis 状态失败: {e}")

    async def _seed_device_statuses(self, device_ids: list[int]):
        if not device_ids:
            return
        try:
            redis_client = self.redis.get_client()
            now = str(time.time())
            async with redis_client.pipeline(transaction=True) as pipe:
                for device_id in device_ids:
                    await pipe.hset(
                        f"device_status:{device_id}",
                        mapping={
                            "status": "offline",
                            "cpu_usage": "0",
                            "memory_usage": "0",
                            "disk_usage": "0",
                            "fsm_state": "init",
                            "fsm_reason": "",
                            "last_updated": now,
                        },
                    )
                    await pipe.expire(f"device_status:{device_id}", 60)
                await pipe.execute()
        except Exception as e:
            logger.error(f"批量写入设备初始状态失败: {e}", exc_info=True)

    async def _prime_startup_statuses(self):
        device_ids = list(self.devices.keys())
        await self._seed_device_statuses(device_ids)
