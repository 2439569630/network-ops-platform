class RedisKeyFactory:
    ALERT_ACTIVE_PREFIX = "alert:active:"
    ALERT_FIRING_LOCK_PREFIX = "alert:dedupe:lock:"
    ALERT_COOLDOWN_PREFIX = "alert:cooldown:"
    MONITOR_RUNTIME_SNAPSHOT_PREFIX = "monitor:runtime:snapshot:"

    @classmethod
    def alert_active(cls, device_id: int, rule_id: int) -> str:
        return f"{cls.ALERT_ACTIVE_PREFIX}{int(device_id)}:{int(rule_id)}"

    @classmethod
    def alert_firing_lock(cls, device_id: int, rule_id: int) -> str:
        return f"{cls.ALERT_FIRING_LOCK_PREFIX}{int(device_id)}:{int(rule_id)}"

    @classmethod
    def alert_cooldown(cls, device_id: int, rule_id: int) -> str:
        return f"{cls.ALERT_COOLDOWN_PREFIX}{int(device_id)}:{int(rule_id)}"

    @classmethod
    def monitor_runtime_snapshot(cls, device_id: int) -> str:
        return f"{cls.MONITOR_RUNTIME_SNAPSHOT_PREFIX}{int(device_id)}"

    @classmethod
    def device_resource_cache_keys(cls, device_id: int) -> list[str]:
        did = int(device_id)
        return [
            cls.monitor_runtime_snapshot(did),
            f"device:{did}:interfaces",
            f"device:{did}:interfaces:last",
            f"device:{did}:routes",
            f"device:{did}:routes:last",
            f"device:{did}:vlans",
            f"device:{did}:vlans:last",
            f"device:{did}:resources:meta",
        ]

    @classmethod
    def device_resource_cache_patterns(cls, device_id: int) -> list[str]:
        did = int(device_id)
        return [
            f"device:{did}:interfaces_slot*_detailed",
            f"device:{did}:interfaces_slot*_detailed:last",
        ]

    @classmethod
    def is_alert_state_key(cls, key: str) -> bool:
        if not isinstance(key, str):
            return False
        return key.startswith(
            (
                cls.ALERT_ACTIVE_PREFIX,
                cls.ALERT_FIRING_LOCK_PREFIX,
                cls.ALERT_COOLDOWN_PREFIX,
            )
        )
