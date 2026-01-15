
import asyncio
import json
import logging
import time
from typing import List, Optional, Dict, Any
from fastapi import HTTPException
from app.core.database import db
from app.core.redis import redis_manager
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.workers.monitor.manager import MonitorManager
from netmiko import ConnectHandler

# ORM Imports
from app.models.orm.device import NetworkDevice
from app.models.orm.user import User
from app.models.orm.audit import DeviceChangeLog, SshCommandAuditLog
from tortoise.expressions import Q
from tortoise.functions import Count

from app.models.orm.location import LocationNode, LocationNodeDevice

from app.services.location_service import LocationService

logger = logging.getLogger(__name__)

def _parse_percent(value) -> float:
    try:
        s = str(value or "").strip()
        if not s:
            return 0.0
        if s.endswith("%"):
            s = s[:-1].strip()
        return float(s)
    except Exception:
        return 0.0

class DeviceService:

    # Helper to convert ORM object to dict (simple version)
    def _model_to_dict(self, obj: Any) -> Dict[str, Any]:
        if not obj:
            return {}
        # Tortoise models can be converted to dict, but we need to handle serialization
        # This is a basic implementation. Pydantic from_orm is better if available.
        return dict(obj)

    async def has_deleted_at(self) -> bool:
        # With ORM, we assume the model schema is correct. 
        # If the column is missing, it should be added to the DB.
        return True

    async def ensure_ssh_command_audit_table(self) -> bool:
        # Tortoise generate_schemas=True handles table creation usually.
        # But we keep this just in case we need explicit check, or remove it.
        # For now, we assume ORM handles it.
        return True

    async def get_device_list(self, type_code: int = 0, search_query: str = None, location_filter: str = None, location_node_id: int = None) -> List[dict]:
        logger.info(f"Start get_device_list (ORM): type={type_code}, search={search_query}, location={location_filter}, node_id={location_node_id}")
        normalized_search = str(search_query or "").strip()

        # Redis Cache Logic
        redis_client = None
        try:
            redis_client = redis_manager.get_client()
        except Exception as e:
            logger.error(f"Redis Connection Error: {e}", exc_info=True)

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
                created_by_name = user_map.get(int(d.created_by), "") if d.created_by and d.created_by.isdigit() else ""
                
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
                    "online_status": d.online_status,
                    "device_type": d.device_type,
                    "location": loc_name,
                    "ssh_port": d.ssh_port,
                    "created_by": d.created_by,
                    "created_by_name": created_by_name
                })
                
        except Exception as e:
            logger.error(f"ORM Fetch Error: {e}", exc_info=True)
            return []

        # Redis status filling
        data = []
        if result:
            redis_rows = None
            if redis_client:
                try:
                    pipe = redis_client.pipeline()
                    for row in result:
                        device_id = row["id"]
                        redis_key = f"device_status:{device_id}"
                        pipe.hmget(redis_key, "cpu_usage", "memory_usage", "disk_usage", "status")
                    redis_rows = await pipe.execute()
                except Exception as e:
                    logger.error(f"Redis batch get error: {e}", exc_info=True)
                    redis_rows = None

            if not redis_rows or len(redis_rows) != len(result):
                redis_rows = [None] * len(result)

            for row, rvals in zip(result, redis_rows):
                try:
                    cpu_usage = "0%"
                    memory_usage = "0%"
                    disk_usage = "0%"
                    status = "待加载"

                    if isinstance(rvals, (list, tuple)) and len(rvals) >= 4:
                        cpu_v, mem_v, disk_v, st_v = rvals[0], rvals[1], rvals[2], rvals[3]
                        if cpu_v is not None:
                            cpu_usage = f"{_parse_percent(cpu_v)}%"
                        if mem_v is not None:
                            memory_usage = f"{_parse_percent(mem_v)}%"
                        if disk_v is not None:
                            disk_usage = f"{_parse_percent(disk_v)}%"
                        if st_v == "online":
                            status = "在线"
                        elif st_v == "offline":
                            status = "离线"

                    if status == "待加载" and row.get("online_status"):
                        status = "在线"

                    data.append(
                        {
                            "id": row["id"],
                            "device_name": row["device_name"],
                            "user_name": str(row.get("user_name") or ""),
                            "ipv4": row["ipv4"],
                            "ipv6": row["ipv6"],
                            "mac": row["mac"],
                            "status": status,
                            "type": row["device_type"],
                            "location": row["location"],
                            "ssh_port": row["ssh_port"],
                            "cpu_usage": cpu_usage,
                            "memory_usage": memory_usage,
                            "disk_usage": disk_usage,
                            "created_by": str(row.get("created_by") or ""),
                            "created_by_name": str(row.get("created_by_name") or ""),
                            "ops_admin_name": str(row.get("created_by_name") or ""),
                        }
                    )
                except Exception as e:
                    logger.error(f"Row processing error: {e}", exc_info=True)
                    continue
        
        logger.info(f"Returning {len(data)} devices")
        return data

    async def add_device(self, device: DeviceCreate, user_id: int):
        # Check if IP exists
        if await NetworkDevice.filter(ipv4=device.ipv4).exists():
            raise ValueError("该IP地址已存在")

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
            # location=location, # Deprecated
            ssh_port=device.ssh_port,
            created_by=str(user_id),
            is_active=True
        )

        # Handle Location Mapping
        location_name = device.location if device.location and device.location.strip() else None
        if location_name:
            node = await LocationNode.filter(name=location_name).first()
            if node:
                await LocationNodeDevice.create(node_id=node.id, device_id=new_device.id)

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
                "location": location_name,
                "ssh_port": device.ssh_port,
            },
        )

        # Trigger monitor
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def delete_device(self, device_id: Optional[int] = None, ip: Optional[str] = None, deleted_by: Optional[str] = None):
        device = None
        if device_id:
            device = await NetworkDevice.get_or_none(id=device_id)
        elif ip:
            device = await NetworkDevice.get_or_none(ipv4=ip)
        
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
             
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def get_deleted_devices(self) -> List[dict]:
        # ORM query for deleted devices
        devices = await NetworkDevice.filter(deleted_at__isnull=False).order_by("-deleted_at", "-id").all()
        
        result = []
        for d in devices:
            result.append({
                "id": d.id,
                "device_name": d.device_name,
                "ipv4": str(d.ipv4),
                "device_type": d.device_type,
                "location": d.location,
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
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def purge_device(self, device_id: int) -> None:
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
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def update_device(self, device_id: int, patch: DeviceUpdate, updated_by: Optional[str] = None) -> None:
        device = await NetworkDevice.get_or_none(id=device_id)
        if not device:
            return

        old_values = dict(device)
        import datetime

        if patch.device_name is not None:
            device.device_name = patch.device_name
        
        # Location update logic
        if patch.location is not None:
            # device.location = patch.location # Deprecated
            # Update mapping
            loc_name = patch.location.strip()
            if not loc_name:
                # Clear mapping
                await LocationNodeDevice.filter(device_id=device.id).delete()
            else:
                # Update mapping
                node = await LocationNode.filter(name=loc_name).first()
                if node:
                    # Upsert
                    # Check existing
                    mapping = await LocationNodeDevice.filter(device_id=device.id).first()
                    if mapping:
                        mapping.node_id = node.id
                        await mapping.save()
                    else:
                        await LocationNodeDevice.create(node_id=node.id, device_id=device.id)
                else:
                    # If location name provided but not found, maybe ignore or clear?
                    # For safety, if user types unknown location, we might just clear it or keep old?
                    # Assuming frontend sends valid location names from selection.
                    pass

        if getattr(patch, "type", None) is not None:
            device.device_type = getattr(patch, "type")
        if getattr(patch, "ssh_port", None) is not None:
            device.ssh_port = getattr(patch, "ssh_port")

        device.updated_at = datetime.datetime.now()
        device.updated_by = str(updated_by or "")
        
        await device.save()

        
        # Reload to get fresh values if needed, or just use what we set
        new_values = dict(device)

        await self._log_device_change(
            device_id=device.id,
            change_type="update",
            change_description="更新设备信息",
            changed_by=str(updated_by or ""),
            old_values=old_values,
            new_values=new_values,
        )

        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def test_connect(self, device: DeviceCreate):
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
            executed_by_name = user_map.get(int(l.executed_by), "") if l.executed_by and l.executed_by.isdigit() else ""
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
            changed_by_name = user_map.get(int(l.changed_by), "") if l.changed_by and l.changed_by.isdigit() else ""
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
