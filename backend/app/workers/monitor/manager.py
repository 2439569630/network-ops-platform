
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
from app.workers.monitor.alert_handler import AlertHandler
from tortoise.expressions import Q

logger = logging.getLogger(__name__)

class MonitorManager:
    """
    监控管理器
    核心单例类，负责管理所有设备监控任务、状态维护、数据采集调度以及 WebSocket/Redis 消息广播。
    """
    # 单例实例，确保 MonitorManager 全局唯一
    _instance = None
    # Redis 中用于缓存设备实时快照的 key 前缀
    _REDIS_SNAPSHOT_KEY_PREFIX = "monitor:runtime:snapshot:"
    # Redis 发布/订阅频道：设备列表更新广播
    _REDIS_LIST_CHANNEL = "ws:devices:list"
    # Redis 发布/订阅频道前缀：单个设备详情更新广播，需拼接设备 ID
    _REDIS_DETAIL_CHANNEL_PREFIX = "ws:devices:detail:"
    
    def __new__(cls):
        """
        必应：单例模式实现
        确保 MonitorManager 全局只有一个实例，并在首次创建时初始化所有运行时容器。
        线程/协程安全由 CPython GIL 与 asyncio 事件循环保证。
        """
        if cls._instance is None:
            cls._instance = super(MonitorManager, cls).__new__(cls)
            # 设备实例映射：device_id -> BaseDevice
            cls._instance.devices: Dict[int, BaseDevice] = {}
            # 设备监控任务映射：device_id -> asyncio.Task
            cls._instance.tasks: Dict[int, asyncio.Task] = {}
            # 全局运行标志
            cls._instance.running = False
            # 设备列表热加载后台任务
            cls._instance.loader_task: Optional[asyncio.Task] = None
            # 预留的“主”后台任务（当前未使用）
            cls._instance.prime_task: Optional[asyncio.Task] = None
            # 设备加速刷新定时器后台任务
            cls._instance.boost_task: Optional[asyncio.Task] = None
            # 加速前的原始采集间隔快照：device_id -> {"interval": x, "monitor_interval": y}
            cls._instance._boost_original: Dict[int, dict] = {}
            # 当前生效的加速覆盖配置：device_id -> {"expire_at": ts, ...}
            cls._instance._boost_overrides: Dict[int, dict] = {}
            # WebSocket 广播订阅队列集合：设备列表频道
            cls._instance._ws_list_subscribers: Set[asyncio.Queue] = set()
            # WebSocket 广播订阅队列映射：设备详情频道，device_id -> Set[asyncio.Queue]
            cls._instance._ws_detail_subscribers: Dict[int, Set[asyncio.Queue]] = defaultdict(set)
            
            # 告警处理器
            cls._instance.alert_handler = AlertHandler()
        return cls._instance

    async def start(self):
        """启动监控服务"""
        if self.running:
            logger.warning("监控服务已在运行中，重复调用 start() 无效果")
            return
        
        self.running = True
        logger.info("正在启动监控服务...")

        try:
            # 启动时立即加载一次数据库中的设备，初始化 devices 与 tasks 映射
            await self.load_devices()
            # 加载告警规则
            await self.alert_handler.load_alert_rules()
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

    def _normalize_static_info(self, info: Any) -> dict:
        if isinstance(info, dict):
            return info
        to_dict = getattr(info, "to_dict", None)
        if callable(to_dict):
            try:
                data = to_dict()
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}
        return {}

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
        # 计算最后更新时间：取 指标更新时间 和 心跳时间 的较大值
        last_updated = max(float(device.last_metrics_updated or 0), float(device.last_heartbeat or 0))
        
        # 构建基础快照
        snapshot = {
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
        
        # 动态合并 last_metrics 中的其他字段（如 version, os_version 等）
        # 排除已显式处理的标准字段，避免覆盖格式化后的数据（如 cpu_usage 已加 % 号）
        exclude_keys = {"cpu_usage", "memory_usage", "disk_usage", "uptime"}
        for k, v in device.last_metrics.items():
            if k not in exclude_keys:
                snapshot[k] = v
                
        return snapshot

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
        logger.info("正在从数据库加载设备...")
        # 查询所有未被逻辑删除且处于激活状态（或激活字段为空）的设备记录
        # Q 对象用于组合查询条件：is_active=True 或 is_active 为空，同时 deleted_at 为空表示未删除
        # 将数据库的数据写入数据模型
        devices = await NetworkDevice.filter(
            Q(is_active=True) | Q(is_active__isnull=True),
            deleted_at__isnull=True
        ).all()
        
        # 收集所有设备记录中 created_by 字段为合法数字的用户 ID
        user_ids = {int(d.created_by) for d in devices if d.created_by and d.created_by.isdigit()}
        # 按需导入 User 模型
        from app.models.orm.user import User
        # 批量查询这些用户，获取其 username
        users = await User.filter(id__in=list(user_ids)).all()
        # 建立 user_id -> username 的映射，方便后续填充 created_by_name
        user_map = {str(u.id): u.username for u in users}
        
        # 将 ORM 设备对象列表转换为纯字典列表，并补充 created_by_name 字段
        devices_data = []
        for d in devices:
            d_dict = dict(d)  # 将 ORM 实例转为字典，方便后续处理
            d_dict['created_by_name'] = user_map.get(d.created_by, "")  # 根据 user_map 回填创建人用户名
            devices_data.append(d_dict)
        
        # 初始化数据库中存在的设备 ID 集合，后续用于比对本地缓存与数据库差异
        db_device_ids: Set[int] = set()
        
        # 遍历所有设备记录
        if devices_data:
            # 从全局配置读取默认的监控采集间隔（秒），用于设备首次加载或配置缺失时兜底
            monitor_interval = settings.MONITOR_INTERVAL
            # 从全局配置读取默认的在线检测间隔（秒），用于设备首次加载或配置缺失时兜底
            online_check_interval = settings.ONLINE_CHECK_INTERVAL
            
            # 遍历本次从数据库拉取到的所有设备字典
            for d in devices_data:
                device_id = d['id']                      # 取出设备主键
                db_device_ids.add(device_id)             # 记录到“数据库存在”集合，用于后续删除比对

                # 若本地缓存中尚未存在该设备，则视为“新增设备”
                if device_id not in self.devices:
                    logger.info(f"发现新增设备: {d['device_name']} ({d['ipv4']})")
                    # 根据字典创建设备驱动实例
                    device = create_device(d)
                    # 使用全局默认间隔兜底，注入配置（首次加载保证有值）
                    device.apply_config(
                        device.config.with_overrides(
                            interval=float(monitor_interval or device.interval or 60),
                            monitor_interval=float(online_check_interval or device.monitor_interval or 10),
                        )
                    )
                    
                    # 注册到本地缓存
                    self.devices[device_id] = device
                    # 启动独立协程负责该设备的整个生命周期监控
                    task = asyncio.create_task(self._monitor_device_loop(device_id, device))
                    self.tasks[device_id] = task
                    # 发布内部状态：已发现 / 加载中
                    await self._update_runtime_status(device_id, "discovered", "task_created")
                    await self._update_state_phase(device_id, "loading", "task_created")
                    logger.info(f"发现新设备并启动监控: {d['device_name']} ({d['ipv4']})")
                else:
                    # 设备已存在，仅应用最新全局默认间隔（后续 DeviceConfigEntry 可再次覆盖）
                    device = self.devices.get(int(device_id))
                    if device:
                        device.apply_config(
                            device.config.with_overrides(
                                interval=float(monitor_interval or device.interval or 60),
                                monitor_interval=float(online_check_interval or device.monitor_interval or 10),
                            )
                        )
            # 批量查询 DeviceConfigEntry 表，获取所有已加载设备的个性化配置
            try:
                cfg_rows = await DeviceConfigEntry.filter(device_id__in=list(db_device_ids)).all()
            except Exception:
                # 查询失败时降级处理：使用空列表，后续逻辑会跳过配置覆盖
                cfg_rows = []
            # 将 DeviceConfigEntry 查询结果转换为以 device_id 为键的字典，方便后续 O(1) 快速查找
            cfg_map = {int(r.device_id): r for r in cfg_rows}
            # 遍历当前已加载到内存的所有设备实例（使用 list 包裹避免字典遍历时被并发修改）
            for did, device in list(self.devices.items()):
                # 根据设备 ID 从配置映射中查找对应的个性化配置记录
                row = cfg_map.get(int(did))
                # 若该设备在 DeviceConfigEntry 中没有记录，则跳过，保持默认全局配置
                if not row:
                    continue
                # 初始化一个空字典，用于收集需要覆盖到设备驱动的配置项
                overrides: dict[str, Any] = {}
                # 以下字段均为 DeviceConfigEntry 表中可自定义的监控/连接参数
                for k in (
                    "interval",                    # 数据采集间隔（秒）
                    "monitor_interval",            # 在线检测间隔（秒）
                    "offline_fail_threshold",      # 连续失败多少次后标记为离线
                    "recovery_success_threshold",  # 连续成功多少次后标记为恢复
                    "connect_timeout",             # 连接超时（秒）
                    "auth_timeout",                  # 认证超时（秒）
                    "banner_timeout",                # Banner 读取超时（秒）
                    "global_delay_factor",           # 全局延迟系数（用于调节网络延迟）
                    "connect_max_retries",           # 最大重连次数
                    "connect_retry_delay_seconds",   # 连接重试间隔（秒）
                    "offline_retry_delay_seconds", # 离线后重试间隔（秒）
                ):
                    # 从 ORM 对象中读取字段值，若值为 None 表示未设置，跳过
                    v = getattr(row, k, None)
                    if v is not None:
                        overrides[k] = v
                # 如果存在任何非 None 的配置项，则调用 apply_config 应用到设备实例
                if overrides:
                    device.apply_config(device.config.with_overrides(**overrides))
        
        # 计算当前内存中已加载的设备 ID 集合
        current_ids = set(self.devices.keys())
        # 取差集：内存中存在但数据库中已不存在的设备，即为“待清理”的设备
        remove_ids = current_ids - db_device_ids
        
        # 遍历所有待清理的设备 ID（已从数据库中删除的设备）
        for did in remove_ids:
            logger.info(f"设备已删除，停止监控任务: Device ID {did}")
            # 若该设备存在对应的监控任务，则取消任务并从 tasks 字典中移除
            if did in self.tasks:
                self.tasks[did].cancel()
                del self.tasks[did]
            
            # 若该设备存在于 devices 缓存中，则先请求优雅关闭，再断开连接，最后从字典中移除
            if did in self.devices:
                try:
                    self.devices[did].request_shutdown()
                except Exception:
                    # 忽略关闭过程中的异常，确保后续清理流程继续
                    pass
                await self.devices[did].disconnect()
                del self.devices[did]
            # 清理该设备对应的 WebSocket 详情订阅队列，避免内存泄漏
            self._ws_detail_subscribers.pop(int(did), None)

    async def refresh_device_config(self, device_id: int) -> None:
        """
        刷新单个设备的配置（从数据库 DeviceConfigEntry 读取并应用覆盖）
        """
        did = int(device_id)
        # 获取内存中的设备实例
        device = self.devices.get(did)
        if not device:
            return
            
        # 从数据库查询配置覆盖项
        row = await DeviceConfigEntry.get_or_none(device_id=did)
        if row:
            overrides: dict[str, Any] = {}
            # 遍历可配置的字段，检查是否有自定义值
            for k in (
                "interval",                    # 数据采集间隔
                "monitor_interval",            # 监控检测间隔
                "offline_fail_threshold",      # 离线判定阈值
                "recovery_success_threshold",  # 恢复判定阈值
                "connect_timeout",             # 连接超时
                "auth_timeout",                # 认证超时
                "banner_timeout",              # Banner读取超时
                "global_delay_factor",         # 延迟系数
                "connect_max_retries",         # 最大重连次数
                "connect_retry_delay_seconds", # 重连等待时间
                "offline_retry_delay_seconds", # 离线重试等待时间
            ):
                v = getattr(row, k, None)
                if v is not None:
                    overrides[k] = v
            
            # 如果存在配置覆盖，应用到设备实例
            if overrides:
                device.apply_config(device.config.with_overrides(**overrides))
        
        # 推送状态更新通知（列表和详情）
        await self._publish_list_update(did)
        await self._publish_detail_update(did)

    def get_device_memory_state(self, device_id: int) -> Dict[str, Any]:
        """
        获取设备的内存运行时状态快照
        """
        return self.get_runtime_snapshot(int(device_id))

    async def sync_device_snapshot(self, device_id: int) -> Dict[str, Any]:
        """
        同步设备快照，并强制推送一次更新通知
        """
        did = int(device_id)
        if did in self.devices:
            await self._publish_list_update(did)
            await self._publish_detail_update(did)
        return await self.get_runtime_snapshot_async(did)

    async def _monitor_device_loop(self, device_id: int, device: BaseDevice):
        """
        设备监控主循环
        """
        # 随机抖动启动时间，避免并发高峰（惊群效应）
        jitter = random.uniform(0, 2)
        await asyncio.sleep(jitter)
        
        logger.info(f"设备 {device_id} ({device.ip}) 开始监控循环 (Jitter: {jitter:.2f}s)")
        # 初始化状态为加载中
        await self._update_state_phase(device_id, "loading", "loop_start")
        await self._update_runtime_status(device_id, "checking", "loop_start")

        async def _connect_progress(phase: str, reason: str) -> None:
            await self._update_state_phase(device_id, phase, reason)
        
        # 1. 尝试建立初始连接
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

        # 2. 生命周期初始化：首次连接成功后，采集设备静态信息（序列号、型号等）
        if device.connected:
             raw_static_info = await device.collect_once()
             
             # 将一次性采集的完整运行时数据（包含版本、OS信息等）立即写入 Redis/内存
             # 确保前端在设备上线后能立即看到版本信息，而无需等待下一次周期采集
             if raw_static_info:
                 # 兼容 raw_static_info 可能是对象的情况
                 data_to_save = raw_static_info.to_dict() if hasattr(raw_static_info, "to_dict") else dict(raw_static_info)
                 await self._save_data_redis(device_id, data_to_save)

             static_info = self._normalize_static_info(raw_static_info)
             if static_info:
                 logger.info(f"设备 {device_id} 静态信息采集成功: {static_info}")
                 await self._update_device_static_info(device_id, static_info)

        next_collection_at = 0.0    #始化下次数据采集的
        offline_retry_at = 0.0
        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

        # 3. 进入主监控循环
        while self.running:
            loop_start_time = time.monotonic()
            
            try:
                # 3.1 检查是否处于离线等待重试状态
                if str(device.fsm_state or "").strip() == "offline":
                    now = time.monotonic()
                    if now < float(offline_retry_at or 0.0):
                        # 未到重试时间，继续等待
                        await asyncio.sleep(max(0.0, float(offline_retry_at) - now))
                        continue

                await self._update_runtime_status(device_id, "checking", "online_check")

                # 3.2 检查设备在线状态
                is_online = await device.check_online(progress_cb=_connect_progress)
                
                if is_online:
                    # 在线状态处理
                    offline_retry_at = 0.0
                    changed = device.record_success()
                    if changed:
                        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                        # 如果状态从未连接/恢复变为在线，更新数据库在线状态
                        if device.fsm_state in {"online", "recovering"}:
                            await self._update_state_phase(device_id, "loading", "fsm_online")
                            await NetworkDevice.filter(id=device_id).update(
                                online_status=True,
                                last_seen=datetime.now(timezone.utc),
                            )

                    await self._update_heartbeat(device_id, fsm_state=device.fsm_state)

                    # 3.3 检查是否到达数据采集时间
                    now = time.monotonic()
                    if device.fsm_state == "online" and now >= float(next_collection_at or 0.0):
                        protocol = "SSH"
                        logger.info(f"开始巡检设备: {device.ip} (协议: {protocol})")
                        await self._update_state_phase(device_id, "collecting", "collect_start")
                        await self._update_runtime_status(device_id, "collecting", "collecting")

                        try:
                            # 执行采集
                            data = await device.collect_status()
                        except Exception as e:
                            # 采集异常处理
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
                            # 采集成功处理
                            if device.connected and data:
                                await self._save_data_redis(device_id, data, fsm_state=device.fsm_state)
                                next_collection_at = time.monotonic() + float(device.interval or 60)
                            elif not device.connected:
                                # 采集中连接断开
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
                                # 采集结果为空
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
                        # 非采集时刻，仅更新心跳
                        if device.fsm_state == "online":
                            await self._update_heartbeat(device_id, fsm_state=device.fsm_state)
                else:
                    # 在线检测失败（Ping/SSH不可达）
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
                # 全局异常捕获
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
            
            # 4. 计算剩余休眠时间，保持固定周期的监控频率
            elapsed = time.monotonic() - loop_start_time
            sleep_time = max(0, device.monitor_interval - elapsed)
            
            await asyncio.sleep(sleep_time)

    async def _update_device_static_info(self, device_id: int, info: dict):
        """
        更新设备的静态信息（厂商、型号、序列号）到数据库
        """
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
        """
        更新FSM状态元数据并推送通知
        """
        await self._publish_list_update(device_id)
        await self._publish_detail_update(device_id)

    async def _update_state_phase(self, device_id: int, state_phase: str, reason: Optional[str] = None):
        """
        更新设备UI展示阶段状态（如 loading, collecting, success, failure 等）
        """
        state = str(state_phase or "").strip() or "unknown"
        if state not in {"init", "loading", "collecting", "success", "failure", "offline", "unknown"}:
            state = "unknown"
        device = self.devices.get(int(device_id))
        if device:
            device.set_state_phase(state, reason)
        await self._publish_list_update(device_id)
        await self._publish_detail_update(device_id)

    async def _update_runtime_status(self, device_id: int, status: str, phase: Optional[str] = None):
        """
        更新设备内部FSM运行时状态
        """
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
        """
        更新设备心跳时间戳
        """
        try:
            device = self.devices.get(int(device_id))
            if device:
                device.last_heartbeat = time.time()
        except Exception as e:
            logger.error(f"更新设备 {device_id} 心跳失败: {e}")
            
    async def _save_data_redis(self, device_id: int, data: dict, fsm_state: Optional[str] = None):
        """
        保存采集到的指标数据到内存对象，并触发 Redis 缓存更新与消息推送
        """
        try:
            # 从内存中获取设备实例
            device = self.devices.get(int(device_id))
            if not device:
                return

            # 定义需要进行数值转换的标准指标字段及其默认值
            # 格式: 字段名 -> (转换函数, 默认值)
            standard_metrics = {
                "cpu_usage": (float, 0.0),
                "memory_usage": (float, 0.0),
                "disk_usage": (float, 0.0),
            }

            # 1. 批量处理标准指标（带类型转换与异常保护）
            for key, (converter, default) in standard_metrics.items():
                try:
                    raw_val = data.get(key)
                    # 如果 raw_val 是 None 或空字符串，使用 default
                    # 否则尝试转换
                    val = converter(raw_val) if raw_val is not None and raw_val != "" else default
                    device.last_metrics[key] = val
                except Exception:
                    device.last_metrics[key] = default

            # 2. 处理特殊字段 uptime
            if data.get("uptime"):
                device.last_metrics["uptime"] = str(data.get("uptime") or "")

            # 3. 动态合并其他所有采集到的数据（如 version, os_version, serial_number 等）
            # 排除已处理的标准字段，避免重复处理
            exclude_keys = set(standard_metrics.keys()) | {"uptime"}
            for k, v in data.items():
                if k not in exclude_keys and v is not None:
                    device.last_metrics[k] = v

            # 更新时间戳与状态
            device.last_metrics_updated = time.time()
            device.set_state_phase("success", "")
            
            # 3.1 检查告警规则
            # 构造完整的检查数据，包括在线状态
            check_data = device.last_metrics.copy()
            check_data["online_status"] = 1.0
            await self.alert_handler.check_alert_rules(device_id, check_data)
            
            # 4. 触发 Redis 更新和 WebSocket 广播
            await self._publish_list_update(device_id)
            await self._publish_detail_update(device_id)

        except Exception as e:
            logger.error(f"保存设备 {device_id} 数据失败: {e}")

    async def _set_device_offline(self, device_id: int, reason: Optional[str] = None):
        """
        将设备标记为离线状态，更新数据库并发送通知
        """
        try:
            device = self.devices.get(int(device_id))
            if device:
                device.set_state_phase("offline", reason)
            await NetworkDevice.filter(id=device_id).update(online_status=False)
            
            # 检查告警 (Offline)
            await self.alert_handler.check_alert_rules(device_id, {"online_status": 0.0})
            
            await self._publish_list_update(device_id)
            await self._publish_detail_update(device_id)
            await NotificationService.notify_device_offline(device_id, reason)
        except Exception as e:
            logger.error(f"更新设备 {device_id} 离线状态失败: {e}")

    async def _clear_redis_status(self, device_id: int):
        """
        清理指定设备在 Redis 中的运行时状态快照
        """
        try:
            redis_client = redis_manager.get_client()
            key = f"{self._REDIS_SNAPSHOT_KEY_PREFIX}{int(device_id)}"
            await redis_client.delete(key)
        except Exception as e:
            logger.error(f"清理设备 {device_id} Redis状态失败: {e}")

    async def clear_all_redis_statuses(self):
        """
        清理所有已加载设备在 Redis 中的运行时状态快照
        通常在服务关闭时调用
        """
        logger.info("正在清理所有设备的 Redis 状态缓存...")
        for device_id in list(self.devices.keys()):
            await self._clear_redis_status(device_id)

    async def _seed_device_statuses(self, device_ids: list[int]):
        """初始化设备状态（预留）"""
        return

    async def _prime_startup_statuses(self):
        """启动时预热状态（预留）"""
        return

    async def refresh_alert_rules(self, device_id: int):
        """刷新单个设备的告警规则（代理到 AlertHandler）"""
        await self.alert_handler.refresh_alert_rules(device_id)

