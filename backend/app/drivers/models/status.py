from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple, Dict, Any
import time

# 状态机状态
@dataclass
class DeviceStatus:
    """设备状态数据类，用于记录设备连接与采集状态"""
    # 连续失败多少次后判定为离线
    offline_fail_threshold: int = 3
    # 连续成功多少次后判定为恢复
    recovery_success_threshold: int = 2

    # 状态机状态
    fsm_state: str = "init"
    fsm_reason: str = ""
    fsm_updated: float = 0.0

    # 连续失败/成功计数
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    def __post_init__(self) -> None:
        """初始化时间戳"""
        now = float(time.time())
        if not self.fsm_updated:
            self.fsm_updated = now

    @staticmethod
    def _normalize_state(value: Any) -> str:
        s = str(value or "").strip().lower()
        return s or "init"

    @staticmethod
    def _known_states() -> set[str]:
        return {
            "init",
            "checking",
            "collecting",
            "online",
            "degraded",
            "offline",
            "backoff",
            "retrying",
            "recovering",
            "reloading",
        }

    @classmethod
    def _allowed_transitions(cls) -> dict[str, set[str]]:
        return {
            "init": {"checking", "offline", "backoff"},
            "checking": {"collecting", "online", "degraded", "offline", "backoff", "reloading"},
            "collecting": {"online", "degraded", "offline", "backoff", "recovering", "reloading"},
            "online": {"collecting", "checking", "degraded", "offline", "backoff", "reloading"},
            "degraded": {"collecting", "checking", "recovering", "offline", "backoff", "reloading"},
            "offline": {"checking", "recovering", "online", "offline", "backoff", "retrying"},
            "backoff": {"retrying", "offline", "backoff", "checking"},
            "retrying": {"online", "degraded", "offline", "backoff", "checking"},
            "recovering": {"online", "degraded", "offline", "backoff", "collecting", "checking"},
            "reloading": {"checking", "collecting", "online", "degraded", "offline", "backoff"},
        }

    def can_set_fsm(self, new_state: str) -> bool:
        cur = self._normalize_state(self.fsm_state)
        nxt = self._normalize_state(new_state)
        known = self._known_states()
        if cur not in known:
            cur = "init"
        if nxt not in known:
            return False
        if cur == nxt:
            return True
        if nxt == "offline":
            return True
        if nxt == "backoff":
            return True
        if nxt == "init":
            return cur == "init"
        allowed = self._allowed_transitions().get(cur, set())
        return nxt in allowed

    def set_fsm(self, new_state: str, reason: Optional[str] = None) -> bool:
        """设置状态机状态，若状态未变化则返回False"""
        state = self._normalize_state(new_state)
        r = str(reason) if reason else ""
        if state == self._normalize_state(self.fsm_state) and r == self.fsm_reason:
            return False
        if not self.can_set_fsm(state):
            return False
        self.fsm_state = state
        self.fsm_reason = r
        self.fsm_updated = float(time.time())
        return True

    def transition(self, event: str, reason: Optional[str] = None) -> Tuple[bool, bool]:
        e = self._normalize_state(event)
        if e == "success":
            return bool(self.record_success()), False
        if e == "failure":
            changed, should_offline = self.record_failure(reason)
            return bool(changed), bool(should_offline)
        return bool(self.set_fsm(e, reason)), False

    def record_success(self) -> bool:
        """记录一次成功，返回是否触发状态变更"""
        self.consecutive_successes += 1
        self.consecutive_failures = 0

        if self._normalize_state(self.fsm_state) == "offline" and self.consecutive_successes < int(self.recovery_success_threshold):
            return self.set_fsm("recovering", "")
        return self.set_fsm("online", "")

    def record_failure(self, reason: Optional[str] = None) -> Tuple[bool, bool]:
        """记录一次失败，返回(是否触发状态变更, 是否应标记为离线)"""
        self.consecutive_failures += 1
        self.consecutive_successes = 0

        should_offline = self.consecutive_failures >= int(self.offline_fail_threshold)
        if should_offline:
            changed = self.set_fsm("offline", reason)
        else:
            changed = self.set_fsm("degraded", reason)
        return changed, should_offline

    def label(self) -> str:
        """根据状态机与阶段生成中文标签"""
        fsm = self._normalize_state(self.fsm_state)
        if fsm == "offline":
            return "离线"
        if fsm == "backoff":
            return "等待重试"
        if fsm == "retrying":
            return "重试中"
        if fsm == "online":
            return "在线"
        if fsm == "recovering":
            return "恢复中"
        if fsm == "degraded":
            return "异常"
        if fsm == "checking":
            return "检测中"
        if fsm == "collecting":
            return "采集中"
        if fsm == "reloading":
            return "重载中"
        if fsm == "init":
            return "初始化中"
        return "未知"

    def snapshot(self) -> Dict[str, Any]:
        """返回当前状态的快照字典"""
        return {
            "fsm_state": str(self.fsm_state or ""),
            "fsm_reason": str(self.fsm_reason or ""),
            "fsm_updated": str(self.fsm_updated or ""),
            "status": self.label(),
        }

# 设备配置
@dataclass(frozen=True)
class DeviceConfig:
    """设备连接配置数据类，所有字段不可变"""
    # SSH认证信息
    username: str = "root"
    password: str = "password"
    port: int = 22

    # 采集与监控间隔（秒）
    metrics_interval: float = 60.0

    # 状态阈值
    offline_fail_threshold: int = 3
    recovery_success_threshold: int = 2

    # SSH连接超时（秒）
    connect_timeout: float = 30.0
    auth_timeout: float = 30.0
    banner_timeout: float = 100.0
    global_delay_factor: float = 2.0

    # 重试策略
    connect_max_retries: int = 3
    connect_retry_delay_seconds: float = 2.0
    offline_retry_delay_seconds: float = 30.0
    offline_retry_silent_after_attempts: int = 0
    offline_retry_silent_min_interval_seconds: float = 300.0
    resource_sync_interval: float = 3600.0
    interfaces_sync_interval: float = 3600.0
    interfaces_slot0_sync_interval: float = 3600.0
    routes_sync_interval: float = 3600.0
    vlans_sync_interval: float = 3600.0

    @staticmethod
    def from_device_info(device_info: Dict[str, Any]) -> "DeviceConfig":
        """从设备信息字典构造配置，提供默认值与容错"""
        username = device_info.get("user_name", "root")
        password = device_info.get("password", "password")
        port = device_info.get("ssh_port") or device_info.get("port") or 22
        try:
            port_int = int(port)
        except Exception:
            port_int = 22
        return DeviceConfig(
            username=str(username or "root"),
            password=str(password or "password"),
            port=port_int,
        )

    def with_overrides(self, **kwargs: Any) -> "DeviceConfig":
        """基于当前配置创建新实例，支持字段覆盖"""
        return replace(self, **kwargs)
