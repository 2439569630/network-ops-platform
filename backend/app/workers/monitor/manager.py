
import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Set, Optional, Any
from app.drivers.factory import create_device
from app.drivers.base import BaseDevice
from app.core.config import settings
from app.core.redis import redis_manager
from app.services.notification_service import NotificationService
from app.models.orm.device import NetworkDevice
from app.models.orm.device import DeviceConfigEntry
from tortoise.expressions import Q

logger = logging.getLogger(__name__)

class MonitorManager:
    _instance = None
    _REDIS_SNAPSHOT_KEY_PREFIX = "monitor:runtime:snapshot:"
    _REDIS_LIST_CHANNEL = "ws:devices:list"
    _REDIS_DETAIL_CHANNEL_PREFIX = "ws:devices:detail:"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MonitorManager, cls).__new__(cls)
            cls._instance.devices: Dict[int, BaseDevice] = {} 
            cls._instance.tasks: Dict[int, asyncio.Task] = {} 
            cls._instance.running = False
            cls._instance.loader_task: Optional[asyncio.Task] = None
            cls._instance.prime_task: Optional[asyncio.Task] = None
            cls._instance.boost_task: Optional[asyncio.Task] = None
            cls._instance._boost_original: Dict[int, dict] = {}
            cls._instance._boost_overrides: Dict[int, dict] = {}
            cls._instance._ws_list_subscribers: Set[asyncio.Queue] = set()
            cls._instance._ws_detail_subscribers: Dict[int, Set[asyncio.Queue]] = defaultdict(set)
        return cls._instance

    async def start(self):
        """启动监控服务"""
        if self.running:
            return
        
        self.running = True
        logger.info("正在启动监控服务...")

        try:
            await self.load_devices()
        except Exception as e:
            logger.error(f"启动时同步设备列表失败: {e}", exc_info=True)

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
        self._ws_list_subscribers.clear()
        self._ws_detail_subscribers.clear()

    def subscribe_list(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._ws_list_subscribers.add(q)
        return q

    def unsubscribe_list(self, q: asyncio.Queue) -> None:
        self._ws_list_subscribers.discard(q)

    def subscribe_detail(self, device_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._ws_detail_subscribers[int(device_id)].add(q)
        return q

    def unsubscribe_detail(self, device_id: int, q: asyncio.Queue) -> None:
        self._ws_detail_subscribers.get(int(device_id), set()).discard(q)

    def _build_status_label(self, device: BaseDevice) -> str:
        st = getattr(device, "status", None)
        if st is not None:
            try:
                label = st.label()
                if label:
                    return str(label)
            except Exception:
                pass
        return "待加载"

    async def get_runtime_snapshot_async(self, device_id: int) -> Dict[str, Any]:
        snap = self.get_runtime_snapshot(int(device_id))
        if snap.get("status") != "待加载":
            return snap
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return snap
        key = f"{self._REDIS_SNAPSHOT_KEY_PREFIX}{int(device_id)}"
        try:
            raw = await redis_client.get(key)
        except Exception:
            raw = None
        if not raw:
            return snap
        try:
            parsed = json.loads(raw)
        except Exception:
            return snap
        if not isinstance(parsed, dict):
            return snap
        return parsed

    def get_runtime_snapshot(self, device_id: int) -> Dict[str, Any]:
        device = self.devices.get(int(device_id))
        if not device:
            return {
                "status": "待加载",
                "cpu_usage": "0%",
                "memory_usage": "0%",
                "disk_usage": "0%",
                "state_phase": "unknown",
                "state_reason": "",
                "state_updated": "",
                "fsm_state": "",
                "fsm_reason": "",
                "fsm_updated": "",
                "uptime": "",
                "last_updated": "",
            }
        status = self._build_status_label(device)
        cpu = float(device.last_metrics.get("cpu_usage", 0) or 0)
        mem = float(device.last_metrics.get("memory_usage", 0) or 0)
        disk = float(device.last_metrics.get("disk_usage", 0) or 0)
        last_updated = max(float(device.last_metrics_updated or 0), float(device.last_heartbeat or 0))
        return {
            "status": status,
            "cpu_usage": f"{cpu}%",
            "memory_usage": f"{mem}%",
            "disk_usage": f"{disk}%",
            "state_phase": str(device.state_phase or ""),
            "state_reason": str(device.state_reason or ""),
            "state_updated": str(device.state_updated or ""),
            "fsm_state": str(device.fsm_state or ""),
            "fsm_reason": str(device.fsm_reason or ""),
            "fsm_updated": str(getattr(device, "fsm_updated", "") or ""),
            "uptime": str(device.last_metrics.get("uptime") or ""),
            "last_updated": str(last_updated or ""),
        }

    async def _persist_snapshot_redis(self, device_id: int, snapshot: dict) -> None:
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return
        key = f"{self._REDIS_SNAPSHOT_KEY_PREFIX}{int(device_id)}"
        try:
            await redis_client.set(key, json.dumps(snapshot, ensure_ascii=False), ex=120)
        except Exception:
            return

    async def _publish_redis(self, channel: str, payload: dict) -> None:
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return
        try:
            await redis_client.publish(str(channel), json.dumps(payload, ensure_ascii=False))
        except Exception:
            return

    async def _publish_list_update(self, device_id: int) -> None:
        if int(device_id) not in self.devices:
            return
        snap = self.get_runtime_snapshot(device_id)
        await self._persist_snapshot_redis(device_id, snap)
        payload = {
            "id": int(device_id),
            "status": snap["status"],
            "cpu_usage": snap["cpu_usage"],
            "memory_usage": snap["memory_usage"],
            "disk_usage": snap["disk_usage"],
            "state_phase": snap.get("state_phase", ""),
            "state_reason": snap.get("state_reason", ""),
            "state_updated": snap.get("state_updated", ""),
        }
        await self._publish_redis(self._REDIS_LIST_CHANNEL, {"type": "update", "data": payload})
        if not self._ws_list_subscribers:
            return
        dead: list[asyncio.Queue] = []
        for q in list(self._ws_list_subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass
            except Exception:
                dead.append(q)
        for q in dead:
            self._ws_list_subscribers.discard(q)

    async def _publish_detail_update(self, device_id: int) -> None:
        if int(device_id) not in self.devices:
            return
        qs = self._ws_detail_subscribers.get(int(device_id))
        payload = self.get_runtime_snapshot(device_id)
        await self._persist_snapshot_redis(device_id, payload)
        await self._publish_redis(f"{self._REDIS_DETAIL_CHANNEL_PREFIX}{int(device_id)}", payload)
        if not qs:
            return
        dead: list[asyncio.Queue] = []
        for q in list(qs):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass
            except Exception:
                dead.append(q)
        for q in dead:
            qs.discard(q)

    async def broadcast_snapshot(self) -> None:
        for device_id in list(self.devices.keys()):
            await self._publish_list_update(device_id)

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
                now = time.time()
                expired: list[int] = []
                for device_id, payload in list(self._boost_overrides.items()):
                    try:
                        expire_at = float(payload.get("expire_at") or 0)
                    except Exception:
                        expire_at = 0
                    if expire_at and now >= expire_at:
                        expired.append(int(device_id))
                        continue
                    if isinstance(payload, dict):
                        self._apply_device_intervals(int(device_id), payload)
                for device_id in expired:
                    self._boost_overrides.pop(int(device_id), None)
                    self._restore_device_intervals(int(device_id))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(1)

    async def boost_device(
        self,
        device_id: int,
        ttl_seconds: int = 60,
        interval: Optional[float] = None,
        monitor_interval: Optional[float] = None,
    ) -> None:
        did = int(device_id)
        ttl = int(ttl_seconds or 60)
        if ttl < 5:
            ttl = 5
        if ttl > 600:
            ttl = 600
        payload: dict[str, Any] = {"expire_at": float(time.time() + ttl)}
        if interval is not None:
            payload["interval"] = float(interval)
        if monitor_interval is not None:
            payload["monitor_interval"] = float(monitor_interval)
        self._boost_overrides[did] = payload
        self._apply_device_intervals(did, payload)

    async def restore_boost(self, device_id: int) -> None:
        did = int(device_id)
        self._boost_overrides.pop(did, None)
        self._restore_device_intervals(did)

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
            overrides: dict[str, Any] = {}
            if interval is not None:
                overrides["interval"] = float(interval)
            if monitor_interval is not None:
                overrides["monitor_interval"] = float(monitor_interval)
            if overrides:
                device.apply_config(device.config.with_overrides(**overrides))
        except Exception:
            pass

    def _restore_device_intervals(self, device_id: int):
        device = self.devices.get(int(device_id))
        original = self._boost_original.pop(int(device_id), None)
        if not device or not original:
            return
        try:
            device.apply_config(
                device.config.with_overrides(
                    interval=float(original.get("interval") or settings.MONITOR_INTERVAL),
                    monitor_interval=float(original.get("monitor_interval") or settings.ONLINE_CHECK_INTERVAL),
                )
            )
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
        
        db_device_ids: Set[int] = set()
        
        if devices_data:
            monitor_interval = settings.MONITOR_INTERVAL
            online_check_interval = settings.ONLINE_CHECK_INTERVAL
            
            for d in devices_data:
                device_id = d['id']
                db_device_ids.add(device_id)
                
                if device_id not in self.devices:
                    device = create_device(d)
                    device.apply_config(
                        device.config.with_overrides(
                            interval=float(monitor_interval or device.interval or 60),
                            monitor_interval=float(online_check_interval or device.monitor_interval or 10),
                        )
                    )
                    
                    self.devices[device_id] = device
                    task = asyncio.create_task(self._monitor_device_loop(device_id, device))
                    self.tasks[device_id] = task
                    await self._update_runtime_status(device_id, "discovered", "task_created")
                    await self._update_state_phase(device_id, "loading", "task_created")
                    logger.info(f"发现新设备并启动监控: {d['device_name']} ({d['ipv4']})")
                else:
                    device = self.devices.get(int(device_id))
                    if device:
                        device.apply_config(
                            device.config.with_overrides(
                                interval=float(monitor_interval or device.interval or 60),
                                monitor_interval=float(online_check_interval or device.monitor_interval or 10),
                            )
                        )

            try:
                cfg_rows = await DeviceConfigEntry.filter(device_id__in=list(db_device_ids)).all()
            except Exception:
                cfg_rows = []
            cfg_map = {int(r.device_id): r for r in cfg_rows}
            for did, device in list(self.devices.items()):
                row = cfg_map.get(int(did))
                if not row:
                    continue
                overrides: dict[str, Any] = {}
                for k in (
                    "interval",
                    "monitor_interval",
                    "offline_fail_threshold",
                    "recovery_success_threshold",
                    "connect_timeout",
                    "auth_timeout",
                    "banner_timeout",
                    "global_delay_factor",
                    "connect_max_retries",
                    "connect_retry_delay_seconds",
                    "offline_retry_delay_seconds",
                ):
                    v = getattr(row, k, None)
                    if v is not None:
                        overrides[k] = v
                if overrides:
                    device.apply_config(device.config.with_overrides(**overrides))
        
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
            self._ws_detail_subscribers.pop(int(did), None)

    async def refresh_device_config(self, device_id: int) -> None:
        did = int(device_id)
        device = self.devices.get(did)
        if not device:
            return
        row = await DeviceConfigEntry.get_or_none(device_id=did)
        if row:
            overrides: dict[str, Any] = {}
            for k in (
                "interval",
                "monitor_interval",
                "offline_fail_threshold",
                "recovery_success_threshold",
                "connect_timeout",
                "auth_timeout",
                "banner_timeout",
                "global_delay_factor",
                "connect_max_retries",
                "connect_retry_delay_seconds",
                "offline_retry_delay_seconds",
            ):
                v = getattr(row, k, None)
                if v is not None:
                    overrides[k] = v
            if overrides:
                device.apply_config(device.config.with_overrides(**overrides))
        await self._publish_list_update(did)
        await self._publish_detail_update(did)

    def get_device_memory_state(self, device_id: int) -> Dict[str, Any]:
        return self.get_runtime_snapshot(int(device_id))

    async def sync_device_snapshot(self, device_id: int) -> Dict[str, Any]:
        did = int(device_id)
        if did in self.devices:
            await self._publish_list_update(did)
            await self._publish_detail_update(did)
        return await self.get_runtime_snapshot_async(did)

    async def _monitor_device_loop(self, device_id: int, device: BaseDevice):
        jitter = random.uniform(0, 2)
        await asyncio.sleep(jitter)
        
        logger.info(f"设备 {device_id} ({device.ip}) 开始监控循环 (Jitter: {jitter:.2f}s)")
        await self._update_state_phase(device_id, "loading", "loop_start")
        await self._update_runtime_status(device_id, "checking", "loop_start")

        async def _connect_progress(phase: str, reason: str) -> None:
            await self._update_state_phase(device_id, phase, reason)
        
        if not await device.connect(progress_cb=_connect_progress):
             logger.warning(f"设备 {device_id} ({device.ip}) 初始连接失败，将在循环中重试")
             reason = str(device.state_reason or device.fsm_reason or "连接失败")
             changed, should_offline = device.record_failure(reason)
             if changed:
                 await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
             await self._update_state_phase(
                 device_id,
                 "failure",
                 f"连接失败({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or reason}",
             )
             if should_offline:
                 await self._set_device_offline(device_id, device.fsm_reason)

        if device.connected:
             static_info = await device.collect_once()
             if static_info:
                 logger.info(f"设备 {device_id} 静态信息采集成功: {static_info}")
                 await self._update_device_static_info(device_id, static_info)

        next_collection_at = 0.0
        offline_retry_at = 0.0
        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

        while self.running:
            loop_start_time = time.monotonic()
            
            try:
                if str(device.fsm_state or "").strip() == "offline":
                    now = time.monotonic()
                    if now < float(offline_retry_at or 0.0):
                        await asyncio.sleep(max(0.0, float(offline_retry_at) - now))
                        continue

                await self._update_runtime_status(device_id, "checking", "online_check")

                is_online = await device.check_online(progress_cb=_connect_progress)
                
                if is_online:
                    offline_retry_at = 0.0
                    changed = device.record_success()
                    if changed:
                        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                        if device.fsm_state in {"online", "recovering"}:
                            await self._update_state_phase(device_id, "loading", "fsm_online")
                            await NetworkDevice.filter(id=device_id).update(
                                online_status=True,
                                last_seen=datetime.now(timezone.utc),
                            )

                    await self._update_heartbeat(device_id, fsm_state=device.fsm_state)

                    now = time.monotonic()
                    if device.fsm_state == "online" and now >= float(next_collection_at or 0.0):
                        protocol = "SSH"
                        logger.info(f"开始巡检设备: {device.ip} (协议: {protocol})")
                        await self._update_state_phase(device_id, "collecting", "collect_start")
                        await self._update_runtime_status(device_id, "collecting", "collecting")

                        try:
                            data = await device.collect_status()
                        except Exception as e:
                            reason = str(e).splitlines()[0] if str(e) else "采集异常"
                            changed, should_offline = device.record_failure(reason)
                            await self._update_state_phase(
                                device_id,
                                "failure",
                                f"采集异常({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or reason}",
                            )
                            if changed:
                                await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                                await self._update_runtime_status(device_id, device.fsm_state, "collect_exception")
                            if should_offline:
                                await self._set_device_offline(device_id, device.fsm_reason)
                                offline_retry_at = time.monotonic() + float(getattr(device.config, "offline_retry_delay_seconds", 30.0) or 30.0)
                            next_collection_at = time.monotonic() + min(10.0, float(device.interval or 60))
                        else:
                            if device.connected and data:
                                await self._save_data_redis(device_id, data, fsm_state=device.fsm_state)
                                next_collection_at = time.monotonic() + float(device.interval or 60)
                            elif not device.connected:
                                logger.warning(f"设备 {device_id} 在采集过程中断开")
                                changed, should_offline = device.record_failure("采集过程中断开")
                                await self._update_state_phase(
                                    device_id,
                                    "failure",
                                    f"采集中断开({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or '采集过程中断开'}",
                                )
                                if changed:
                                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                                    await self._update_runtime_status(device_id, device.fsm_state, "collect_failed")
                                if should_offline:
                                    await self._set_device_offline(device_id, device.fsm_reason)
                                    offline_retry_at = time.monotonic() + float(getattr(device.config, "offline_retry_delay_seconds", 30.0) or 30.0)
                                next_collection_at = time.monotonic() + min(10.0, float(device.interval or 60))
                            else:
                                changed, should_offline = device.record_failure("采集无数据")
                                await self._update_state_phase(
                                    device_id,
                                    "failure",
                                    f"采集无数据({device.consecutive_failures}/{device.offline_fail_threshold})",
                                )
                                if changed:
                                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                                    await self._update_runtime_status(device_id, device.fsm_state, "collect_empty")
                                if should_offline:
                                    await self._set_device_offline(device_id, device.fsm_reason)
                                    offline_retry_at = time.monotonic() + float(getattr(device.config, "offline_retry_delay_seconds", 30.0) or 30.0)
                                await self._update_heartbeat(device_id, fsm_state=device.fsm_state)
                                next_collection_at = time.monotonic() + min(10.0, float(device.interval or 60))
                    else:
                        if device.fsm_state == "online":
                            await self._update_heartbeat(device_id, fsm_state=device.fsm_state)
                else:
                    changed, should_offline = device.record_failure("在线检测失败")
                    await self._update_state_phase(
                        device_id,
                        "failure",
                        f"在线检测失败({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or '在线检测失败'}",
                    )
                    if changed:
                        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                        await self._update_runtime_status(device_id, device.fsm_state, "online_check_failed")
                    if should_offline:
                        await self._set_device_offline(device_id, device.fsm_reason)
                        offline_retry_at = time.monotonic() + float(getattr(device.config, "offline_retry_delay_seconds", 30.0) or 30.0)
            
            except asyncio.CancelledError:
                logger.info(f"设备 {device_id} 监控任务被取消")
                break
            except Exception as e:
                logger.error(f"设备 {device_id} 监控循环发生未捕获异常: {e}")
                reason = str(e).splitlines()[0] if str(e) else "未捕获异常"
                changed, should_offline = device.record_failure(reason)
                await self._update_state_phase(
                    device_id,
                    "failure",
                    f"未捕获异常({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or reason}",
                )
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                    await self._update_runtime_status(device_id, device.fsm_state, "exception")
                if should_offline:
                    await self._set_device_offline(device_id, device.fsm_reason)
                    offline_retry_at = time.monotonic() + float(getattr(device.config, "offline_retry_delay_seconds", 30.0) or 30.0)
            
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

            if updates:
                await NetworkDevice.filter(id=device_id).update(**updates)
                logger.info(f"更新设备 {device_id} 静态信息到数据库成功")
                
        except Exception as e:
            logger.error(f"更新设备 {device_id} 静态信息失败: {e}")

    async def _update_fsm_meta(self, device_id: int, fsm_state: str, reason: Optional[str] = None):
        await self._publish_list_update(device_id)
        await self._publish_detail_update(device_id)

    async def _update_state_phase(self, device_id: int, state_phase: str, reason: Optional[str] = None):
        state = str(state_phase or "").strip() or "unknown"
        if state not in {"init", "loading", "collecting", "success", "failure", "offline", "unknown"}:
            state = "unknown"
        device = self.devices.get(int(device_id))
        if device:
            device.set_state_phase(state, reason)
        await self._publish_list_update(device_id)
        await self._publish_detail_update(device_id)

    async def _update_runtime_status(self, device_id: int, status: str, phase: Optional[str] = None):
        device = self.devices.get(int(device_id))
        if not device:
            return
        s = str(status or "").strip().lower()
        current = str(device.fsm_state or "").strip()
        if s in {"checking", "discovered"}:
            if current in {"", "init", "checking"}:
                if device.status.set_fsm("checking", str(phase or "")):
                    await self._publish_list_update(device_id)
                    await self._publish_detail_update(device_id)
            return

        if s in {"online", "recovering", "degraded", "offline"}:
            if device.status.set_fsm(s, str(phase or device.fsm_reason or "")):
                await self._publish_list_update(device_id)
                await self._publish_detail_update(device_id)
            return

        return

    async def _update_heartbeat(self, device_id: int, fsm_state: Optional[str] = None):
        try:
            device = self.devices.get(int(device_id))
            if device:
                device.last_heartbeat = time.time()
        except Exception as e:
            logger.error(f"更新设备 {device_id} 心跳失败: {e}")

    async def _save_data_redis(self, device_id: int, data: dict, fsm_state: Optional[str] = None):
        try:
            device = self.devices.get(int(device_id))
            if device:
                try:
                    device.last_metrics["cpu_usage"] = float(data.get("cpu_usage", 0) or 0)
                except Exception:
                    device.last_metrics["cpu_usage"] = 0.0
                try:
                    device.last_metrics["memory_usage"] = float(data.get("memory_usage", 0) or 0)
                except Exception:
                    device.last_metrics["memory_usage"] = 0.0
                try:
                    device.last_metrics["disk_usage"] = float(data.get("disk_usage", 0) or 0)
                except Exception:
                    device.last_metrics["disk_usage"] = 0.0
                if data.get("uptime"):
                    device.last_metrics["uptime"] = str(data.get("uptime") or "")
                device.last_metrics_updated = time.time()
                device.set_state_phase("success", "")
            await self._publish_list_update(device_id)
            await self._publish_detail_update(device_id)
        except Exception as e:
            logger.error(f"保存设备 {device_id} 数据失败: {e}")

    async def _set_device_offline(self, device_id: int, reason: Optional[str] = None):
        try:
            device = self.devices.get(int(device_id))
            if device:
                device.set_state_phase("offline", reason)
            await NetworkDevice.filter(id=device_id).update(online_status=False)
            await self._publish_list_update(device_id)
            await self._publish_detail_update(device_id)
            await NotificationService.notify_device_offline(device_id, reason)
        except Exception as e:
            logger.error(f"更新设备 {device_id} 离线状态失败: {e}")

    async def _clear_redis_status(self, device_id: int):
        return

    async def _seed_device_statuses(self, device_ids: list[int]):
        return

    async def _prime_startup_statuses(self):
        return
