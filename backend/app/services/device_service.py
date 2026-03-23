
import asyncio
import json
import logging
import time
import datetime
from typing import List, Optional, Dict, Any
from fastapi import HTTPException
from app.core.database import db
from app.constants.user import DELETED_USER_DISPLAY_NAME
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.core.redis import redis_manager
from app.workers.monitor.manager import MonitorManager
from app.utils.device_status import status_fields_from_snapshot
from netmiko import ConnectHandler
from app.services.device_event_service import DeviceEventService
from app.services.notification_service import NotificationService

# ORM Imports
from app.models.orm.device import NetworkDevice
from app.models.orm.user import User
from app.models.orm.audit import DeviceChangeLog, SshCommandAuditLog
from tortoise.expressions import Q
from tortoise.functions import Count

from app.models.orm.location import LocationNode, LocationNodeDevice
from app.models.orm.device import DeviceConfigEntry

from app.services.location_service import LocationService

logger = logging.getLogger(__name__)

class DeviceService:
    """
    设备服务类
    处理设备管理相关的业务逻辑，包括设备的增删改查、配置管理、状态监控等。
    """
    DEVICE_CONFIG_GROUP_LABELS = {
        "basic_monitoring": "基础监控配置",
        "resource_sync": "资源同步配置",
        "state_recovery_policy": "状态判定与重连策略",
        "alert_notification": "告警与通知配置",
    }

    DEVICE_CONFIG_FIELD_META = {
        "metrics_interval": {"label": "指标监控周期（秒）", "group": "basic_monitoring", "advanced": False},
        "connect_timeout": {"label": "连接超时（秒）", "group": "basic_monitoring", "advanced": False},
        "auth_timeout": {"label": "认证超时（秒）", "group": "basic_monitoring", "advanced": True},
        "banner_timeout": {"label": "Banner 超时（秒）", "group": "basic_monitoring", "advanced": True},
        "global_delay_factor": {"label": "全局延迟因子", "group": "basic_monitoring", "advanced": True},
        "resource_sync_interval": {"label": "资源同步总间隔（秒）", "group": "resource_sync", "advanced": True},
        "interfaces_sync_interval": {"label": "接口同步间隔（秒）", "group": "resource_sync", "advanced": True},
        "interfaces_slot0_sync_interval": {"label": "插槽0接口详情同步间隔（秒）", "group": "resource_sync", "advanced": True},
        "routes_sync_interval": {"label": "路由同步间隔（秒）", "group": "resource_sync", "advanced": True},
        "vlans_sync_interval": {"label": "VLAN 同步间隔（秒）", "group": "resource_sync", "advanced": True},
        "offline_fail_threshold": {"label": "离线判定阈值（次）", "group": "state_recovery_policy", "advanced": False},
        "recovery_success_threshold": {"label": "恢复判定阈值（次）", "group": "state_recovery_policy", "advanced": False},
        "connect_max_retries": {"label": "最大重连次数", "group": "state_recovery_policy", "advanced": True},
        "connect_retry_delay_seconds": {"label": "重连等待时间（秒）", "group": "state_recovery_policy", "advanced": True},
        "offline_retry_delay_seconds": {"label": "离线重试间隔（秒）", "group": "state_recovery_policy", "advanced": True},
        "offline_retry_silent_after_attempts": {"label": "静默重试阈值", "group": "state_recovery_policy", "advanced": True},
        "offline_retry_silent_min_interval_seconds": {"label": "静默最小间隔（秒）", "group": "state_recovery_policy", "advanced": True},
    }

    DEVICE_CONFIG_BASIC_FIELDS = (
        "metrics_interval",
        "connect_timeout",
        "offline_fail_threshold",
        "recovery_success_threshold",
    )

    def _group_device_config(self, flat_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {
            k: {} for k in self.DEVICE_CONFIG_GROUP_LABELS.keys()
        }
        for field, meta in self.DEVICE_CONFIG_FIELD_META.items():
            group = str(meta.get("group") or "").strip()
            if not group:
                continue
            if group not in grouped:
                grouped[group] = {}
            grouped[group][field] = flat_config.get(field)
        return grouped

    async def get_device_config_meta(self) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        for key, meta in self.DEVICE_CONFIG_FIELD_META.items():
            fields[key] = {
                "label": meta.get("label"),
                "group": meta.get("group"),
                "advanced": bool(meta.get("advanced", False)),
            }
        return {
            "group_labels": self.DEVICE_CONFIG_GROUP_LABELS,
            "basic_fields": list(self.DEVICE_CONFIG_BASIC_FIELDS),
            "all_fields": list(self.DEVICE_CONFIG_FIELD_META.keys()),
            "fields": fields,
        }

    async def get_device_config_grouped(self, device_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        flat = await self.get_device_config(int(device_id))
        grouped = self._group_device_config(flat)
        meta = await self.get_device_config_meta()
        capabilities = await NotificationService.get_alert_notification_capabilities(user_id=user_id, device_id=device_id)
        return {
            "device_id": int(device_id),
            "flat": flat,
            "grouped": grouped,
            "meta": meta,
            "capabilities": capabilities,
        }

    async def get_device_config_capabilities(self, user_id: Optional[int] = None, device_id: Optional[int] = None) -> Dict[str, Any]:
        return await NotificationService.get_alert_notification_capabilities(user_id=user_id, device_id=device_id)

    # Helper to convert ORM object to dict (simple version)
    def _model_to_dict(self, obj: Any) -> Dict[str, Any]:
        """
        将 ORM 对象转换为字典
        """
        if not obj:
            return {}
        # Tortoise models can be converted to dict, but we need to handle serialization
        # This is a basic implementation. Pydantic from_orm is better if available.
        return dict(obj)

    async def has_deleted_at(self) -> bool:
        """
        检查模型是否包含 deleted_at 字段
        """
        # With ORM, we assume the model schema is correct. 
        # If the column is missing, it should be added to the DB.
        return True

    async def ensure_ssh_command_audit_table(self) -> bool:
        """
        确保 SSH 命令审计表存在
        """
        # Tortoise generate_schemas=True handles table creation usually.
        # But we keep this just in case we need explicit check, or remove it.
        # For now, we assume ORM handles it.
        return True

    async def get_device_list(self, type_code: int = 0, search_query: str = None, location_filter: str = None, location_node_id: int = None) -> List[dict]:
        """
        获取设备列表
        支持按类型、关键字、位置过滤
        """
        logger.info(f"Start get_device_list (ORM): type={type_code}, search={search_query}, location={location_filter}, node_id={location_node_id}")
        normalized_search = str(search_query or "").strip()

        # Build Query using Tortoise ORM
        query = NetworkDevice.filter(is_active=True, deleted_at__isnull=True)

        if location_node_id:
            # Find node by ID
            node = await LocationNode.get_or_none(id=location_node_id)
            if node:
                # Include descendants
                node_ids = await LocationService.get_descendant_ids(node.id)
                node_ids.append(node.id)
                
                device_ids = await LocationNodeDevice.filter(node_id__in=node_ids).values_list("device_id", flat=True)
                query = query.filter(id__in=device_ids)
            else:
                query = query.filter(id=-1)
        elif location_filter:
            # Join with mapping table to filter by location name
            # Find node id first
            node = await LocationNode.filter(name=location_filter).first()
            if node:
                # Include descendants
                node_ids = await LocationService.get_descendant_ids(node.id)
                node_ids.append(node.id)
                
                device_ids = await LocationNodeDevice.filter(node_id__in=node_ids).values_list("device_id", flat=True)
                query = query.filter(id__in=device_ids)
            else:
                # If location node not found, return empty
                query = query.filter(id=-1)

        if type_code == 1:  # Router
            query = query.filter(device_type__in=['router', '路由器', 'huawei'])
        elif type_code == 2:  # Switch
            query = query.filter(device_type__in=['switch', '交换机'])
        elif type_code == 3:  # Firewall
            query = query.filter(device_type__in=['firewall', '防火墙'])
        elif type_code == 4:  # Server
            query = query.filter(device_type__in=['server', '服务器', 'linux'])

        if normalized_search:
            # For search, we also need to check location name.
            # This is tricky without Join.
            # We can find all node IDs that match the search name
            matched_nodes = await LocationNode.filter(name__icontains=normalized_search).values_list("id", flat=True)
            matched_dev_ids_from_loc = []
            if matched_nodes:
                matched_dev_ids_from_loc = await LocationNodeDevice.filter(node_id__in=matched_nodes).values_list("device_id", flat=True)

            q_obj = Q(device_name__icontains=normalized_search) | Q(ipv4__icontains=normalized_search)
            if matched_dev_ids_from_loc:
                q_obj |= Q(id__in=matched_dev_ids_from_loc)
            
            query = query.filter(q_obj)

        try:
            # Fetch data
            devices = await query.all().order_by("-id")
            
            # Fetch mappings for these devices to show location name
            device_ids_list = [d.id for d in devices]
            mappings = await LocationNodeDevice.filter(device_id__in=device_ids_list).all()
            
            # Map device_id -> node_id
            dev_to_node = {m.device_id: m.node_id for m in mappings}
            
            # Fetch node names
            node_ids = set(dev_to_node.values())
            nodes = await LocationNode.filter(id__in=list(node_ids)).all()
            node_map = {n.id: n.name for n in nodes}
            
            # Map created_by to username
            user_ids = {int(d.created_by) for d in devices if d.created_by and d.created_by.isdigit()}
            users = await User.filter(id__in=list(user_ids)).all()
            user_map = {u.id: u.username for u in users}

            result = []
            for d in devices:
                created_by_name = ""
                if d.created_by:
                    if d.created_by.isdigit():
                        created_by_name = user_map.get(int(d.created_by)) or DELETED_USER_DISPLAY_NAME
                    else:
                        created_by_name = str(d.created_by)
                
                # Get location name from mapping
                node_id = dev_to_node.get(d.id)
                loc_name = node_map.get(node_id, "") if node_id else ""
                
                result.append({
                    "id": d.id,
                    "device_name": d.device_name,
                    "user_name": d.user_name,
                    "ipv4": str(d.ipv4) if d.ipv4 else "",
                    "ipv6": str(d.ipv6) if d.ipv6 else "",
                    "mac": str(d.mac) if d.mac else "",
                    "device_type": d.device_type,
                    "location": loc_name,
                    "ssh_port": d.ssh_port,
                    "created_by": d.created_by,
                    "created_by_name": created_by_name
                })
                
        except Exception as e:
            logger.error(f"ORM Fetch Error: {e}", exc_info=True)
            return []

        monitor = MonitorManager()
        monitor_alive = False
        monitor_heartbeat_age_seconds = 0.0
        try:
            redis_client = redis_manager.get_client()
            raw = await redis_client.get(getattr(MonitorManager, "_LEADER_HEARTBEAT_KEY", "monitor:leader:heartbeat"))
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            payload = json.loads(raw) if raw else None
            ts = float(payload.get("ts") or 0) if isinstance(payload, dict) else 0.0
            if ts > 0:
                monitor_heartbeat_age_seconds = float(time.time() - ts)
                ttl = float(getattr(MonitorManager, "_LEADER_LOCK_TTL_SECONDS", 90) or 90)
                monitor_alive = monitor_heartbeat_age_seconds <= max(5.0, ttl)
        except Exception:
            monitor_alive = False
            monitor_heartbeat_age_seconds = 0.0
        data: list[dict] = []
        for row in result:
            try:
                device_id = int(row["id"])
                snap = await monitor.get_runtime_snapshot_async(device_id)
                base = status_fields_from_snapshot(snap)
                data.append(
                    {
                        "id": device_id,
                        "device_name": row["device_name"],
                        "user_name": str(row.get("user_name") or ""),
                        "ipv4": row["ipv4"],
                        "ipv6": row["ipv6"],
                        "mac": row["mac"],
                        "status": str(snap.get("status") or "无运行态"),
                        "display_status": str(base.get("display_status") or snap.get("status") or "无运行态"),
                        "connectivity": str(base.get("connectivity") or "offline"),
                        "online_status": bool(base.get("online_status")),
                        "fsm_state": str(base.get("fsm_state") or ""),
                        "fsm_reason": str(base.get("fsm_reason") or ""),
                        "fsm_updated": str(base.get("fsm_updated") or ""),
                        "snapshot_source": str(snap.get("snapshot_source") or ""),
                        "snapshot_generated_at": str(snap.get("snapshot_generated_at") or ""),
                        "age_seconds": float(snap.get("age_seconds") or 0.0),
                        "stale": bool(snap.get("stale")),
                        "monitor_alive": bool(monitor_alive),
                        "monitor_heartbeat_age_seconds": float(monitor_heartbeat_age_seconds),
                        "type": row["device_type"],
                        "location": row["location"],
                        "ssh_port": row["ssh_port"],
                        "cpu_usage": str(snap.get("cpu_usage") or "--"),
                        "memory_usage": str(snap.get("memory_usage") or "--"),
                        "disk_usage": str(snap.get("disk_usage") or "--"),
                        "uptime": str(snap.get("uptime") or "未知"),
                        "last_updated": str(snap.get("last_updated") or ""),
                        "os_version": str(snap.get("os_version") or snap.get("kernel") or "Unknown"),
                        "created_by": str(row.get("created_by") or ""),
                        "created_by_name": str(row.get("created_by_name") or DELETED_USER_DISPLAY_NAME),
                        "ops_admin_name": str(row.get("created_by_name") or DELETED_USER_DISPLAY_NAME),
                    }
                )
            except Exception as e:
                logger.error(f"Row processing error: {e}", exc_info=True)
                continue
        
        logger.info(f"Returning {len(data)} devices")
        return data

    async def add_device(self, device: DeviceCreate, user_id: int) -> int:
        """
        添加新设备
        """
        # 唯一性检查：IP + 端口组合必须唯一
        if await NetworkDevice.filter(ipv4=device.ipv4, ssh_port=device.ssh_port).exists():
            raise ValueError("该IP+端口已存在")

        ipv6 = device.ipv6 if device.ipv6 and device.ipv6.strip() else None
        mac = device.mac if device.mac and device.mac.strip() else None
        # location = device.location if device.location and device.location.strip() else None

        new_device = await NetworkDevice.create(
            device_name=device.device_name,
            ipv4=device.ipv4,
            ipv6=ipv6,
            mac=mac,
            device_type=device.type,
            user_name=device.user_name,
            password=device.password,
            ssh_port=device.ssh_port,
            created_by=str(user_id),
            is_active=True
        )

        await self._log_device_change(
            device_id=new_device.id,
            change_type="create",
            change_description="新增设备",
            changed_by=str(user_id),
            old_values=None,
            new_values={
                "device_name": device.device_name,
                "ipv4": device.ipv4,
                "ipv6": ipv6,
                "mac": mac,
                "device_type": device.type,
                "user_name": device.user_name,
                "ssh_port": device.ssh_port,
            },
        )
        await DeviceEventService.publish_device_event("add", int(new_device.id))
        return int(new_device.id)

    async def get_device_config(self, device_id: int) -> dict:
        did = int(device_id)
        entry = await DeviceConfigEntry.get_or_none(device_id=did)
        if not entry:
            return {
                "device_id": did,
                "metrics_interval": None,
                "resource_sync_interval": 3600.0,
                "interfaces_sync_interval": 3600.0,
                "interfaces_slot0_sync_interval": 3600.0,
                "routes_sync_interval": 3600.0,
                "vlans_sync_interval": 3600.0,
            }
        return {
            "device_id": did,
            "metrics_interval": getattr(entry, "metrics_interval", None),
            "offline_fail_threshold": entry.offline_fail_threshold,
            "recovery_success_threshold": entry.recovery_success_threshold,
            "connect_timeout": entry.connect_timeout,
            "auth_timeout": entry.auth_timeout,
            "banner_timeout": entry.banner_timeout,
            "global_delay_factor": entry.global_delay_factor,
            "connect_max_retries": entry.connect_max_retries,
            "connect_retry_delay_seconds": entry.connect_retry_delay_seconds,
            "offline_retry_delay_seconds": entry.offline_retry_delay_seconds,
            "offline_retry_silent_after_attempts": getattr(entry, "offline_retry_silent_after_attempts", None),
            "offline_retry_silent_min_interval_seconds": getattr(entry, "offline_retry_silent_min_interval_seconds", None),
            "resource_sync_interval": entry.resource_sync_interval,
            "interfaces_sync_interval": getattr(entry, "interfaces_sync_interval", 3600.0),
            "interfaces_slot0_sync_interval": getattr(entry, "interfaces_slot0_sync_interval", 3600.0),
            "routes_sync_interval": getattr(entry, "routes_sync_interval", 3600.0),
            "vlans_sync_interval": getattr(entry, "vlans_sync_interval", 3600.0),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    async def update_device_config(self, device_id: int, patch: dict, updated_by: Optional[str] = None) -> dict:
        """
        更新设备配置
        """
        did = int(device_id)
        clean: dict = {}

        def _normalize_period_seconds(value):
            if value is None:
                return None
            try:
                v = float(value)
            except Exception:
                return None
            if v == -1:
                return -1.0
            if v <= 0:
                return None
            return max(1.0, v)

        def _normalize_period_seconds_with_default(value, default_seconds: float):
            if value is None:
                return float(default_seconds)
            try:
                v = float(value)
            except Exception:
                return float(default_seconds)
            if v == -1:
                return -1.0
            if v <= 0:
                return float(default_seconds)
            return max(1.0, v)

        allowed = set(self.DEVICE_CONFIG_FIELD_META.keys())
        for k in allowed:
            if k in patch:
                clean[k] = patch.get(k)

        if "metrics_interval" in clean:
            clean["metrics_interval"] = _normalize_period_seconds(clean.get("metrics_interval"))

        for k in (
            "resource_sync_interval",
            "interfaces_sync_interval",
            "interfaces_slot0_sync_interval",
            "routes_sync_interval",
            "vlans_sync_interval",
        ):
            if k in clean:
                clean[k] = _normalize_period_seconds_with_default(clean.get(k), 3600.0)

        if "resource_sync_interval" in clean:
            has_split = any(
                x in clean
                for x in (
                    "interfaces_sync_interval",
                    "interfaces_slot0_sync_interval",
                    "routes_sync_interval",
                    "vlans_sync_interval",
                )
            )
            if not has_split:
                clean["interfaces_sync_interval"] = clean["resource_sync_interval"]
                clean["interfaces_slot0_sync_interval"] = clean["resource_sync_interval"]
                clean["routes_sync_interval"] = clean["resource_sync_interval"]
                clean["vlans_sync_interval"] = clean["resource_sync_interval"]
        
        entry = await DeviceConfigEntry.get_or_none(device_id=did)
        
        # Only keep old values for fields that are being updated to ensure symmetry
        old_values = {}
        if entry:
            for k in clean.keys():
                old_values[k] = getattr(entry, k)
        else:
            old_values = None

        if not entry:
            entry = await DeviceConfigEntry.create(device_id=did, **clean)
        else:
            for k, v in clean.items():
                setattr(entry, k, v)
            await entry.save()
        
        # Translate field names for better audit log
        field_names = {
            "metrics_interval": "指标巡检周期",
            "offline_fail_threshold": "离线阈值",
            "recovery_success_threshold": "恢复阈值",
            "connect_timeout": "连接超时",
            "auth_timeout": "认证超时",
            "banner_timeout": "Banner超时",
            "global_delay_factor": "全局延迟因子",
            "connect_max_retries": "连接最大重试",
            "connect_retry_delay_seconds": "连接重试间隔",
            "offline_retry_delay_seconds": "离线重试间隔",
            "offline_retry_silent_after_attempts": "静默重试阈值",
            "offline_retry_silent_min_interval_seconds": "静默重试最小间隔",
            "resource_sync_interval": "深度巡检间隔",
            "interfaces_sync_interval": "接口同步间隔",
            "interfaces_slot0_sync_interval": "插槽0接口详情同步间隔",
            "routes_sync_interval": "路由同步间隔",
            "vlans_sync_interval": "VLAN同步间隔",
        }
        
        changes_list = []
        for k, v in clean.items():
            old_v = old_values.get(k) if old_values else None
            # Compare values. If old_values is None (creation), everything is a change.
            # If old_values exists, check if value changed.
            # Convert both to string to be safe against int vs str mismatch if any, 
            # though usually they are consistent types.
            is_changed = True
            if old_values is not None:
                # Use str comparison for simplicity, or direct equality
                if str(old_v) == str(v):
                    is_changed = False
            
            if is_changed:
                field_name = field_names.get(k, k)
                changes_list.append(f"{field_name}({old_v}→{v})")

        if not changes_list:
            desc = "更新监控参数配置: 无变更"
        else:
            desc = f"更新监控参数配置: {', '.join(changes_list)}"

        await self._log_device_change(
            device_id=did,
            change_type="update_config",
            change_description=desc,
            changed_by=str(updated_by or ""),
            old_values=old_values,
            new_values=clean,
        )

        await DeviceEventService.publish_device_event("config_update", did)

        return await self.get_device_config(did)

    async def delete_device(self, device_id: Optional[int] = None, ip: Optional[str] = None, deleted_by: Optional[str] = None):
        """
        删除设备 (软删除)
        """
        device = None
        if device_id:
            device = await NetworkDevice.get_or_none(id=device_id)
        elif ip:
            # 如仅按IP匹配，需处理多匹配的情况
            matches = await NetworkDevice.filter(ipv4=ip).all()
            if len(matches) == 1:
                device = matches[0]
            elif len(matches) > 1:
                raise ValueError("存在多个设备使用该IP，请提供设备ID进行删除")
        
        if not device:
            raise ValueError("必须提供有效的设备ID或IP地址")

        old_values = dict(device)
        
        # Soft delete
        device.is_active = False
        import datetime
        device.deleted_at = datetime.datetime.now()
        device.updated_at = datetime.datetime.now()
        device.updated_by = str(deleted_by or "")
        
        await device.save()
        
        # Remove mapping on delete? Or keep it?
        # Usually we keep it if it's soft delete, but maybe we should clear it to avoid "ghost" if restored?
        # Let's keep it for now as soft delete implies "recycle bin". 
        # But if the user purges, we delete.

        await self._log_device_change(
            device_id=device.id,
            change_type="delete",
            change_description="删除设备(移入回收站)",
            changed_by=str(deleted_by or ""),
            old_values=old_values,
            new_values={"deleted_at": str(device.deleted_at), "is_active": False},
        )
        await DeviceEventService.publish_device_event("delete", int(device.id))

    async def get_deleted_devices(self, user_id: Optional[int] = None, is_super: bool = False) -> List[dict]:
        """
        获取已删除设备列表 (回收站)
        
        Args:
            user_id: 当前用户ID
            is_super: 是否是超级管理员
        """
        # ORM query for deleted devices
        query = NetworkDevice.filter(deleted_at__isnull=False)
        
        # 权限过滤：非超级管理员只能看到自己创建的设备
        # 或者自己删除的设备？
        # 通常回收站应该看到自己有权看到的设备。
        # 简单起见，这里逻辑是：如果是非超管，只能看 created_by=自己 OR updated_by=自己 (即执行删除操作的人)
        if not is_super and user_id is not None:
            # 兼容 created_by 可能为空的情况
            uid = str(user_id)
            query = query.filter(Q(created_by=uid) | Q(updated_by=uid))
            
        devices = await query.order_by("-deleted_at", "-id").all()
        
        # 批量获取位置信息
        device_ids = [d.id for d in devices]
        loc_map = {}
        if device_ids:
            mappings = await LocationNodeDevice.filter(device_id__in=device_ids).all()
            if mappings:
                node_ids = {m.node_id for m in mappings}
                nodes = await LocationNode.filter(id__in=list(node_ids)).all()
                node_name_map = {n.id: n.name for n in nodes}
                
                for m in mappings:
                    if m.node_id in node_name_map:
                        loc_map[m.device_id] = node_name_map[m.node_id]

        result = []
        for d in devices:
            result.append({
                "id": d.id,
                "device_name": d.device_name,
                "ipv4": str(d.ipv4),
                "device_type": d.device_type,
                "location": loc_map.get(d.id, ""),
                "ssh_port": d.ssh_port,
                "deleted_at": d.deleted_at,
                "deleted_by": d.updated_by or "" 
            })
        return result

    async def restore_device(self, device_id: int, restored_by: Optional[str] = None) -> None:
        device = await NetworkDevice.get_or_none(id=device_id)
        if not device:
            return

        old_values = dict(device)
        
        device.is_active = True
        device.deleted_at = None
        device.updated_at = datetime.datetime.now()
        device.updated_by = str(restored_by or "")
        await device.save()

        await self._log_device_change(
            device_id=device.id,
            change_type="restore",
            change_description="从回收站恢复设备",
            changed_by=str(restored_by or ""),
            old_values=old_values,
            new_values={"deleted_at": None, "is_active": True},
        )
        await DeviceEventService.publish_device_event("add", int(device.id))

    async def purge_device(self, device_id: int) -> None:
        """
        彻底删除设备
        """
        device = await NetworkDevice.get_or_none(id=device_id)
        if not device:
            return

        old_values = dict(device)
        
        # Delete mapping
        await LocationNodeDevice.filter(device_id=device_id).delete()
        
        await device.delete()
        
        await self._log_device_change(
            device_id=device.id,
            change_type="purge",
            change_description="从回收站彻底删除设备",
            changed_by="",
            old_values=old_values,
            new_values=None,
        )
        await DeviceEventService.publish_device_event("delete", int(device.id))

    async def update_device(self, device_id: int, patch: DeviceUpdate, updated_by: Optional[str] = None) -> None:
        device = await NetworkDevice.get_or_none(id=device_id)
        if not device:
            return

        old_values = dict(device)
        try:
            old_values.pop("password", None)
        except Exception:
            pass
        import datetime

        next_ipv4 = str(device.ipv4 or "")
        next_ssh_port = int(device.ssh_port or 22)
        if getattr(patch, "ipv4", None) is not None:
            v = str(getattr(patch, "ipv4") or "").strip()
            if not v:
                raise HTTPException(status_code=400, detail="IPv4不能为空")
            next_ipv4 = v
        if getattr(patch, "ssh_port", None) is not None:
            try:
                next_ssh_port = int(getattr(patch, "ssh_port") or 0)
            except Exception:
                next_ssh_port = 0
            if next_ssh_port <= 0 or next_ssh_port > 65535:
                raise HTTPException(status_code=400, detail="SSH端口不合法")
        if next_ipv4 != str(device.ipv4 or "") or next_ssh_port != int(device.ssh_port or 22):
            exists = await NetworkDevice.filter(ipv4=next_ipv4, ssh_port=next_ssh_port).exclude(id=device.id).exists()
            if exists:
                raise HTTPException(status_code=400, detail="该IP+端口已存在")

        if patch.device_name is not None:
            device.device_name = patch.device_name

        if getattr(patch, "type", None) is not None:
            device.device_type = getattr(patch, "type")
        if getattr(patch, "ipv4", None) is not None:
            device.ipv4 = next_ipv4
        if getattr(patch, "ssh_port", None) is not None:
            device.ssh_port = next_ssh_port
        if getattr(patch, "ipv6", None) is not None:
            v = str(getattr(patch, "ipv6") or "").strip()
            device.ipv6 = v or None
        if getattr(patch, "mac", None) is not None:
            v = str(getattr(patch, "mac") or "").strip()
            device.mac = v or None
        if getattr(patch, "user_name", None) is not None:
            device.user_name = str(getattr(patch, "user_name") or "").strip()
        if getattr(patch, "password", None) is not None:
            device.password = str(getattr(patch, "password") or "")
        if getattr(patch, "is_active", None) is not None:
            device.is_active = bool(getattr(patch, "is_active"))

        device.updated_at = datetime.datetime.now()
        device.updated_by = str(updated_by or "")
        
        await device.save()

        
        # Reload to get fresh values if needed, or just use what we set
        new_values = dict(device)
        try:
            new_values.pop("password", None)
        except Exception:
            pass

        await self._log_device_change(
            device_id=device.id,
            change_type="update",
            change_description="更新设备信息",
            changed_by=str(updated_by or ""),
            old_values=old_values,
            new_values=new_values,
        )
        await DeviceEventService.publish_device_event("update", int(device.id))

    async def test_connect(self, device: DeviceCreate):
        """
        测试设备连接 (SSH)
        """
        # 映射设备类型
        netmiko_device_type = 'linux'
        if device.type in ['路由器', '交换机', '防火墙', 'huawei']:
            netmiko_device_type = 'huawei'
        elif device.type == '服务器':
            netmiko_device_type = 'linux'
            
        params = {
            'device_type': netmiko_device_type,
            'host': device.ipv4,
            'port': device.ssh_port,
            'username': device.user_name,
            'password': device.password,
            'timeout': 10
        }
        
        def _connect():
            conn = ConnectHandler(**params)
            conn.disconnect()
            return True

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _connect)
        return True

    async def log_device_action(self, device_id: int, action: str, description: str, changed_by: str, payload: Optional[dict] = None) -> None:
        """
        记录设备操作日志
        """
        await self._log_device_change(
            device_id=int(device_id),
            change_type=str(action),
            change_description=str(description),
            changed_by=str(changed_by or ""),
            old_values=None,
            new_values=payload,
        )

    async def log_ssh_command(self, device_id: int, device_ip: str, command: str, executed_by: str) -> None:
        cmd = str(command or "")
        if not cmd.strip():
            return
        
        try:
            await SshCommandAuditLog.create(
                device_id=int(device_id),
                device_ip=str(device_ip or ""),
                command=cmd,
                executed_by=str(executed_by or "")
            )
        except Exception as e:
            logger.error(f"写入 SSH 命令审计失败: {e}", exc_info=True)

    async def get_ssh_command_audit_logs(self, device_id: int, page: int = 1, page_size: int = 50) -> dict:
        p = max(1, int(page or 1))
        ps = max(1, min(200, int(page_size or 50)))
        offset = (p - 1) * ps
        
        total = await SshCommandAuditLog.filter(device_id=device_id).count()
        logs = await SshCommandAuditLog.filter(device_id=device_id)\
            .order_by("-executed_at", "-id")\
            .offset(offset)\
            .limit(ps)\
            .all()

        # Fetch user names
        user_ids = {int(l.executed_by) for l in logs if l.executed_by and l.executed_by.isdigit()}
        users = await User.filter(id__in=list(user_ids)).all()
        user_map = {u.id: u.username for u in users}

        items = []
        for l in logs:
            executed_by_name = ""
            if l.executed_by:
                if l.executed_by.isdigit():
                    executed_by_name = user_map.get(int(l.executed_by)) or DELETED_USER_DISPLAY_NAME
                else:
                    executed_by_name = DELETED_USER_DISPLAY_NAME
            items.append({
                "id": l.id,
                "device_id": l.device_id,
                "device_ip": l.device_ip,
                "command": l.command,
                "executed_by": l.executed_by,
                "executed_by_name": executed_by_name,
                "executed_at": l.executed_at
            })
            
        return {"items": items, "total": total, "page": p, "page_size": ps}

    async def get_device_change_logs(self, device_id: int, page: int = 1, page_size: int = 50) -> dict:
        """
        获取设备变更日志
        """
        p = max(1, int(page or 1))
        ps = max(1, min(200, int(page_size or 50)))
        offset = (p - 1) * ps
        
        total = await DeviceChangeLog.filter(device_id=device_id).count()
        logs = await DeviceChangeLog.filter(device_id=device_id)\
            .order_by("-changed_at", "-id")\
            .offset(offset)\
            .limit(ps)\
            .all()
            
        # Fetch user names
        user_ids = {int(l.changed_by) for l in logs if l.changed_by and l.changed_by.isdigit()}
        users = await User.filter(id__in=list(user_ids)).all()
        user_map = {u.id: u.username for u in users}

        items = []
        for l in logs:
            changed_by_name = ""
            if l.changed_by:
                if l.changed_by.isdigit():
                    changed_by_name = user_map.get(int(l.changed_by)) or DELETED_USER_DISPLAY_NAME
                else:
                    changed_by_name = DELETED_USER_DISPLAY_NAME
            items.append({
                "id": l.id,
                "device_id": l.device_id,
                "change_type": l.change_type,
                "change_description": l.change_description,
                "changed_by": l.changed_by,
                "changed_by_name": changed_by_name,
                "changed_at": l.changed_at,
                "old_values": l.old_values,
                "new_values": l.new_values
            })

        return {"items": items, "total": total, "page": p, "page_size": ps}

    def _sanitize_json(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._sanitize_json(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._sanitize_json(v) for v in data]
        if hasattr(data, "isoformat"):
            return data.isoformat()
        if hasattr(data, "__str__"): 
             # For UUIDs or other objects
             return str(data)
        return data

    async def _log_device_change(
        self,
        *,
        device_id: int,
        change_type: str,
        change_description: str,
        changed_by: str,
        old_values: Optional[dict],
        new_values: Optional[dict],
    ) -> None:
        try:
            old_val_safe = self._sanitize_json(old_values) if old_values else None
            new_val_safe = self._sanitize_json(new_values) if new_values else None
            
            await DeviceChangeLog.create(
                device_id=device_id,
                change_type=change_type,
                change_description=change_description,
                changed_by=changed_by,
                old_values=old_val_safe,
                new_values=new_val_safe
            )
        except Exception as e:
            logger.error(f"写入设备审计日志失败: {e}", exc_info=True)

device_service = DeviceService()
