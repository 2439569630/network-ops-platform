import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional
from datetime import datetime, timezone

from app.models.orm.alert import DeviceAlertRule, DeviceAlertLog
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class AlertHandler:
    """
    告警逻辑处理器
    负责管理告警规则的加载、缓存、检查以及触发告警通知。
    """
    def __init__(self):
        # 告警规则缓存：device_id -> List[DeviceAlertRule]
        self.alert_rules: Dict[int, list] = defaultdict(list)
        # 告警状态缓存：device_id -> { rule_id: { "triggered_at": ts, "is_firing": bool } }
        self.alert_states: Dict[int, dict] = defaultdict(dict)

    async def load_alert_rules(self):
        """加载所有告警规则"""
        try:
            rules = await DeviceAlertRule.filter(is_enabled=True).all()
            self.alert_rules.clear()
            for rule in rules:
                self.alert_rules[rule.device_id].append(rule)
            logger.info(f"已加载 {len(rules)} 条告警规则")
        except Exception as e:
            logger.error(f"加载告警规则失败: {e}")

    async def refresh_alert_rules(self, device_id: int):
        """刷新单个设备的告警规则"""
        try:
            rules = await DeviceAlertRule.filter(device_id=device_id, is_enabled=True).all()
            self.alert_rules[int(device_id)] = rules
            # 清理状态中已不存在的规则
            if int(device_id) in self.alert_states:
                current_rule_ids = {r.id for r in rules}
                tracked_rule_ids = list(self.alert_states[int(device_id)].keys())
                for rid in tracked_rule_ids:
                    if rid not in current_rule_ids:
                        self.alert_states[int(device_id)].pop(rid, None)
            logger.info(f"刷新设备 {device_id} 告警规则成功，当前规则数: {len(rules)}")
        except Exception as e:
            logger.error(f"刷新设备 {device_id} 告警规则失败: {e}")

    async def check_alert_rules(self, device_id: int, metrics: dict):
        """检查告警规则"""
        rules = self.alert_rules.get(int(device_id), [])
        if not rules:
            return

        now = time.time()
        # Ensure alert_states init
        if int(device_id) not in self.alert_states:
            self.alert_states[int(device_id)] = {}
            
        device_states = self.alert_states[int(device_id)]

        for rule in rules:
            # Get value
            val = metrics.get(rule.metric)
            if val is None:
                continue
                
            # Convert to float for comparison if possible
            try:
                # Handle boolean for online_status
                if rule.metric == "online_status":
                     current_val = 1.0 if val else 0.0
                else:
                     # Remove % if present
                     if isinstance(val, str) and val.endswith("%"):
                         val = val[:-1]
                     current_val = float(val)
            except:
                continue
                
            # Check condition
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
                
            # State tracking
            rule_state = device_states.get(rule.id, {"triggered_at": 0, "is_firing": False})
            
            if triggered:
                if rule_state["triggered_at"] == 0:
                    rule_state["triggered_at"] = now
                
                duration = now - rule_state["triggered_at"]
                
                if duration >= rule.duration and not rule_state["is_firing"]:
                    # Fire Alert
                    rule_state["is_firing"] = True
                    await self._log_alert(device_id, rule, current_val, f"触发告警: {rule.metric} {rule.operator} {rule.threshold}")
            else:
                if rule_state["is_firing"]:
                    # Resolve Alert
                    await self._resolve_alert(device_id, rule, current_val)
                
                rule_state["triggered_at"] = 0
                rule_state["is_firing"] = False
                
            device_states[rule.id] = rule_state

    async def _log_alert(self, device_id: int, rule: DeviceAlertRule, value: float, message: str):
        """记录告警并发送通知"""
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
            # TODO: Integrate with NotificationService for email/webhook
            await NotificationService.notify_device_alert(device_id, message, rule.severity)
        except Exception as e:
            logger.error(f"记录告警失败: {e}")

    async def _resolve_alert(self, device_id: int, rule: DeviceAlertRule, value: float):
        """记录告警恢复"""
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
            
            await NotificationService.notify_device_alert(device_id, f"告警恢复: {rule.metric}", "info")
            
        except Exception as e:
            logger.error(f"记录告警恢复失败: {e}")
