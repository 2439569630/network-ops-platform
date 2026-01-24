
import asyncio
import heapq
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Set, Optional, Any
from app.drivers.factory import create_device
from app.drivers.base import BaseDevice
from app.drivers.ssh_retry import classify_ssh_failure
from app.core.config import settings
from app.core.redis import redis_manager
from app.services.notification_service import NotificationService
from app.services.device_event_service import DEVICE_UPDATE_CHANNEL
from app.models.orm.device import NetworkDevice
from app.models.orm.device import DeviceConfigEntry
from app.workers.monitor.alert_handler import AlertHandler
from app.services.alert_service import ALERT_RULES_UPDATE_CHANNEL
from app.utils.device_status import status_fields_from_snapshot
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
    _LEADER_LOCK_KEY = "monitor:leader_lock"
    _LEADER_LOCK_TTL_SECONDS = 90
    
    def __new__(cls):
        """
        单例模式实现
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
            cls._instance._last_loaded_device_ids: Optional[Set[int]] = None
            # WebSocket 广播订阅队列集合：设备列表频道
            cls._instance._ws_list_subscribers: Set[asyncio.Queue] = set()
            # WebSocket 广播订阅队列映射：设备详情频道，device_id -> Set[asyncio.Queue]
            cls._instance._ws_detail_subscribers: Dict[int, Set[asyncio.Queue]] = defaultdict(set)
            cls._instance._inspect_seq: Dict[int, int] = defaultdict(int)
            
            # 告警处理器
            cls._instance.alert_handler = AlertHandler()
            # 告警规则订阅任务
            cls._instance.alert_sub_task: Optional[asyncio.Task] = None
            cls._instance.device_sub_task: Optional[asyncio.Task] = None
            cls._instance.device_event_consumer_task: Optional[asyncio.Task] = None
            cls._instance._leader_lock_token: Optional[str] = None
            cls._instance._leader_lock_task: Optional[asyncio.Task] = None
            cls._instance._device_event_signal: asyncio.Event = asyncio.Event()
            cls._instance._device_event_lock: asyncio.Lock = asyncio.Lock()
            cls._instance._device_event_latest: Dict[int, dict] = {}
            cls._instance._monitor_log_detail: str = str(os.getenv("MONITOR_LOG_DETAIL", "summary") or "summary").strip().lower()
        return cls._instance

    def _is_full_monitor_log(self) -> bool:
        v = str(getattr(self, "_monitor_log_detail", "") or "").strip().lower()
        return v in {"1", "true", "yes", "y", "full", "verbose", "debug"}

    @staticmethod
    def _format_log_value(value: Any, max_len: int = 120) -> str:
        try:
            s = "" if value is None else str(value)
        except Exception:
            s = ""
        s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        if max_len > 0 and len(s) > max_len:
            return s[: max(1, max_len - 1)] + "…"
        return s

    def _format_metrics_extras(self, data: dict) -> str:
        if not isinstance(data, dict) or not data:
            return ""
        cpu = data.get("cpu_usage")
        mem = data.get("memory_usage")
        disk = data.get("disk_usage")
        uptime = data.get("uptime")
        temp = data.get("temperature")
        extras = []
        if cpu is not None:
            extras.append(f"cpu={self._format_log_value(cpu)}")
        if mem is not None:
            extras.append(f"mem={self._format_log_value(mem)}")
        if disk is not None:
            extras.append(f"disk={self._format_log_value(disk)}")
        if uptime:
            extras.append(f"uptime={self._format_log_value(uptime)}")
        if temp is not None:
            try:
                if float(temp or 0.0) != 0.0:
                    extras.append(f"temp={self._format_log_value(temp)}")
            except Exception:
                extras.append(f"temp={self._format_log_value(temp)}")
        return (" " + " ".join(extras)) if extras else ""

    @staticmethod
    def _job_what(job_name: str) -> str:
        n = str(job_name or "").strip()
        mapping = {
            "metrics": "指标巡检",
            "interfaces": "接口巡检",
            "routes": "路由巡检",
            "vlans": "VLAN巡检",
            "interfaces_slot0_detailed": "接口详情巡检(slot0)",
        }
        return mapping.get(n, n or "巡检")

    def _format_cmds(self, commands: Any) -> str:
        if not commands:
            return ""
        if not isinstance(commands, (list, tuple)):
            return ""
        parts = []
        for c in commands:
            s = self._format_log_value(c, max_len=120)
            if s:
                parts.append(s)
        if not parts:
            return ""
        return " cmds=[" + "; ".join(parts) + "]"

    @staticmethod
    def _safe_len(value: Any) -> Optional[int]:
        try:
            return len(value)  # type: ignore[arg-type]
        except Exception:
            return None

    def _next_inspect_id(self, device_id: int, job_name: str) -> str:
        did = int(device_id)
        self._inspect_seq[did] = int(self._inspect_seq.get(did, 0)) + 1
        seq = int(self._inspect_seq[did])
        short = uuid.uuid4().hex[:8]
        return f"{did}-{job_name}-{seq}-{short}"

    @staticmethod
    def _device_event_action_rank(action: str) -> int:
        a = str(action or "").strip().lower()
        if a == "delete":
            return 4
        if a == "update":
            return 3
        if a in {"add", "restore"}:
            return 2
        if a == "config_update":
            return 1
        return 0

    @classmethod
    def _merge_device_event_payload(cls, existing: Optional[dict], incoming: dict) -> dict:
        if not isinstance(existing, dict):
            return dict(incoming)
        a1 = str(existing.get("action") or "").strip().lower()
        a2 = str(incoming.get("action") or "").strip().lower()
        if cls._device_event_action_rank(a2) >= cls._device_event_action_rank(a1):
            merged = dict(existing)
            merged.update(incoming)
            merged["action"] = a2
            return merged
        merged = dict(existing)
        merged.update({k: v for k, v in incoming.items() if k != "action"})
        merged["action"] = a1
        return merged

    async def _enqueue_device_event(self, payload: dict) -> None:
        action = str(payload.get("action") or "").strip().lower()
        try:
            did = int(payload.get("device_id"))
        except Exception:
            return
        if not action or did <= 0:
            return
        async with self._device_event_lock:
            existing = self._device_event_latest.get(did)
            self._device_event_latest[did] = self._merge_device_event_payload(existing, {"action": action, "device_id": did, **payload})
        self._device_event_signal.set()

    async def _device_event_consumer_loop(self) -> None:
        while self.running:
            try:
                await self._device_event_signal.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.1)
                continue

            self._device_event_signal.clear()
            async with self._device_event_lock:
                batch = self._device_event_latest
                self._device_event_latest = {}

            if not batch:
                continue

            for did, payload in list(batch.items()):
                if not self.running:
                    break
                started = time.monotonic()
                try:
                    logger.info(f"收到设备事件: action={payload.get('action')} device_id={did}")
                    await self._handle_device_event(payload)
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    logger.info(f"设备事件处理完成: device_id={did} action={payload.get('action')} cost_ms={elapsed_ms}")
                except (asyncio.TimeoutError, TimeoutError) as e:
                    logger.error(f"处理设备变更事件失败(数据库连接超时): device_id={did} action={payload.get('action')} err={e}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"处理设备变更事件失败: device_id={did} action={payload.get('action')} err={e}")

    async def _acquire_leader_lock(self) -> bool:
        token = f"{os.getpid()}:{uuid.uuid4()}"
        redis_client = redis_manager.get_client()
        ok = await redis_client.set(
            self._LEADER_LOCK_KEY,
            token,
            nx=True,
            ex=int(self._LEADER_LOCK_TTL_SECONDS),
        )
        if ok:
            self._leader_lock_token = token
            return True
        return False

    async def _renew_leader_lock_loop(self) -> None:
        redis_client = redis_manager.get_client()
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('expire', KEYS[1], tonumber(ARGV[2])) "
            "else return 0 end"
        )
        while self.running and self._leader_lock_token:
            await asyncio.sleep(max(1.0, float(self._LEADER_LOCK_TTL_SECONDS) / 3.0))
            try:
                await redis_client.eval(
                    script,
                    1,
                    self._LEADER_LOCK_KEY,
                    self._leader_lock_token,
                    int(self._LEADER_LOCK_TTL_SECONDS),
                )
            except Exception as e:
                logger.warning(f"监控主实例锁续租失败: {e}")

    async def _release_leader_lock(self) -> None:
        token = self._leader_lock_token
        self._leader_lock_token = None
        if not token:
            return
        redis_client = redis_manager.get_client()
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) "
            "else return 0 end"
        )
        try:
            await redis_client.eval(script, 1, self._LEADER_LOCK_KEY, token)
        except Exception:
            return

    async def _subscribe_alert_updates(self):
        """订阅 Redis 告警规则更新频道"""
        try:
            redis_client = redis_manager.get_client()
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(ALERT_RULES_UPDATE_CHANNEL)
            logger.info(f"已订阅告警规则更新频道: {ALERT_RULES_UPDATE_CHANNEL}")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        device_id = int(message["data"])
                        logger.info(f"收到规则更新通知，刷新设备 {device_id}")
                        await self.alert_handler.refresh_alert_rules(device_id)
                    except ValueError:
                        logger.warning(f"收到无效的规则更新消息: {message['data']}")
                    except Exception as e:
                        logger.error(f"处理规则更新消息失败: {e}")
        except asyncio.CancelledError:
            logger.info("告警规则订阅任务被取消")
            if 'pubsub' in locals():
                await pubsub.unsubscribe(ALERT_RULES_UPDATE_CHANNEL)
        except Exception as e:
            logger.error(f"订阅告警规则频道失败: {e}")

    async def _subscribe_device_updates(self) -> None:
        delay = 1.0
        while self.running:
            pubsub = None
            try:
                redis_client = redis_manager.get_client()
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(DEVICE_UPDATE_CHANNEL)
                logger.info(f"已订阅设备变更频道: {DEVICE_UPDATE_CHANNEL}")
                delay = 1.0

                try:
                    await self.load_devices()
                except Exception as e:
                    logger.warning(f"设备变更订阅重连后校准失败: {e}")

                async for message in pubsub.listen():
                    if not self.running:
                        break
                    if message.get("type") != "message":
                        continue
                    payload = None
                    try:
                        raw = message.get("data")
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode("utf-8", errors="ignore")
                        if isinstance(raw, str):
                            payload = json.loads(raw) if raw else None
                        elif isinstance(raw, dict):
                            payload = raw
                    except Exception as e:
                        logger.warning(f"设备变更事件解析失败: {e}")
                        payload = None

                    if not isinstance(payload, dict):
                        continue
                    await self._enqueue_device_event(payload)
            except asyncio.CancelledError:
                logger.info("设备变更订阅任务被取消")
                raise
            except Exception as e:
                logger.error(f"订阅设备变更频道失败: {e}")
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.unsubscribe(DEVICE_UPDATE_CHANNEL)
                    except Exception:
                        pass
                    try:
                        await pubsub.close()
                    except Exception:
                        pass

            if not self.running:
                break
            await asyncio.sleep(delay + random.uniform(0.0, 0.5))
            delay = min(30.0, delay * 2.0)

    async def _handle_device_event(self, payload: dict) -> None:
        action = str(payload.get("action") or "").strip().lower()
        try:
            device_id = int(payload.get("device_id"))
        except Exception:
            return

        if action in {"add", "restore"}:
            await self._ensure_device_running(device_id, recreate=False)
            return
        if action == "update":
            await self._ensure_device_running(device_id, recreate=True)
            return
        if action == "delete":
            await self._remove_device(device_id, reason="device_deleted")
            return
        if action == "config_update":
            await self._ensure_device_running(device_id, recreate=False)
            return

    async def _ensure_device_running(self, device_id: int, recreate: bool = False) -> None:
        did = int(device_id)
        if recreate:
            logger.info(f"设备 {did} 开始重载(recreate=True)")
        try:
            row = await NetworkDevice.get_or_none(id=did)
        except (asyncio.TimeoutError, TimeoutError) as e:
            logger.error(f"设备 {did} 加载失败(数据库连接超时): {e}")
            return
        if not row or row.deleted_at is not None or (row.is_active is False):
            await self._remove_device(did, reason="device_missing_or_inactive")
            return

        if recreate and did in self.devices:
            await self._remove_device(did, reason="device_recreate")

        if did not in self.devices:
            d = dict(row)
            d["created_by_name"] = ""
            device = create_device(d)
            try:
                monitor_interval = settings.MONITOR_INTERVAL
                online_check_interval = settings.ONLINE_CHECK_INTERVAL
                device.apply_config(
                    device.config.with_overrides(
                        interval=float(monitor_interval or getattr(device, "interval", 60) or 60),
                        monitor_interval=float(online_check_interval or getattr(device, "monitor_interval", 10) or 10),
                    )
                )
            except Exception:
                pass

            self.devices[did] = device
            self.tasks[did] = asyncio.create_task(self._monitor_device_loop(did, device))
            await self._update_runtime_status(did, "checking", "event_add")

        await self._apply_device_config_update(did)
        await self._publish_list_update(did)
        await self._publish_detail_update(did)
        if recreate:
            logger.info(f"设备 {did} 重载完成")

    async def _apply_device_config_update(self, device_id: int) -> None:
        did = int(device_id)
        device = self.devices.get(did)
        if not device:
            return

        try:
            row = await DeviceConfigEntry.get_or_none(device_id=did)
        except (asyncio.TimeoutError, TimeoutError) as e:
            logger.error(f"设备 {did} 配置加载失败(数据库连接超时): {e}")
            return
        if not row:
            return

        overrides: dict[str, Any] = {}
        interval_val = getattr(row, "interval", None)
        if interval_val is not None:
            try:
                overrides["interval"] = float(interval_val)
            except Exception:
                pass

        monitor_val = getattr(row, "monitor_interval", None)
        if monitor_val is not None:
            try:
                overrides["monitor_interval"] = float(monitor_val)
            except Exception:
                pass

        for k in (
            "offline_fail_threshold",
            "recovery_success_threshold",
            "connect_timeout",
            "auth_timeout",
            "banner_timeout",
            "global_delay_factor",
            "connect_max_retries",
            "connect_retry_delay_seconds",
            "offline_retry_delay_seconds",
            "resource_sync_interval",
            "interfaces_sync_interval",
            "interfaces_slot0_sync_interval",
            "routes_sync_interval",
            "vlans_sync_interval",
        ):
            v = getattr(row, k, None)
            if v is not None:
                overrides[k] = v
        if overrides:
            try:
                device.apply_config(device.config.with_overrides(**overrides))
            except Exception:
                return
            if any(
                k in overrides
                for k in (
                    "resource_sync_interval",
                    "interfaces_sync_interval",
                    "interfaces_slot0_sync_interval",
                    "routes_sync_interval",
                    "vlans_sync_interval",
                )
            ):
                if hasattr(device, "next_interfaces_sync_at"):
                    device.next_interfaces_sync_at = 0.0
                if hasattr(device, "next_routes_sync_at"):
                    device.next_routes_sync_at = 0.0
                if hasattr(device, "next_vlans_sync_at"):
                    device.next_vlans_sync_at = 0.0
                if hasattr(device, "next_interfaces_slot0_sync_at"):
                    device.next_interfaces_slot0_sync_at = 0.0

    async def _remove_device(self, device_id: int, reason: str = "") -> None:
        did = int(device_id)
        task = self.tasks.pop(did, None)
        if task:
            try:
                task.cancel()
            except Exception:
                pass
            logger.info(f"设备 {did} 取消监控任务: reason={reason or ''}")

        device = self.devices.get(did)
        if device:
            try:
                device.status.set_fsm("offline", str(reason or "removed"))
            except Exception:
                pass
            await self._publish_list_update(did)
            await self._publish_detail_update(did)
            try:
                device.request_shutdown()
            except Exception:
                pass
            try:
                logger.info(f"设备 {did} 开始断开连接: reason={reason or ''}")
                await asyncio.wait_for(device.disconnect(), timeout=5.0)
                logger.info(f"设备 {did} 断开连接完成")
            except asyncio.TimeoutError:
                logger.warning(f"设备 {did} 断开连接超时(5s)，继续重载/清理")
            except Exception:
                pass
            self.devices.pop(did, None)

        self._ws_detail_subscribers.pop(did, None)
        return

    async def start(self):
        """启动监控服务"""
        if self.running:
            logger.warning("监控服务已在运行中，重复调用 start() 无效果")
            return

        try:
            leader_ok = await self._acquire_leader_lock()
        except Exception as e:
            logger.error(f"获取监控主实例锁失败: {e}")
            return
        if not leader_ok:
            logger.warning("当前实例未获得监控主实例锁，跳过监控启动")
            return

        self.running = True
        logger.info("正在启动监控服务...")
        self._leader_lock_task = asyncio.create_task(self._renew_leader_lock_loop())

        try:
            # 启动时立即加载一次数据库中的设备，初始化 devices 与 tasks 映射
            await self.load_devices()
            # 加载告警规则
            await self.alert_handler.load_alert_rules()
        except (asyncio.TimeoutError, TimeoutError) as e:
            logger.error(f"启动时同步设备列表失败(数据库连接超时): {e}")
        except Exception as e:
            logger.error(f"启动时同步设备列表失败: {e}", exc_info=True)

        try:
            if self.device_event_consumer_task:
                self.device_event_consumer_task.cancel()
            self.device_event_consumer_task = asyncio.create_task(self._device_event_consumer_loop())
        except Exception as e:
            logger.error(f"启动设备事件处理守护任务失败: {e}", exc_info=True)
        self.alert_sub_task = asyncio.create_task(self._subscribe_alert_updates())
        self.device_sub_task = asyncio.create_task(self._subscribe_device_updates())
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

        if self.alert_sub_task:
            self.alert_sub_task.cancel()
            try:
                await self.alert_sub_task
            except asyncio.CancelledError:
                pass
            self.alert_sub_task = None

        if self.device_sub_task:
            self.device_sub_task.cancel()
            try:
                await self.device_sub_task
            except asyncio.CancelledError:
                pass
            self.device_sub_task = None

        if self.device_event_consumer_task:
            self.device_event_consumer_task.cancel()
            try:
                await self.device_event_consumer_task
            except asyncio.CancelledError:
                pass
            self.device_event_consumer_task = None

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

        if self._leader_lock_task:
            self._leader_lock_task.cancel()
            try:
                await self._leader_lock_task
            except asyncio.CancelledError:
                pass
            self._leader_lock_task = None
        await self._release_leader_lock()

        for device in self.devices.values():
            try:
                device.request_shutdown()
            except Exception:
                pass
        
        for task in self.tasks.values():
            task.cancel()
        
        if self.tasks:
            # 等待所有任务结束
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

        # 任务已停止，现在清理 Redis 状态，避免残留
        await self.clear_all_redis_statuses()

        # 并发断开所有设备连接，并设置超时防止卡死
        disconnect_tasks = []
        for device in self.devices.values():
            disconnect_tasks.append(device.disconnect())
        
        if disconnect_tasks:
            try:
                # 设置 5 秒超时，防止个别设备断开连接卡死
                await asyncio.wait_for(asyncio.gather(*disconnect_tasks, return_exceptions=True), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("部分设备断开连接超时，强制退出")
            except Exception as e:
                logger.error(f"断开设备连接时发生错误: {e}")

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
        base = status_fields_from_snapshot(snap)
        payload = {
            "id": int(device_id),
            "status": snap["status"],
            "display_status": str(base.get("display_status") or snap.get("status") or ""),
            "connectivity": str(base.get("connectivity") or "offline"),
            "online_status": bool(base.get("online_status")),
            "cpu_usage": snap["cpu_usage"],
            "memory_usage": snap["memory_usage"],
            "disk_usage": snap["disk_usage"],
            "fsm_state": str(base.get("fsm_state") or snap.get("fsm_state") or ""),
            "fsm_reason": str(base.get("fsm_reason") or snap.get("fsm_reason") or ""),
            "fsm_updated": str(base.get("fsm_updated") or snap.get("fsm_updated") or ""),
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
        interval = float(getattr(settings, "DEVICE_LOADER_INTERVAL", 300) or 300)
        if interval < 10:
            interval = 10
        logger.info(f"启动设备列表热更新守护任务，间隔 {int(interval)} 秒")
        while self.running:
            try:
                await self.load_devices()
            except Exception as e:
                logger.error(f"热更新设备列表失败: {e}")
            
            await asyncio.sleep(interval)

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
        # 查询所有未被逻辑删除且处于激活状态（或激活字段为空）的设备记录
        # Q 对象用于组合查询条件：is_active=True 或 is_active 为空，同时 deleted_at 为空表示未删除
        # 将数据库的数据写入数据模型
        try:
            devices = await NetworkDevice.filter(
                Q(is_active=True) | Q(is_active__isnull=True),
                deleted_at__isnull=True
            ).all()
        except (asyncio.TimeoutError, TimeoutError) as e:
            logger.error(f"数据库连接超时，跳过本轮设备加载: {e}")
            return
        
        db_ids_now: Set[int] = {int(d.id) for d in devices}
        last_ids = self._last_loaded_device_ids
        if last_ids is None or db_ids_now != last_ids:
            device_infos = [f"{d.device_name}({d.ipv4})" for d in devices]
            logger.info(f"正在从数据库加载 {len(devices)} 台设备: {', '.join(device_infos)}")
        self._last_loaded_device_ids = db_ids_now
        
        # 收集所有设备记录中 created_by 字段为合法数字的用户 ID
        user_ids = {int(d.created_by) for d in devices if d.created_by and d.created_by.isdigit()}
        # 按需导入 User 模型
        from app.models.orm.user import User
        # 批量查询这些用户，获取其 username
        try:
            users = await User.filter(id__in=list(user_ids)).all()
        except (asyncio.TimeoutError, TimeoutError) as e:
            logger.error(f"数据库连接超时，跳过本轮用户映射加载: {e}")
            return
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
                    await self._update_runtime_status(device_id, "checking", "task_created")
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
                    "resource_sync_interval",      # 深度巡检/资源同步间隔（秒）
                    "interfaces_sync_interval",
                    "interfaces_slot0_sync_interval",
                    "routes_sync_interval",
                    "vlans_sync_interval",
                ):
                    # 从 ORM 对象中读取字段值，若值为 None 表示未设置，跳过
                    v = getattr(row, k, None)
                    if v is not None:
                        overrides[k] = v
                # 如果存在任何非 None 的配置项，则调用 apply_config 应用到设备实例
                if overrides:
                    device.apply_config(device.config.with_overrides(**overrides))
                    if any(
                        k in overrides
                        for k in (
                            "resource_sync_interval",
                            "interfaces_sync_interval",
                            "routes_sync_interval",
                            "vlans_sync_interval",
                        )
                    ):
                        if hasattr(device, "next_interfaces_sync_at"):
                            device.next_interfaces_sync_at = 0.0
                        if hasattr(device, "next_routes_sync_at"):
                            device.next_routes_sync_at = 0.0
                        if hasattr(device, "next_vlans_sync_at"):
                            device.next_vlans_sync_at = 0.0
                        if hasattr(device, "next_interfaces_slot0_sync_at"):
                            device.next_interfaces_slot0_sync_at = 0.0
        
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
                "resource_sync_interval",      # 深度巡检/资源同步间隔
                "interfaces_sync_interval",
                "interfaces_slot0_sync_interval",
                "routes_sync_interval",
                "vlans_sync_interval",
            ):
                v = getattr(row, k, None)
                if v is not None:
                    overrides[k] = v
            
            # 如果存在配置覆盖，应用到设备实例
            if overrides:
                device.apply_config(device.config.with_overrides(**overrides))
                if any(
                    k in overrides
                    for k in (
                        "resource_sync_interval",
                        "interfaces_sync_interval",
                        "interfaces_slot0_sync_interval",
                        "routes_sync_interval",
                        "vlans_sync_interval",
                    )
                ):
                    if hasattr(device, "next_interfaces_sync_at"):
                        device.next_interfaces_sync_at = 0.0
                    if hasattr(device, "next_routes_sync_at"):
                        device.next_routes_sync_at = 0.0
                    if hasattr(device, "next_vlans_sync_at"):
                        device.next_vlans_sync_at = 0.0
                    if hasattr(device, "next_interfaces_slot0_sync_at"):
                        device.next_interfaces_slot0_sync_at = 0.0
        
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
        await self._update_runtime_status(device_id, "checking", "loop_start")

        async def _connect_progress(phase: str, reason: str) -> None:
            p = str(phase or "").strip().lower()
            if p in {"loading", "checking"}:
                await self._update_runtime_status(device_id, "checking", reason)
            elif p in {"failure", "failed"}:
                await self._update_runtime_status(device_id, "degraded", reason)

        offline_retry_at = 0.0
        job_seq = 0
        jobs: list[tuple[float, int, str, float]] = []

        def _push_job(name: str, period: float, start_at: float = 0.0) -> None:
            nonlocal job_seq
            try:
                p = float(period or 0.0)
            except Exception:
                p = 0.0
            if p < 0:
                return
            job_seq += 1
            heapq.heappush(jobs, (time.monotonic() + float(start_at or 0.0), job_seq, str(name), p))

        async def _publish_resources(did: int, data: dict[str, Any]) -> None:
            if not data:
                return
            try:
                redis = redis_manager.get_client()
            except Exception:
                return
            ttl = 3600
            updated_names = []
            pipe = redis.pipeline()
            for name, items in data.items():
                if items is None:
                    continue
                n = str(name).strip()
                if not n:
                    continue
                updated_names.append(n)
                key = f"device:{int(did)}:{n}"
                payload = json.dumps(items, ensure_ascii=False)
                pipe.set(key, payload, ex=ttl)
                pipe.set(f"{key}:last", payload)
            if not updated_names:
                return
            await pipe.execute()
            await redis.publish(
                "device:resource:update",
                json.dumps({"device_id": int(did), "resources": sorted(updated_names)}, ensure_ascii=False),
            )
            await redis.publish(
                f"ws:devices:resources:{int(did)}",
                json.dumps(
                    {
                        "type": "resources_updated",
                        "device_id": int(did),
                        "resources": sorted(updated_names),
                        "data": {k: v for k, v in data.items() if v is not None},
                    },
                    ensure_ascii=False,
                ),
            )

        async def _run_metrics_job() -> None:
            nonlocal offline_retry_at
            inspect_id = self._next_inspect_id(device_id, "metrics")
            start_at = time.monotonic()
            what = self._job_what("metrics")
            logger.info(
                f"巡检开始 inspect_id={inspect_id} device={int(device_id)} {device.ip}:{getattr(device, 'port', '')} "
                f"job=metrics what={what} fsm={str(device.fsm_state or '').strip() or 'unknown'}"
            )
            await self._update_runtime_status(device_id, "collecting", "collecting")

            if hasattr(device, "begin_inspection"):
                try:
                    device.begin_inspection(inspect_id)
                except Exception:
                    pass

            try:
                data = await device.collect_status()
            except Exception as e:
                reason = str(e).splitlines()[0] if str(e) else "采集异常"
                cost_ms = int((time.monotonic() - start_at) * 1000)
                cmds = []
                if hasattr(device, "end_inspection"):
                    try:
                        cmds = device.end_inspection()
                    except Exception:
                        cmds = []
                cmds_text = self._format_cmds(cmds)
                changed, should_offline = device.record_failure(reason)
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                await self._update_runtime_status(device_id, device.fsm_state, "collect_exception")
                if should_offline:
                    await self._set_device_offline(device_id, device.fsm_reason)
                    offline_retry_at = time.monotonic() + _next_offline_delay_seconds(e)
                if self._is_full_monitor_log() and should_offline:
                    retry_in_s = max(0, int(float(offline_retry_at or 0.0) - time.monotonic()))
                    logger.warning(
                        f"巡检失败 inspect_id={inspect_id} job=metrics cost_ms={cost_ms} "
                        f"reason={device.fsm_reason or reason} next_retry_in_s={retry_in_s}{cmds_text}"
                    )
                else:
                    logger.warning(
                        f"巡检失败 inspect_id={inspect_id} job=metrics cost_ms={cost_ms} "
                        f"reason={device.fsm_reason or reason}{cmds_text}"
                    )
                return

            if device.connected and data:
                changed = device.record_success()
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                await self._save_data_redis(device_id, data, fsm_state=device.fsm_state)
                await self._update_heartbeat(device_id, fsm_state=device.fsm_state)
                cost_ms = int((time.monotonic() - start_at) * 1000)
                extras_text = self._format_metrics_extras(data)
                cmds = []
                if hasattr(device, "end_inspection"):
                    try:
                        cmds = device.end_inspection()
                    except Exception:
                        cmds = []
                cmds_text = self._format_cmds(cmds)
                if self._is_full_monitor_log():
                    fields = ",".join(sorted([str(k) for k in data.keys()]))
                    logger.info(
                        f"巡检完成 inspect_id={inspect_id} job=metrics what={what} cost_ms={cost_ms} ok=1 "
                        f"fields={fields}{extras_text}{cmds_text}"
                    )
                else:
                    logger.info(
                        f"巡检完成 inspect_id={inspect_id} job=metrics what={what} cost_ms={cost_ms} ok=1{extras_text}{cmds_text}"
                    )
                return

            if not device.connected:
                cost_ms = int((time.monotonic() - start_at) * 1000)
                cmds = []
                if hasattr(device, "end_inspection"):
                    try:
                        cmds = device.end_inspection()
                    except Exception:
                        cmds = []
                cmds_text = self._format_cmds(cmds)
                logger.warning(
                    f"巡检中断 inspect_id={inspect_id} job=metrics what={what} cost_ms={cost_ms} reason=采集过程中断开{cmds_text}"
                )
                changed, should_offline = device.record_failure("采集过程中断开")
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                await self._update_runtime_status(device_id, device.fsm_state, "collect_failed")
                if should_offline:
                    await self._set_device_offline(device_id, device.fsm_reason)
                    offline_retry_at = time.monotonic() + _next_offline_delay_seconds(getattr(device, "last_connect_error", None))
                return

            changed, should_offline = device.record_failure("采集无数据")
            cost_ms = int((time.monotonic() - start_at) * 1000)
            cmds = []
            if hasattr(device, "end_inspection"):
                try:
                    cmds = device.end_inspection()
                except Exception:
                    cmds = []
            cmds_text = self._format_cmds(cmds)
            if changed:
                await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
            await self._update_runtime_status(device_id, device.fsm_state, "collect_empty")
            if should_offline:
                await self._set_device_offline(device_id, device.fsm_reason)
                offline_retry_at = time.monotonic() + _next_offline_delay_seconds(getattr(device, "last_connect_error", None))
            await self._update_heartbeat(device_id, fsm_state=device.fsm_state)
            logger.warning(f"巡检无数据 inspect_id={inspect_id} job=metrics what={what} cost_ms={cost_ms} ok=0{cmds_text}")

        async def _run_resource_job(name: str) -> None:
            nonlocal offline_retry_at
            n = str(name or "").strip()
            if not n:
                return
            if str(device.fsm_state or "").strip() == "offline":
                return
            inspect_id = self._next_inspect_id(device_id, n)
            start_at = time.monotonic()
            what = self._job_what(n)
            logger.info(
                f"资源同步开始 inspect_id={inspect_id} device={int(device_id)} {device.ip}:{getattr(device, 'port', '')} "
                f"job={n} what={what} fsm={str(device.fsm_state or '').strip() or 'unknown'}"
            )
            if hasattr(device, "begin_inspection"):
                try:
                    device.begin_inspection(inspect_id)
                except Exception:
                    pass
            try:
                if n == "interfaces" and hasattr(device, "collect_interfaces"):
                    items = await device.collect_interfaces()
                    if items is not None:
                        await _publish_resources(int(device_id), {"interfaces": items})
                        cost_ms = int((time.monotonic() - start_at) * 1000)
                        count = self._safe_len(items)
                        items_text = f" items={count}" if count is not None else ""
                        cmds = []
                        if hasattr(device, "end_inspection"):
                            try:
                                cmds = device.end_inspection()
                            except Exception:
                                cmds = []
                        cmds_text = self._format_cmds(cmds)
                        logger.info(
                            f"资源同步完成 inspect_id={inspect_id} job=interfaces what={what} cost_ms={cost_ms} ok=1{items_text}{cmds_text}"
                        )
                elif n == "routes" and hasattr(device, "collect_routes"):
                    items = await device.collect_routes()
                    if items is not None:
                        await _publish_resources(int(device_id), {"routes": items})
                        cost_ms = int((time.monotonic() - start_at) * 1000)
                        count = self._safe_len(items)
                        items_text = f" items={count}" if count is not None else ""
                        cmds = []
                        if hasattr(device, "end_inspection"):
                            try:
                                cmds = device.end_inspection()
                            except Exception:
                                cmds = []
                        cmds_text = self._format_cmds(cmds)
                        logger.info(
                            f"资源同步完成 inspect_id={inspect_id} job=routes what={what} cost_ms={cost_ms} ok=1{items_text}{cmds_text}"
                        )
                elif n == "vlans" and hasattr(device, "collect_vlans"):
                    items = await device.collect_vlans()
                    if items is not None:
                        await _publish_resources(int(device_id), {"vlans": items})
                        cost_ms = int((time.monotonic() - start_at) * 1000)
                        count = self._safe_len(items)
                        items_text = f" items={count}" if count is not None else ""
                        cmds = []
                        if hasattr(device, "end_inspection"):
                            try:
                                cmds = device.end_inspection()
                            except Exception:
                                cmds = []
                        cmds_text = self._format_cmds(cmds)
                        logger.info(
                            f"资源同步完成 inspect_id={inspect_id} job=vlans what={what} cost_ms={cost_ms} ok=1{items_text}{cmds_text}"
                        )
                elif n == "interfaces_slot0_detailed" and hasattr(device, "collect_interfaces_detailed"):
                    items = await device.collect_interfaces_detailed(slot_id=0)
                    if items is not None:
                        await _publish_resources(int(device_id), {"interfaces_slot0_detailed": items})
                        cost_ms = int((time.monotonic() - start_at) * 1000)
                        count = self._safe_len(items)
                        items_text = f" items={count}" if count is not None else ""
                        cmds = []
                        if hasattr(device, "end_inspection"):
                            try:
                                cmds = device.end_inspection()
                            except Exception:
                                cmds = []
                        cmds_text = self._format_cmds(cmds)
                        logger.info(
                            f"资源同步完成 inspect_id={inspect_id} job=interfaces_slot0_detailed what={what} "
                            f"cost_ms={cost_ms} ok=1{items_text}{cmds_text}"
                        )
            except Exception as e:
                reason = str(e).splitlines()[0] if str(e) else "资源同步异常"
                cost_ms = int((time.monotonic() - start_at) * 1000)
                cmds = []
                if hasattr(device, "end_inspection"):
                    try:
                        cmds = device.end_inspection()
                    except Exception:
                        cmds = []
                cmds_text = self._format_cmds(cmds)
                changed, should_offline = device.record_failure(reason)
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                if should_offline:
                    await self._set_device_offline(device_id, device.fsm_reason)
                    offline_retry_at = time.monotonic() + _next_offline_delay_seconds(e)
                if self._is_full_monitor_log() and should_offline:
                    retry_in_s = max(0, int(float(offline_retry_at or 0.0) - time.monotonic()))
                    logger.warning(
                        f"资源同步失败 inspect_id={inspect_id} job={n} cost_ms={cost_ms} "
                        f"reason={device.fsm_reason or reason} next_retry_in_s={retry_in_s}{cmds_text}"
                    )
                else:
                    logger.warning(
                        f"资源同步失败 inspect_id={inspect_id} job={n} what={what} cost_ms={cost_ms} "
                        f"reason={device.fsm_reason or reason}{cmds_text}"
                    )

        def _next_offline_delay_seconds(exc: BaseException | None) -> float:
            base = float(getattr(device.config, "offline_retry_delay_seconds", 30.0) or 30.0)
            decision = classify_ssh_failure(
                exc,
                default_base_delay_seconds=base,
                default_max_delay_seconds=max(120.0, base * 20.0),
            )
            n = max(1, int(device.consecutive_failures) - int(device.offline_fail_threshold) + 1)
            return float(decision.next_delay_seconds(n) or base)
        
        # 1. 尝试建立初始连接
        if not await device.connect(progress_cb=_connect_progress):
             logger.warning(f"设备 {device_id} ({device.ip}) 初始连接失败，将在循环中重试")
             reason = str(device.fsm_reason or "连接失败")
             changed, should_offline = device.record_failure(reason)
             if changed:
                 await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
             await self._update_runtime_status(
                 device_id,
                 device.fsm_state,
                 f"连接失败({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or reason}",
             )
             if should_offline:
                 await self._set_device_offline(device_id, device.fsm_reason)
                 offline_retry_at = time.monotonic() + _next_offline_delay_seconds(getattr(device, "last_connect_error", None))

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
                # 优化日志显示：排除冗长的原始回显
                log_info = static_info.copy()
                log_info.pop("version_raw", None)
                logger.info(f"设备 {device_id} 静态信息采集成功: {log_info}")

        await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)

        # 3. 进入主监控循环（tickless）
        local_schedule_rev = int(getattr(device, "schedule_rev", 0) or 0)

        def _rebuild_jobs() -> None:
            jobs.clear()
            try:
                heapq.heapify(jobs)
            except Exception:
                pass

            cfg = getattr(device, "config", None)
            try:
                interval_cfg = float(getattr(cfg, "interval", 60.0)) if cfg is not None else 60.0
            except Exception:
                interval_cfg = 60.0
            _push_job("metrics", float(interval_cfg), start_at=0.0)

            try:
                if cfg is not None:
                    if hasattr(device, "collect_interfaces"):
                        _push_job("interfaces", float(getattr(cfg, "interfaces_sync_interval", 0.0)), start_at=0.0)
                    if hasattr(device, "collect_routes"):
                        _push_job("routes", float(getattr(cfg, "routes_sync_interval", 0.0)), start_at=0.0)
                    if hasattr(device, "collect_vlans"):
                        _push_job("vlans", float(getattr(cfg, "vlans_sync_interval", 0.0)), start_at=0.0)
                    if hasattr(device, "collect_interfaces_detailed"):
                        _push_job(
                            "interfaces_slot0_detailed",
                            float(getattr(cfg, "interfaces_slot0_sync_interval", 0.0)),
                            start_at=0.0,
                        )
            except Exception:
                return

        _rebuild_jobs()

        while self.running:
            try:
                now = time.monotonic()
                if str(device.fsm_state or "").strip() == "offline" and now < float(offline_retry_at or 0.0):
                    await asyncio.sleep(max(0.0, float(offline_retry_at) - now))
                    continue

                current_rev = int(getattr(device, "schedule_rev", 0) or 0)
                if current_rev != local_schedule_rev:
                    local_schedule_rev = current_rev
                    _rebuild_jobs()
                    await self._update_runtime_status(device_id, "reloading", "schedule_rebuild")
                    continue

                if not jobs:
                    await asyncio.sleep(0.1)
                    continue

                executed = 0
                while executed < 5 and jobs:
                    now = time.monotonic()
                    next_run, _, name, period = jobs[0]
                    if now < next_run:
                        break
                    heapq.heappop(jobs)
                    if name == "metrics":
                        await _run_metrics_job()
                    else:
                        await _run_resource_job(name)
                    executed += 1

                    new_next = float(next_run) + float(period)
                    if new_next <= now:
                        new_next = now
                    heapq.heappush(jobs, (new_next, job_seq + 1, name, period))
                    job_seq += 1

                now = time.monotonic()
                if jobs:
                    next_run, _, _, _ = jobs[0]
                    sleep_time = max(0.0, float(next_run) - now)
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                    else:
                        await asyncio.sleep(0)
                else:
                    await asyncio.sleep(0.1)
            
            except asyncio.CancelledError:
                logger.info(f"设备 {device_id} 监控任务被取消")
                break
            except Exception as e:
                # 全局异常捕获
                logger.error(f"设备 {device_id} 监控循环发生未捕获异常: {e}")
                reason = str(e).splitlines()[0] if str(e) else "未捕获异常"
                changed, should_offline = device.record_failure(reason)
                if changed:
                    await self._update_fsm_meta(device_id, device.fsm_state, device.fsm_reason)
                await self._update_runtime_status(
                    device_id,
                    device.fsm_state,
                    f"未捕获异常({device.consecutive_failures}/{device.offline_fail_threshold}): {device.fsm_reason or reason}",
                )
                if should_offline:
                    await self._set_device_offline(device_id, device.fsm_reason)
                    offline_retry_at = time.monotonic() + _next_offline_delay_seconds(e)

    async def _update_device_static_info(self, device_id: int, info: dict):
        return

    async def _update_fsm_meta(self, device_id: int, fsm_state: str, reason: Optional[str] = None):
        """
        更新FSM状态元数据并推送通知
        """
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
        if s == "checking":
            if current in {"", "init", "checking"}:
                if device.status.set_fsm("checking", str(phase or "")):
                    await self._publish_list_update(device_id)
                    await self._publish_detail_update(device_id)
            return

        if s == "collecting":
            if current != "offline":
                if device.status.set_fsm("collecting", str(phase or device.fsm_reason or "")):
                    await self._publish_list_update(device_id)
                    await self._publish_detail_update(device_id)
            return

        if s == "reloading":
            if device.status.set_fsm("reloading", str(phase or device.fsm_reason or "")):
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
                device.status.set_fsm("offline", str(reason or ""))
            
            # 检查告警 (Offline)
            # 将离线原因传递给告警处理器，以便生成更友好的告警信息
            check_data = {"online_status": 0.0}
            if reason:
                check_data["offline_reason"] = reason
            await self.alert_handler.check_alert_rules(device_id, check_data)
            
            await self._publish_list_update(device_id)
            await self._publish_detail_update(device_id)
        except Exception as e:
            logger.error(f"更新设备 {device_id} 离线状态失败: {e}")

    async def _clear_redis_status(self, device_id: int):
        """
        清理指定设备在 Redis 中的运行时状态快照以及接口、路由、VLAN 等资源数据
        """
        try:
            redis_client = redis_manager.get_client()
            did = int(device_id)
            cleared_resources = {"interfaces", "routes", "vlans"}
            keys = [
                f"{self._REDIS_SNAPSHOT_KEY_PREFIX}{did}",
                f"device:{did}:interfaces",
                f"device:{did}:interfaces:last",
                f"device:{did}:routes",
                f"device:{did}:routes:last",
                f"device:{did}:vlans",
                f"device:{did}:vlans:last",
                f"device:{did}:resources:meta",
            ]
            await redis_client.delete(*keys)

            patterns = [
                f"device:{did}:interfaces_slot*_detailed",
                f"device:{did}:interfaces_slot*_detailed:last",
            ]
            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, found = await redis_client.scan(cursor=cursor, match=pattern, count=500)
                    if found:
                        for k in found:
                            if isinstance(k, (bytes, bytearray)):
                                k = k.decode("utf-8", errors="ignore")
                            if not isinstance(k, str):
                                continue
                            parts = k.split(":", 2)
                            if len(parts) >= 3:
                                name = parts[2]
                                if name.endswith(":last"):
                                    name = name[: -len(":last")]
                                if name:
                                    cleared_resources.add(name)
                        await redis_client.delete(*found)
                    if int(cursor) == 0:
                        break

            payload = json.dumps(
                {"device_id": did, "resources": sorted(cleared_resources)},
                ensure_ascii=False,
            )
            await redis_client.publish("device:resource:update", payload)
            await redis_client.publish(
                f"ws:devices:resources:{did}",
                json.dumps(
                    {
                        "type": "resources_updated",
                        "device_id": did,
                        "resources": sorted(cleared_resources),
                        "data": {name: [] for name in sorted(cleared_resources)},
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as e:
            logger.error(f"清理设备 {device_id} Redis状态失败: {e}")

    async def clear_all_redis_statuses(self):
        """
        清理所有已加载设备在 Redis 中的运行时状态快照
        通常在服务关闭时调用
        """
        logger.info("正在清理所有设备的 Redis 状态缓存...")
        tasks = [self._clear_redis_status(device_id) for device_id in self.devices.keys()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _seed_device_statuses(self, device_ids: list[int]):
        """初始化设备状态（预留）"""
        return

    async def _prime_startup_statuses(self):
        """启动时预热状态（预留）"""
        return

    async def refresh_alert_rules(self, device_id: int):
        """刷新单个设备的告警规则（代理到 AlertHandler）"""
        await self.alert_handler.refresh_alert_rules(device_id)
