import logging
import json
import hashlib
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from tortoise.exceptions import ConfigurationError
from app.models.orm.device import NetworkDevice
from app.drivers.netmiko_driver import HuaweiDevice
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)

class NetworkResourceService:
    """
    网络资源服务
    负责接口、路由、VLAN 等深度网络信息的采集、缓存(Redis)与持久化(DB)
    """

    def _calculate_hash(self, data: Any) -> str:
        """计算数据的 MD5 指纹"""
        s = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(s.encode('utf-8')).hexdigest()

    def _build_ws_resources_payload(self, device_id: int, resources: List[str], data: Dict[str, Any]) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
        for k, v in (data or {}).items():
            if v is not None:
                clean[str(k)] = v
        return {
            "type": "resources_updated",
            "device_id": int(device_id),
            "resources": [str(x) for x in (resources or [])],
            "data": clean,
        }

    async def _get_device_driver(self, device: NetworkDevice) -> HuaweiDevice:
        """获取设备驱动实例"""
        # 简化版：目前假设都是 Huawei 设备，且凭证存储在 device 表中
        # 实际场景可能需要 DeviceDriverFactory
        device_info = {
            "id": device.id,
            "device_name": device.device_name,
            "ipv4": device.ipv4,
            "device_type": "huawei",
            "host": device.ipv4,
            "ssh_port": device.ssh_port,
            "port": device.ssh_port,
            "user_name": device.user_name,
            "username": device.user_name,
            "password": device.password,
            "timeout": 10,
        }
        return HuaweiDevice(device_info)

    def _resource_key(self, device_id: int, name: str) -> str:
        return f"device:{int(device_id)}:{str(name).strip()}"

    def _resource_last_key(self, device_id: int, name: str) -> str:
        return f"{self._resource_key(device_id, name)}:last"

    def _resource_meta_key(self, device_id: int) -> str:
        return f"device:{int(device_id)}:resources:meta"

    async def _load_meta(self, redis, device_id: int) -> Dict[str, Any]:
        try:
            raw = await redis.get(self._resource_meta_key(int(device_id)))
            if not raw:
                return {}
            meta = json.loads(raw)
            return meta if isinstance(meta, dict) else {}
        except Exception:
            return {}

    async def _save_meta(self, redis, device_id: int, meta: Dict[str, Any]) -> None:
        try:
            await redis.set(self._resource_meta_key(int(device_id)), json.dumps(meta, ensure_ascii=False))
        except Exception:
            return

    async def _mark_success(self, redis, device_id: int, resources: List[str]) -> None:
        meta = await self._load_meta(redis, int(device_id))
        now = datetime.now(timezone.utc).isoformat()
        for name in resources:
            k = str(name).strip()
            if not k:
                continue
            cur = meta.get(k)
            if not isinstance(cur, dict):
                cur = {}
            cur["last_success_at"] = now
            cur.pop("last_error", None)
            cur.pop("last_error_at", None)
            meta[k] = cur
        await self._save_meta(redis, int(device_id), meta)

    async def _mark_error(self, redis, device_id: int, resources: List[str], error: str) -> None:
        meta = await self._load_meta(redis, int(device_id))
        now = datetime.now(timezone.utc).isoformat()
        msg = str(error or "").strip()
        for name in resources:
            k = str(name).strip()
            if not k:
                continue
            cur = meta.get(k)
            if not isinstance(cur, dict):
                cur = {}
            cur["last_error"] = msg
            cur["last_error_at"] = now
            meta[k] = cur
        await self._save_meta(redis, int(device_id), meta)

    async def sync_device_interfaces_brief(self, device_id: int) -> None:
        await self.sync_device_resources(int(device_id), resources=["interfaces"])

    async def sync_device_interfaces_slot_detailed(self, device_id: int, slot_id: int = 0) -> None:
        did = int(device_id)
        sid = int(slot_id)
        if sid < 0:
            sid = 0

        try:
            device = await NetworkDevice.get_or_none(id=did)
        except ConfigurationError:
            return
        if not device:
            logger.warning(f"Device {did} not found")
            return

        logger.info(f"巡检了设备 {device.device_name} ({device.ipv4}) 的接口详细信息 (Slot {sid})")
        driver = await self._get_device_driver(device)
        try:
            items = await driver.collect_interfaces_detailed(slot_id=sid)
            if items is None:
                redis = redis_manager.get_client()
                await self._mark_error(redis, did, [f"interfaces_slot{sid}_detailed"], "采集失败")
                return

            redis = redis_manager.get_client()
            ttl = 3600
            key = self._resource_key(did, f"interfaces_slot{sid}_detailed")
            last_key = self._resource_last_key(did, f"interfaces_slot{sid}_detailed")
            await redis.set(key, json.dumps(items, ensure_ascii=False), ex=ttl)
            await redis.set(last_key, json.dumps(items, ensure_ascii=False))
            await redis.publish(
                "device:resource:update",
                json.dumps({"device_id": did, "resources": [f"interfaces_slot{sid}_detailed"]}),
            )
            await redis.publish(
                f"ws:devices:resources:{did}",
                json.dumps(
                    self._build_ws_resources_payload(
                        did,
                        [f"interfaces_slot{sid}_detailed"],
                        {f"interfaces_slot{sid}_detailed": items},
                    ),
                    ensure_ascii=False,
                ),
            )
            await self._mark_success(redis, did, [f"interfaces_slot{sid}_detailed"])
            logger.info(f"设备 {did} Slot {sid} 接口详细信息巡检完成")
        except Exception as e:
            logger.error(f"设备 {did} Slot {sid} 接口详细信息巡检失败: {e}", exc_info=True)
            try:
                redis = redis_manager.get_client()
                await self._mark_error(redis, did, [f"interfaces_slot{sid}_detailed"], str(e))
            except Exception:
                pass
        finally:
            try:
                await driver.disconnect()
            except Exception:
                pass

    async def sync_device_resources(self, device_id: int, resources: Optional[List[str]] = None):
        """
        同步设备网络资源 (接口/路由/VLAN)
        1. 采集数据
        2. 更新 Redis 缓存
        3. 比对 Hash，如有变更则落库
        """
        wanted = {str(x).strip().lower() for x in (resources or []) if str(x).strip()}
        if not wanted:
            wanted = {"interfaces", "routes", "vlans", "interfaces_slot0_detailed"}
        wanted = wanted & {"interfaces", "routes", "vlans", "interfaces_slot0_detailed"}
        if not wanted:
            return

        try:
            device = await NetworkDevice.get_or_none(id=device_id)
        except ConfigurationError:
            return
        if not device:
            logger.warning(f"Device {device_id} not found")
            return

        logger.info(f"巡检了设备 {device.device_name} ({device.ipv4}) 的资源: {sorted(wanted)}")
        driver = await self._get_device_driver(device)
        
        try:
            # 1. 并发采集
            # 注意：Netmiko 是同步库封装的异步，并发可能受限于连接数，但在 async 框架下并发调用是个好习惯
            # 但同一个 SSH 连接通常不支持并发命令，这里需确认 driver 实现是否支持
            # 这里的 collect 方法是 async 的，但底层 send_command 通常需要排队
            # 简单起见，顺序调用，或由 driver 内部锁控制
            
            interfaces = None
            routes = None
            vlans = None
            interfaces_slot0_detailed = None
            if "interfaces" in wanted:
                interfaces = await driver.collect_interfaces()
            if "routes" in wanted:
                routes = await driver.collect_routes()
            if "vlans" in wanted:
                vlans = await driver.collect_vlans()
            if "interfaces_slot0_detailed" in wanted:
                interfaces_slot0_detailed = await driver.collect_interfaces_detailed(slot_id=0)
            
            # 2. 更新 Redis 缓存
            redis = redis_manager.get_client()
            pipe = redis.pipeline()
            
            # 设置 1 小时过期，保证数据鲜活
            ttl = 3600 

            success_resources: List[str] = []
            failed_resources: List[str] = []

            if "interfaces" in wanted:
                if interfaces is None:
                    failed_resources.append("interfaces")
                else:
                    success_resources.append("interfaces")
                    key = self._resource_key(device_id, "interfaces")
                    last_key = self._resource_last_key(device_id, "interfaces")
                    payload = json.dumps(interfaces, ensure_ascii=False)
                    pipe.set(key, payload, ex=ttl)
                    pipe.set(last_key, payload)
            if "routes" in wanted:
                if routes is None:
                    failed_resources.append("routes")
                else:
                    success_resources.append("routes")
                    key = self._resource_key(device_id, "routes")
                    last_key = self._resource_last_key(device_id, "routes")
                    payload = json.dumps(routes, ensure_ascii=False)
                    pipe.set(key, payload, ex=ttl)
                    pipe.set(last_key, payload)
            if "vlans" in wanted:
                if vlans is None:
                    failed_resources.append("vlans")
                else:
                    success_resources.append("vlans")
                    key = self._resource_key(device_id, "vlans")
                    last_key = self._resource_last_key(device_id, "vlans")
                    payload = json.dumps(vlans, ensure_ascii=False)
                    pipe.set(key, payload, ex=ttl)
                    pipe.set(last_key, payload)
            if "interfaces_slot0_detailed" in wanted:
                if interfaces_slot0_detailed is None:
                    failed_resources.append("interfaces_slot0_detailed")
                else:
                    success_resources.append("interfaces_slot0_detailed")
                    key = self._resource_key(device_id, "interfaces_slot0_detailed")
                    last_key = self._resource_last_key(device_id, "interfaces_slot0_detailed")
                    payload = json.dumps(interfaces_slot0_detailed, ensure_ascii=False)
                    pipe.set(key, payload, ex=ttl)
                    pipe.set(last_key, payload)
                
            await pipe.execute()
            
            if success_resources:
                await redis.publish(
                    "device:resource:update",
                    json.dumps({"device_id": device_id, "resources": sorted(success_resources)}, ensure_ascii=False),
                )
                await redis.publish(
                    f"ws:devices:resources:{int(device_id)}",
                    json.dumps(
                        self._build_ws_resources_payload(
                            int(device_id),
                            sorted(success_resources),
                            {
                                "interfaces": interfaces if "interfaces" in success_resources else None,
                                "routes": routes if "routes" in success_resources else None,
                                "vlans": vlans if "vlans" in success_resources else None,
                                "interfaces_slot0_detailed": interfaces_slot0_detailed
                                if "interfaces_slot0_detailed" in success_resources
                                else None,
                            },
                        ),
                        ensure_ascii=False,
                    ),
                )
                await self._mark_success(redis, int(device_id), success_resources)

            if failed_resources:
                await self._mark_error(redis, int(device_id), failed_resources, "采集失败")
            
            logger.info(f"设备 {device_id} 资源巡检完成")
            
        except Exception as e:
            logger.error(f"设备 {device_id} 资源巡检失败: {e}", exc_info=True)
            try:
                redis = redis_manager.get_client()
                await self._mark_error(redis, int(device_id), sorted(list(wanted)), str(e))
            except Exception:
                pass
        finally:
            try:
                await driver.disconnect()
            except Exception:
                pass

    async def get_interfaces(self, device_id: int) -> List[Dict]:
        """读取接口列表（Redis）"""
        redis = redis_manager.get_client()
        cache = await redis.get(self._resource_key(int(device_id), "interfaces"))
        if cache:
            return json.loads(cache)
        last_cache = await redis.get(self._resource_last_key(int(device_id), "interfaces"))
        if last_cache:
            return json.loads(last_cache)
        return []

    async def get_interfaces_detailed(self, device_id: int, slot_id: int = 0) -> List[Dict]:
        redis = redis_manager.get_client()
        key = self._resource_key(int(device_id), f"interfaces_slot{int(slot_id)}_detailed")
        cache = await redis.get(key)
        if cache:
            return json.loads(cache)
        last_cache = await redis.get(self._resource_last_key(int(device_id), f"interfaces_slot{int(slot_id)}_detailed"))
        if last_cache:
            return json.loads(last_cache)
        return []
    async def get_vlans(self, device_id: int) -> List[Dict]:
        redis = redis_manager.get_client()
        cache = await redis.get(self._resource_key(int(device_id), "vlans"))
        if cache:
            return json.loads(cache)
        last_cache = await redis.get(self._resource_last_key(int(device_id), "vlans"))
        if last_cache:
            return json.loads(last_cache)
        return []

    async def get_routes(self, device_id: int) -> List[Dict]:
        redis = redis_manager.get_client()
        cache = await redis.get(self._resource_key(int(device_id), "routes"))
        if cache:
            return json.loads(cache)
        last_cache = await redis.get(self._resource_last_key(int(device_id), "routes"))
        if last_cache:
            return json.loads(last_cache)
        return []

network_resource_service = NetworkResourceService()
