import time
import logging
import asyncio
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from app.models.orm.alert import DeviceAlertRule, DeviceAlertLog
from app.core.redis import redis_manager
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class AlertHandler:
    """
    告警逻辑处理器
    负责管理告警规则的加载、缓存、检查以及触发告警通知。
    """
    def __init__(self):
        # 告警规则缓存：device_id -> { metric_name: List[DeviceAlertRule] }
        # 优化：按 metric 分组，减少不必要的循环
        self.alert_rules: Dict[int, Dict[str, List[DeviceAlertRule]]] = defaultdict(lambda: defaultdict(list))
        
        # 告警状态缓存：device_id -> { rule_id: { "triggered_at": ts, "is_firing": bool } }
        self.alert_states: Dict[int, dict] = defaultdict(dict)

        self._device_registry: dict[int, Any] | None = None
        self._devices_with_interface_rules: set[int] = set()
        self._interface_check_interval_seconds = 5.0
        self._interface_task: asyncio.Task | None = None

    def bind_device_registry(self, devices: dict[int, Any]) -> None:
        self._device_registry = devices

    def start_background_tasks(self) -> None:
        if self._interface_task is not None and not self._interface_task.done():
            return
        self._interface_task = asyncio.create_task(self._interface_rule_loop())

    async def stop_background_tasks(self) -> None:
        task = self._interface_task
        self._interface_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    def _compute_firing_lock_ttl_seconds(self, *, cooldown_seconds: int) -> int:
        cd = max(0, int(cooldown_seconds or 0))
        return max(cd, 600)

    async def _try_acquire_firing_lock(self, device_id: int, rule_id: int, ttl_seconds: int) -> str:
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return "local"

        try:
            key = f"alert:firing:{device_id}:{rule_id}"
            token = uuid.uuid4().hex
            ok = await redis_client.set(key, token, nx=True, ex=max(int(ttl_seconds), 1))
            return token if ok else ""
        except Exception:
            return "local"

    async def _release_firing_lock(self, device_id: int, rule_id: int, token: Optional[str] = None):
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return

        try:
            key = f"alert:firing:{device_id}:{rule_id}"
            if not token or token == "local":
                await redis_client.delete(key)
                return
            script = (
                "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                "return redis.call('DEL', KEYS[1]) "
                "else return 0 end"
            )
            await redis_client.eval(script, 1, key, token)
        except Exception:
            return

    async def _refresh_firing_lock(self, device_id: int, rule_id: int, token: Optional[str], ttl_seconds: int) -> None:
        if not token or token == "local":
            return
        try:
            redis_client = redis_manager.get_client()
        except Exception:
            return
        try:
            key = f"alert:firing:{device_id}:{rule_id}"
            script = (
                "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                "return redis.call('EXPIRE', KEYS[1], ARGV[2]) "
                "else return 0 end"
            )
            await redis_client.eval(script, 1, key, token, max(int(ttl_seconds), 1))
        except Exception:
            return

    async def load_alert_rules(self):
        """加载所有告警规则"""
        try:
            rules = await DeviceAlertRule.filter(is_enabled=True).all()
            self.alert_rules.clear()
            self._devices_with_interface_rules.clear()
            for rule in rules:
                self.alert_rules[rule.device_id][rule.metric].append(rule)
                if str(rule.metric or "").startswith("if_"):
                    self._devices_with_interface_rules.add(int(rule.device_id))
            logger.info(f"已加载 {len(rules)} 条告警规则")
        except Exception as e:
            logger.error(f"加载告警规则失败: {e}")

    async def refresh_alert_rules(self, device_id: int):
        """刷新单个设备的告警规则"""
        try:
            # 清除旧规则
            if device_id in self.alert_rules:
                del self.alert_rules[device_id]
                
            rules = await DeviceAlertRule.filter(device_id=device_id, is_enabled=True).all()
            has_interface = False
            
            # 重建索引
            for rule in rules:
                self.alert_rules[device_id][rule.metric].append(rule)
                if str(rule.metric or "").startswith("if_"):
                    has_interface = True
                
            # 清理状态中已不存在的规则
            if int(device_id) in self.alert_states:
                current_rule_ids = {r.id for r in rules}
                tracked_rule_ids = list(self.alert_states[int(device_id)].keys())
                for rid in tracked_rule_ids:
                    if rid not in current_rule_ids:
                        self.alert_states[int(device_id)].pop(rid, None)

            if has_interface:
                self._devices_with_interface_rules.add(int(device_id))
            else:
                self._devices_with_interface_rules.discard(int(device_id))
                        
            logger.info(f"刷新设备 {device_id} 告警规则成功，当前规则数: {len(rules)}")
        except Exception as e:
            logger.error(f"刷新设备 {device_id} 告警规则失败: {e}")

    async def _interface_rule_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interface_check_interval_seconds)
                if not self._devices_with_interface_rules:
                    continue
                devices = self._device_registry
                if not devices:
                    continue

                for device_id in list(self._devices_with_interface_rules):
                    device = devices.get(int(device_id))
                    if not device:
                        continue
                    items = getattr(device, "last_interfaces", None)
                    if not items:
                        continue

                    rules_map = self.alert_rules.get(int(device_id)) or {}
                    if not rules_map:
                        continue

                    iface_map: dict[str, Any] = {}
                    try:
                        for it in items:
                            if not isinstance(it, dict):
                                continue
                            name = str(it.get("name") or "").strip()
                            if name:
                                iface_map[name] = it
                    except Exception:
                        continue

                    metrics: dict[str, float] = {}
                    need_phy_count = "if_phy_down_count" in rules_map
                    need_proto_count = "if_protocol_down_count" in rules_map

                    need_phy_names = []
                    need_proto_names = []
                    for k in rules_map.keys():
                        ks = str(k or "")
                        if ks.startswith("if_phy_down:"):
                            need_phy_names.append(ks.split(":", 1)[1])
                        elif ks.startswith("if_protocol_down:"):
                            need_proto_names.append(ks.split(":", 1)[1])

                    if need_phy_count or need_proto_count:
                        phy_down = 0
                        proto_down = 0
                        for it in iface_map.values():
                            phy = str(it.get("phy_state") or "").strip().lower()
                            proto = str(it.get("protocol_state") or "").strip().lower()
                            if need_phy_count and phy and phy != "up":
                                phy_down += 1
                            if need_proto_count and proto and proto != "up":
                                proto_down += 1
                        if need_phy_count:
                            metrics["if_phy_down_count"] = float(phy_down)
                        if need_proto_count:
                            metrics["if_protocol_down_count"] = float(proto_down)

                    for name in need_phy_names:
                        it = iface_map.get(str(name))
                        phy = str((it or {}).get("phy_state") or "").strip().lower()
                        metrics[f"if_phy_down:{name}"] = 1.0 if phy and phy != "up" else 0.0

                    for name in need_proto_names:
                        it = iface_map.get(str(name))
                        proto = str((it or {}).get("protocol_state") or "").strip().lower()
                        metrics[f"if_protocol_down:{name}"] = 1.0 if proto and proto != "up" else 0.0

                    if metrics:
                        await self.check_alert_rules(int(device_id), metrics)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"接口告警检测循环异常: {e}")

    async def check_alert_rules(self, device_id: int, metrics: dict):
        """
        检查告警规则
        优化策略：
        1. Fast Fail: 无规则直接返回
        2. Hash Index: 仅检查 metrics 中存在的指标规则
        3. Async IO: 告警记录异步写入，不阻塞主循环
        """
        device_id = int(device_id)
        
        # 1. Fast Fail
        if device_id not in self.alert_rules:
            return

        device_rules_map = self.alert_rules[device_id]
        if not device_rules_map:
            return

        now = time.time()
        # Ensure alert_states init
        if device_id not in self.alert_states:
            self.alert_states[device_id] = {}
            
        device_states = self.alert_states[device_id]

        severity_rank = {"info": 0, "warning": 1, "critical": 2}

        # 2. 遍历当前采集到的指标 (metrics keys)，仅检查相关规则
        for metric_name, val in metrics.items():
            if metric_name not in device_rules_map:
                continue
                
            rules = device_rules_map[metric_name]
            
            # 解析当前值
            current_val = 0.0
            try:
                # Handle boolean for online_status
                if metric_name == "online_status":
                     current_val = 1.0 if val else 0.0
                else:
                     # Remove % if present
                     if isinstance(val, str) and val.endswith("%"):
                         val = val[:-1]
                     current_val = float(val)
            except:
                continue

            eval_rows = []
            for rule in rules:
                triggered = False
                if rule.operator == ">":
                    triggered = current_val > rule.threshold
                elif rule.operator == "<":
                    triggered = current_val < rule.threshold
                elif rule.operator == ">=":
                    triggered = current_val >= rule.threshold
                elif rule.operator == "<=":
                    triggered = current_val <= rule.threshold
                elif rule.operator == "=":
                    triggered = current_val == rule.threshold

                rule_state = device_states.get(
                    rule.id,
                    {
                        "triggered_at": 0,
                        "is_firing": False,
                        "external_firing": False,
                        "muted": False,
                        "last_fired_at": 0,
                    },
                )
                eval_rows.append((rule, rule_state, triggered))

            active_max_rank = -1
            for rule, rule_state, triggered in eval_rows:
                if triggered and rule_state.get("is_firing"):
                    if not rule_state.get("external_firing", False):
                        ttl = self._compute_firing_lock_ttl_seconds(
                            cooldown_seconds=int(getattr(rule, "cooldown", 0) or 0)
                        )
                        asyncio.create_task(
                            self._refresh_firing_lock(
                                device_id,
                                rule.id,
                                str(rule_state.get("lock_token") or ""),
                                ttl,
                            )
                        )
                    active_max_rank = max(active_max_rank, severity_rank.get(rule.severity, 1))

            candidates = []
            for rule, rule_state, triggered in eval_rows:
                if triggered:
                    cooldown = int(getattr(rule, "cooldown", 0) or 0)
                    last_fired_at = float(rule_state.get("last_fired_at", 0) or 0)
                    if (
                        cooldown > 0
                        and not rule_state.get("is_firing")
                        and last_fired_at > 0
                        and (now - last_fired_at) < cooldown
                    ):
                        rule_state["triggered_at"] = 0
                        device_states[rule.id] = rule_state
                        continue

                    if rule_state.get("triggered_at", 0) == 0:
                        rule_state["triggered_at"] = now
                    duration = now - rule_state["triggered_at"]
                    if duration >= rule.duration and not rule_state.get("is_firing"):
                        if active_max_rank == -1 or severity_rank.get(rule.severity, 1) >= active_max_rank:
                            candidates.append((rule, rule_state))
                else:
                    if rule_state.get("is_firing"):
                        if not rule_state.get("external_firing", False):
                            asyncio.create_task(
                                self._resolve_alert(
                                    device_id,
                                    rule,
                                    current_val,
                                    send_notify=not rule_state.get("muted", False),
                                    release_lock=True,
                                    lock_token=str(rule_state.get("lock_token") or ""),
                                )
                            )
                    rule_state["triggered_at"] = 0
                    rule_state["is_firing"] = False
                    rule_state["external_firing"] = False
                    rule_state["muted"] = False
                    rule_state["lock_token"] = ""
                    rule_state["lock_ttl"] = 0

                device_states[rule.id] = rule_state

            chosen = None
            if candidates:
                def _score(item):
                    rule, _state = item
                    rank = severity_rank.get(rule.severity, 1)
                    op = str(rule.operator or "")
                    if op in {">", ">="}:
                        threshold_score = float(rule.threshold)
                    elif op in {"<", "<="}:
                        threshold_score = -float(rule.threshold)
                    else:
                        threshold_score = 0.0
                    return (rank, threshold_score)

                chosen = max(candidates, key=_score)

            if chosen is not None:
                chosen_rule, chosen_state = chosen

                ttl = self._compute_firing_lock_ttl_seconds(
                    cooldown_seconds=int(getattr(chosen_rule, "cooldown", 0) or 0)
                )
                token = await self._try_acquire_firing_lock(device_id, chosen_rule.id, ttl)
                if not token:
                    chosen_state["is_firing"] = True
                    chosen_state["external_firing"] = True
                    chosen_state["muted"] = True
                    chosen_state["lock_token"] = ""
                    chosen_state["lock_ttl"] = 0
                    device_states[chosen_rule.id] = chosen_state
                else:
                    chosen_state["is_firing"] = True
                    chosen_state["external_firing"] = False
                    chosen_state["muted"] = False
                    chosen_state["last_fired_at"] = now
                    chosen_state["lock_token"] = token
                    chosen_state["lock_ttl"] = ttl

                    msg = f"触发告警: {chosen_rule.metric} {chosen_rule.operator} {chosen_rule.threshold}"
                    if chosen_rule.metric == "online_status" and current_val == 0:
                        reason = metrics.get("offline_reason", "")
                        msg = "设备离线"
                        if reason:
                            msg += f": {reason}"

                    asyncio.create_task(self._log_alert(device_id, chosen_rule, current_val, msg))

                chosen_rank = severity_rank.get(chosen_rule.severity, 1)
                for rule, rule_state, triggered in eval_rows:
                    if rule.id == chosen_rule.id:
                        continue
                    if triggered and rule_state.get("is_firing") and severity_rank.get(rule.severity, 1) < chosen_rank:
                        rule_state["muted"] = True
                        device_states[rule.id] = rule_state

                    if triggered and not rule_state.get("is_firing") and severity_rank.get(rule.severity, 1) < chosen_rank:
                        rule_state["triggered_at"] = now
                        device_states[rule.id] = rule_state

    async def _log_alert(self, device_id: int, rule: DeviceAlertRule, value: float, message: str):
        """记录告警并发送通知 (Async Task)"""
        try:
            logger.warning(f"设备 {device_id} {message}, 当前值: {value}")
            await DeviceAlertLog.create(
                device_id=device_id,
                rule_id=rule.id,
                metric=rule.metric,
                value=value,
                message=message,
                severity=rule.severity
            )
            await NotificationService.notify_device_alert(device_id, message, rule.severity)
        except Exception as e:
            logger.error(f"记录告警失败: {e}")

    async def _resolve_alert(
        self,
        device_id: int,
        rule: DeviceAlertRule,
        value: float,
        send_notify: bool = True,
        release_lock: bool = True,
        lock_token: str = "",
    ):
        """记录告警恢复 (Async Task)"""
        try:
            logger.info(f"设备 {device_id} 告警恢复: {rule.metric}")
            
            # Try to find the latest unresolved log for this rule
            last_log = await DeviceAlertLog.filter(
                device_id=device_id, 
                rule_id=rule.id, 
                resolved_at__isnull=True
            ).order_by("-triggered_at").first()
            
            if last_log:
                last_log.resolved_at = datetime.now(timezone.utc)
                await last_log.save()
            
            msg = f"告警恢复: {rule.metric}"
            if rule.metric == "online_status":
                msg = "设备已恢复在线"

            if send_notify:
                await NotificationService.notify_device_alert(device_id, msg, "info")

            if release_lock:
                await self._release_firing_lock(device_id, rule.id, token=str(lock_token or ""))
            
        except Exception as e:
            logger.error(f"记录告警恢复失败: {e}")
