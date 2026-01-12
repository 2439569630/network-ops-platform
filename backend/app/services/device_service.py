
import asyncio
import json
import logging
import time
from typing import List, Optional, Dict
from fastapi import HTTPException
from app.core.database import db
from app.core.redis import redis_manager
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.drivers.factory import create_device
from app.workers.monitor.manager import MonitorManager
from netmiko import ConnectHandler

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
    _deleted_at_capable: Optional[bool] = None
    _deleted_at_checked_at: float = 0.0
    _ssh_audit_table_ready: Optional[bool] = None
    _ssh_audit_table_checked_at: float = 0.0

    async def _has_deleted_at(self) -> bool:
        now = time.time()
        if self._deleted_at_capable is not None and now - float(self._deleted_at_checked_at or 0.0) < 60:
            return bool(self._deleted_at_capable)
        try:
            exists = await db.fetch_val(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'network_devices'
                      AND column_name = 'deleted_at'
                )
                """
            )
            self._deleted_at_capable = bool(exists)
        except Exception:
            self._deleted_at_capable = False
        self._deleted_at_checked_at = now
        return bool(self._deleted_at_capable)

    async def has_deleted_at(self) -> bool:
        return await self._has_deleted_at()

    async def _ensure_ssh_command_audit_table(self) -> bool:
        now = time.time()
        if self._ssh_audit_table_ready is not None and now - float(self._ssh_audit_table_checked_at or 0.0) < 60:
            return bool(self._ssh_audit_table_ready)
        self._ssh_audit_table_checked_at = now
        try:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ssh_command_audit_log (
                    id BIGSERIAL PRIMARY KEY,
                    device_id INTEGER NOT NULL,
                    device_ip TEXT NOT NULL,
                    command TEXT NOT NULL,
                    executed_by TEXT NOT NULL,
                    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ssh_command_audit_log_device_time
                ON ssh_command_audit_log (device_id, executed_at DESC, id DESC)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ssh_command_audit_log_executed_by
                ON ssh_command_audit_log (executed_by)
                """
            )
            self._ssh_audit_table_ready = True
            return True
        except Exception as e:
            logger.error(f"初始化 SSH 命令审计表失败: {e}", exc_info=True)
            self._ssh_audit_table_ready = False
            return False

    async def ensure_ssh_command_audit_table(self) -> bool:
        return await self._ensure_ssh_command_audit_table()

    async def get_device_list(self, type_code: int = 0, search_query: str = None) -> List[dict]:
        logger.info(f"Start get_device_list: type={type_code}, search={search_query}")
        normalized_search = str(search_query or "").strip()

        def _type_match(value: str) -> bool:
            s = str(value or "").strip().lower()
            if type_code == 1:
                return s in {"router", "路由器", "huawei"}
            if type_code == 2:
                return s in {"switch", "交换机"}
            if type_code == 3:
                return s in {"firewall", "防火墙"}
            if type_code == 4:
                return s in {"server", "服务器", "linux"}
            return True

        redis_client = None
        try:
            redis_client = redis_manager.get_client()
        except Exception as e:
            logger.error(f"Redis Connection Error: {e}", exc_info=True)

        result = None
        if redis_client:
            try:
                cached = await redis_client.get("cache:device_list:v1")
                if cached:
                    parsed = json.loads(cached)
                    if isinstance(parsed, list):
                        rows = [x for x in parsed if isinstance(x, dict)]
                        if type_code:
                            rows = [r for r in rows if _type_match(r.get("device_type"))]
                        if normalized_search:
                            q = normalized_search.lower()
                            rows = [
                                r
                                for r in rows
                                if q in str(r.get("device_name") or "").lower()
                                or q in str(r.get("ipv4") or "").lower()
                                or q in str(r.get("location") or "").lower()
                            ]
                        result = rows
            except Exception as e:
                logger.error(f"Read device list cache error: {e}", exc_info=True)
                result = None

        if result is None:
            sql = """
                SELECT 
                    nd.id,
                    nd.device_name,
                    nd.user_name,
                    nd.ipv4,
                    nd.ipv6,
                    nd.mac,
                    nd.online_status,
                    nd.device_type,
                    nd.location,
                    nd.ssh_port,
                    nd.created_by,
                    u.username AS created_by_name
                FROM network_devices nd
                LEFT JOIN users u ON u.id::text = nd.created_by
            """

            where_clauses = []
            params = []
            param_idx = 1
            where_clauses.append("COALESCE(nd.is_active, true) = true")
            if await self._has_deleted_at():
                where_clauses.append("nd.deleted_at IS NULL")

            if type_code == 1:  # Router
                where_clauses.append("nd.device_type IN ('router', '路由器', 'huawei')")
            elif type_code == 2:  # Switch
                where_clauses.append("nd.device_type IN ('switch', '交换机')")
            elif type_code == 3:  # Firewall
                where_clauses.append("nd.device_type IN ('firewall', '防火墙')")
            elif type_code == 4:  # Server
                where_clauses.append("nd.device_type IN ('server', '服务器', 'linux')")

            if normalized_search:
                where_clauses.append(
                    f"(nd.device_name ILIKE ${param_idx} OR nd.ipv4::text ILIKE ${param_idx} OR nd.location ILIKE ${param_idx})"
                )
                params.append(f"%{normalized_search}%")
                param_idx += 1

            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)

            try:
                logger.info(f"Executing DB query: {sql} params={params}")
                result = await db.fetch_all(sql, *params)
                logger.info(f"DB query result count: {len(result) if result else 0}")
                if redis_client and not normalized_search and type_code == 0 and result:
                    try:
                        payload = []
                        for r in result:
                            row = dict(r)
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
                        await redis_client.set(
                            "cache:device_list:v1",
                            json.dumps(payload, ensure_ascii=False),
                            ex=120,
                        )
                    except Exception as e:
                        logger.error(f"Write device list cache error: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"DB Fetch Error: {e}", exc_info=True)
                return []
        
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
                            "ipv4": str(row["ipv4"]) if row["ipv4"] else "",
                            "ipv6": str(row["ipv6"]) if row["ipv6"] else "",
                            "mac": str(row["mac"]) if row["mac"] else "",
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
        # 检查IP是否已存在
        check_sql = "SELECT id FROM network_devices WHERE ipv4 = $1"
        exists = await db.fetch_val(check_sql, device.ipv4)
        if exists:
            raise ValueError("该IP地址已存在")

        sql = """
            INSERT INTO network_devices 
            (device_name, ipv4, ipv6, mac, device_type, user_name, password, location, ssh_port, created_by, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true, NOW(), NOW())
        """
        
        ipv6 = device.ipv6 if device.ipv6 and device.ipv6.strip() else None
        mac = device.mac if device.mac and device.mac.strip() else None
        location = device.location if device.location and device.location.strip() else None

        device_id = await db.fetch_val(
            sql + " RETURNING id",
            device.device_name,
            device.ipv4,
            ipv6,
            mac,
            device.type,
            device.user_name,
            device.password,
            location,
            device.ssh_port,
            str(user_id),
        )

        await self._log_device_change(
            device_id=int(device_id),
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
                "location": location,
                "ssh_port": device.ssh_port,
            },
        )

        # 触发监控加载
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def delete_device(self, device_id: Optional[int] = None, ip: Optional[str] = None, deleted_by: Optional[str] = None):
        has_deleted_at = await self._has_deleted_at()
        target_id = None
        if device_id:
            target_id = int(device_id)
        elif ip:
            target_id = await db.fetch_val("SELECT id FROM network_devices WHERE ipv4 = $1", str(ip))
            target_id = int(target_id) if target_id is not None else None

        old_row = None
        if target_id is not None:
            old_row = await db.fetch_one(
                "SELECT id, device_name, ipv4, ipv6, mac, device_type, location, ssh_port, deleted_at, is_active FROM network_devices WHERE id = $1",
                int(target_id),
            )
        if device_id:
            if has_deleted_at:
                sql = "UPDATE network_devices SET is_active = false, deleted_at = NOW(), updated_at = NOW(), updated_by = $2 WHERE id = $1"
            else:
                sql = "UPDATE network_devices SET is_active = false, updated_at = NOW(), updated_by = $2 WHERE id = $1"
            await db.execute(sql, int(device_id), str(deleted_by or ""))
        elif ip:
            if has_deleted_at:
                sql = "UPDATE network_devices SET is_active = false, deleted_at = NOW(), updated_at = NOW(), updated_by = $2 WHERE ipv4 = $1"
            else:
                sql = "UPDATE network_devices SET is_active = false, updated_at = NOW(), updated_by = $2 WHERE ipv4 = $1"
            await db.execute(sql, str(ip), str(deleted_by or ""))
        else:
             raise ValueError("必须提供设备ID或IP地址")

        if target_id is not None:
            await self._log_device_change(
                device_id=int(target_id),
                change_type="delete",
                change_description="删除设备(移入回收站)",
                changed_by=str(deleted_by or ""),
                old_values=dict(old_row) if old_row else None,
                new_values={"deleted_at": "NOW()", "is_active": False},
            )
             
        # 触发监控加载
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def get_deleted_devices(self) -> List[dict]:
        has_deleted_at = await self._has_deleted_at()
        if has_deleted_at:
            rows = await db.fetch_all(
                """
                SELECT id, device_name, ipv4, device_type, location, ssh_port, deleted_at, updated_by AS deleted_by
                FROM network_devices
                WHERE deleted_at IS NOT NULL
                ORDER BY deleted_at DESC NULLS LAST, id DESC
                """
            )
        else:
            rows = await db.fetch_all(
                """
                SELECT id, device_name, ipv4, device_type, location, ssh_port, updated_at AS deleted_at, updated_by AS deleted_by
                FROM network_devices
                WHERE COALESCE(is_active, true) = false
                ORDER BY updated_at DESC NULLS LAST, id DESC
                """
            )
        return [dict(r) for r in (rows or [])]

    async def restore_device(self, device_id: int, restored_by: Optional[str] = None) -> None:
        has_deleted_at = await self._has_deleted_at()
        old_row = await db.fetch_one(
            "SELECT id, device_name, ipv4, ipv6, mac, device_type, location, ssh_port, deleted_at, is_active FROM network_devices WHERE id = $1",
            int(device_id),
        )
        if has_deleted_at:
            sql = "UPDATE network_devices SET is_active = true, deleted_at = NULL, updated_at = NOW(), updated_by = $2 WHERE id = $1"
        else:
            sql = "UPDATE network_devices SET is_active = true, updated_at = NOW(), updated_by = $2 WHERE id = $1"
        await db.execute(sql, int(device_id), str(restored_by or ""))

        await self._log_device_change(
            device_id=int(device_id),
            change_type="restore",
            change_description="从回收站恢复设备",
            changed_by=str(restored_by or ""),
            old_values=dict(old_row) if old_row else None,
            new_values={"deleted_at": None, "is_active": True},
        )
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def purge_device(self, device_id: int) -> None:
        old_row = await db.fetch_one(
            "SELECT id, device_name, ipv4, ipv6, mac, device_type, location, ssh_port, deleted_at, is_active FROM network_devices WHERE id = $1",
            int(device_id),
        )
        await db.execute("DELETE FROM network_devices WHERE id = $1", int(device_id))
        await self._log_device_change(
            device_id=int(device_id),
            change_type="purge",
            change_description="从回收站彻底删除设备",
            changed_by="",
            old_values=dict(old_row) if old_row else None,
            new_values=None,
        )
        try:
            monitor = MonitorManager()
            await monitor.load_devices()
        except Exception as e:
            logger.error(f"触发监控加载失败: {e}")

    async def update_device(self, device_id: int, patch: DeviceUpdate, updated_by: Optional[str] = None) -> None:
        old_row = await db.fetch_one(
            "SELECT id, device_name, ipv4, ipv6, mac, device_type, location, ssh_port, deleted_at, is_active FROM network_devices WHERE id = $1",
            int(device_id),
        )
        fields = []
        values = []
        idx = 1

        if patch.device_name is not None:
            fields.append(f"device_name = ${idx}")
            values.append(str(patch.device_name))
            idx += 1
        if patch.location is not None:
            fields.append(f"location = ${idx}")
            values.append(str(patch.location))
            idx += 1
        if getattr(patch, "type", None) is not None:
            fields.append(f"device_type = ${idx}")
            values.append(str(getattr(patch, "type")))
            idx += 1
        if getattr(patch, "ssh_port", None) is not None:
            fields.append(f"ssh_port = ${idx}")
            try:
                values.append(int(getattr(patch, "ssh_port")))
            except Exception:
                values.append(22)
            idx += 1

        if not fields:
            return

        fields.append("updated_at = NOW()")
        fields.append(f"updated_by = ${idx}")
        values.append(str(updated_by or ""))
        idx += 1

        sql = f"UPDATE network_devices SET {', '.join(fields)} WHERE id = ${idx}"
        values.append(int(device_id))
        await db.execute(sql, *values)

        new_row = await db.fetch_one(
            "SELECT id, device_name, ipv4, ipv6, mac, device_type, location, ssh_port, deleted_at, is_active FROM network_devices WHERE id = $1",
            int(device_id),
        )
        await self._log_device_change(
            device_id=int(device_id),
            change_type="update",
            change_description="更新设备信息",
            changed_by=str(updated_by or ""),
            old_values=dict(old_row) if old_row else None,
            new_values=dict(new_row) if new_row else None,
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
        if not await self._ensure_ssh_command_audit_table():
            return
        try:
            await db.execute(
                """
                INSERT INTO ssh_command_audit_log (device_id, device_ip, command, executed_by, executed_at)
                VALUES ($1, $2, $3, $4, NOW())
                """,
                int(device_id),
                str(device_ip or ""),
                cmd,
                str(executed_by or ""),
            )
        except Exception as e:
            logger.error(f"写入 SSH 命令审计失败: {e}", exc_info=True)

    async def get_ssh_command_audit_logs(self, device_id: int, page: int = 1, page_size: int = 50) -> dict:
        if not await self._ensure_ssh_command_audit_table():
            return {"items": [], "total": 0, "page": 1, "page_size": int(max(1, min(200, int(page_size or 50))))}
        p = max(1, int(page or 1))
        ps = max(1, min(200, int(page_size or 50)))
        offset = (p - 1) * ps
        total = await db.fetch_val("SELECT COUNT(1) FROM ssh_command_audit_log WHERE device_id = $1", int(device_id))
        rows = await db.fetch_all(
            """
            SELECT
                l.id,
                l.device_id,
                l.device_ip,
                l.command,
                l.executed_by,
                u.username AS executed_by_name,
                l.executed_at
            FROM ssh_command_audit_log l
            LEFT JOIN users u ON u.id::text = l.executed_by
            WHERE l.device_id = $1
            ORDER BY l.executed_at DESC NULLS LAST, l.id DESC
            LIMIT $2 OFFSET $3
            """,
            int(device_id),
            int(ps),
            int(offset),
        )
        items = []
        for r in rows or []:
            d = dict(r)
            d["executed_by"] = str(d.get("executed_by") or "")
            d["executed_by_name"] = str(d.get("executed_by_name") or "")
            items.append(d)
        return {"items": items, "total": int(total or 0), "page": p, "page_size": ps}

    async def get_device_change_logs(self, device_id: int, page: int = 1, page_size: int = 50) -> dict:
        p = max(1, int(page or 1))
        ps = max(1, min(200, int(page_size or 50)))
        offset = (p - 1) * ps
        total = await db.fetch_val("SELECT COUNT(1) FROM device_change_log WHERE device_id = $1", int(device_id))
        rows = await db.fetch_all(
            """
            SELECT
                l.id,
                l.device_id,
                l.change_type,
                l.change_description,
                l.changed_by,
                u.username AS changed_by_name,
                l.changed_at,
                l.old_values,
                l.new_values
            FROM device_change_log l
            LEFT JOIN users u ON u.id::text = l.changed_by
            WHERE l.device_id = $1
            ORDER BY l.changed_at DESC NULLS LAST, l.id DESC
            LIMIT $2 OFFSET $3
            """,
            int(device_id),
            int(ps),
            int(offset),
        )
        items = []
        for r in rows or []:
            d = dict(r)
            d["changed_by"] = str(d.get("changed_by") or "")
            d["changed_by_name"] = str(d.get("changed_by_name") or "")
            items.append(d)
        return {"items": items, "total": int(total or 0), "page": p, "page_size": ps}

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
            await db.execute(
                """
                INSERT INTO device_change_log
                    (device_id, change_type, change_description, changed_by, changed_at, old_values, new_values)
                VALUES
                    ($1, $2, $3, $4, NOW(), $5::jsonb, $6::jsonb)
                """,
                int(device_id),
                str(change_type),
                str(change_description),
                str(changed_by or ""),
                json.dumps(old_values, ensure_ascii=False, default=str) if old_values is not None else None,
                json.dumps(new_values, ensure_ascii=False, default=str) if new_values is not None else None,
            )
        except Exception as e:
            logger.error(f"写入设备审计日志失败: {e}", exc_info=True)

device_service = DeviceService()
