
import asyncio
import json
import logging
import random
import time
from typing import Dict, Set, Optional
from app.core.redis import redis_manager
from app.drivers.factory import create_device
from app.drivers.base import BaseDevice
from app.core.config import settings
from app.services.notification_service import NotificationService
from app.models.orm.device import NetworkDevice
from tortoise.expressions import Q

logger = logging.getLogger(__name__)

class MonitorManager:
    _instance = None
    BOOST_SET_KEY = "device:boost:set"
    BOOST_KEY_PREFIX = "device:boost:"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MonitorManager, cls).__new__(cls)
            cls._instance.devices: Dict[int, BaseDevice] = {} 
            cls._instance.tasks: Dict[int, asyncio.Task] = {} 
            cls._instance.running = False
            cls._instance.redis = redis_manager
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
                
            await NetworkDevice.all().update(online_status=False)
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
        
        for task in self.tasks.values():
            task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

        for device in self.devices.values():
            await device.disconnect()
        self.devices.clear()

    async def _device_loader_loop(self):
        logger.info("启动设备列表热更新守护任务")
        while self.running:
            try:
                await self.load_devices()
            except Exception as e:
                logger.error(f"热更新设备列表失败: {e}")
            
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
        # ORM Fetch
        # We need created_by_name (user.username). Join User.
        # Tortoise: NetworkDevice.all().prefetch_related("created_by")? 
        # But created_by is a string field storing ID in current Model (not ForeignKey).
        # We need to fetch Users manually or use raw SQL?
        # Let's stick to fetching users manually.
        
        devices = await NetworkDevice.filter(
            Q(is_active=True) | Q(is_active__isnull=True),
            deleted_at__isnull=True
        ).all()
        
        # Fetch creator names
        user_ids = {int(d.created_by) for d in devices if d.created_by and d.created_by.isdigit()}
        from app.models.orm.user import User
        users = await User.filter(id__in=list(user_ids)).all()
        user_map = {str(u.id): u.username for u in users}
        
        devices_data = []
        for d in devices:
            d_dict = dict(d)
            d_dict['created_by_name'] = user_map.get(d.created_by, "")
            devices_data.append(d_dict)

        await self._refresh_device_list_cache(devices_data)
        
        db_device_ids: Set[int] = set()
        
        if devices_data:
            monitor_interval = settings.MONITOR_INTERVAL
            online_check_interval = settings.ONLINE_CHECK_INTERVAL
            
            for d in devices_data:
                device_id = d['id']
                db_device_ids.add(device_id)
                
                if device_id not in self.devices:
                    device = create_device(d)
                    device.interval = monitor_interval
                    device.monitor_interval = online_check_interval
                    
                    self.devices[device_id] = device
                    task = asyncio.create_task(self._monitor_device_loop(device_id, device))
                    self.tasks[device_id] = task
                    logger.info(f"发现新设备并启动监控: {d['device_name']} ({d['ipv4']})")
        
        current_ids = set(self.devices.keys())
        remove_ids = current_ids - db_device_ids
        
        for did in remove_ids:
            logger.info(f"设备已删除，停止监控任务: Device ID {did}")
            if did in self.tasks:
                self.tasks[did].cancel()
                del self.tasks[did]
            
            if did in self.devices:
                try:
                    self.devices[did].request_shutdown()
                except Exception:
                    pass
                await self.devices[did].disconnect()
                del self.devices[did]
            
            await self._clear_redis_status(did)

    async def _refresh_device_list_cache(self, devices_data):
        try:
            if not devices_data:
                return
            redis_client = self.redis.get_client()
            payload = []
            for row in devices_data:
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
        jitter = random.uniform(0, 2)
        await asyncio.sleep(jitter)
        
        logger.info(f"设备 {device_id} ({device.ip}) 开始监控循环 (Jitter: {jitter:.2f}s)")
        
        if not await device.connect():
             logger.warning(f"设备 {device_id} ({device.ip}) 初始连接失败，将在循环中重试")

        if device.connected:
             static_info = await device.collect_once()
             if static_info:
                 logger.info(f"设备 {device_id} 静态信息采集成功: {static_info}")
                 await self._update_device_static_info(device_id, static_info)

        last_collection_time = 0
        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

        while self.running:
            loop_start_time = time.monotonic()
            
            try:
                is_online = await device.check_online()
                
                if is_online:
                    changed = device.record_success()
                    if changed and device.fsm_state != "online":
                        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

                    current_time = time.monotonic()
                    if device.fsm_state == "online" and current_time - last_collection_time >= device.interval:
                        protocol = "SSH"
                        logger.info(f"开始巡检设备: {device.ip} (协议: {protocol})")
                        
                        data = await device.collect_status()
                        
                        if device.connected and data:
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
            
            elapsed = time.monotonic() - loop_start_time
            sleep_time = max(0, device.monitor_interval - elapsed)
            
            await asyncio.sleep(sleep_time)

    async def _update_device_static_info(self, device_id: int, info: dict):
        try:
            updates = {}
            if 'vendor' in info:
                updates['vendor'] = info['vendor']
            if 'model' in info:
                updates['model'] = info['model']
            if 'serial_number' in info:
                updates['serial_number'] = info['serial_number']
            
            redis_updates = {}
            if 'os_version' in info:
                 redis_updates['os_version'] = info['os_version']
            if 'kernel' in info:
                 redis_updates['kernel'] = info['kernel']
            
            if redis_updates:
                 redis_client = self.redis.get_client()
                 key = f"device_status:{device_id}"
                 await redis_client.hset(key, mapping=redis_updates)
                 await redis_client.expire(key, 60)

            if updates:
                await NetworkDevice.filter(id=device_id).update(**updates)
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
        try:
            redis_client = self.redis.get_client()
            key = f"device_status:{device_id}"
            state = fsm_state or "online"
            
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping={
                    "status": "online",
                    "ever_online": "1",
                    "fsm_state": state,
                    "fsm_reason": "",
                    "last_updated": str(time.time())
                })
                await pipe.expire(key, 60)
                await pipe.publish(f"device_update:{device_id}", "heartbeat")
                await pipe.execute()
                
        except Exception as e:
            logger.error(f"更新设备 {device_id} 心跳失败: {e}")

    async def _save_data_redis(self, device_id: int, data: dict, fsm_state: Optional[str] = None):
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
            
            expire_seconds = 60
            
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping=mapping)
                await pipe.expire(key, expire_seconds)
                await pipe.publish(f"device_update:{device_id}", "update")
                await pipe.execute()
            
        except Exception as e:
            logger.error(f"保存设备 {device_id} 数据到 Redis 失败: {e}")

    async def _set_device_offline(self, device_id: int, reason: Optional[str] = None):
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
