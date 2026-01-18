import logging
import json
import hashlib
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.models.orm.device import NetworkDevice
from app.models.orm.interface import DeviceInterface
from app.models.orm.vlan import DeviceVlan
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

    async def _get_device_driver(self, device: NetworkDevice) -> HuaweiDevice:
        """获取设备驱动实例"""
        # 简化版：目前假设都是 Huawei 设备，且凭证存储在 device 表中
        # 实际场景可能需要 DeviceDriverFactory
        device_info = {
            "id": device.id,
            "ipv4": device.ipv4,
            "device_type": "huawei",
            "host": device.ipv4,
            "port": device.ssh_port,
            "username": device.user_name,
            "password": device.password,
            "timeout": 10,
        }
        return HuaweiDevice(device_info)

    async def sync_device_resources(self, device_id: int):
        """
        同步设备网络资源 (接口/路由/VLAN)
        1. 采集数据
        2. 更新 Redis 缓存
        3. 比对 Hash，如有变更则落库
        """
        device = await NetworkDevice.get_or_none(id=device_id)
        if not device:
            logger.warning(f"Device {device_id} not found")
            return

        logger.info(f"Start syncing resources for device {device.device_name} ({device.ipv4})")
        driver = await self._get_device_driver(device)
        
        try:
            # 1. 并发采集
            # 注意：Netmiko 是同步库封装的异步，并发可能受限于连接数，但在 async 框架下并发调用是个好习惯
            # 但同一个 SSH 连接通常不支持并发命令，这里需确认 driver 实现是否支持
            # 这里的 collect 方法是 async 的，但底层 send_command 通常需要排队
            # 简单起见，顺序调用，或由 driver 内部锁控制
            
            interfaces = await driver.collect_interfaces()
            routes = await driver.collect_routes()
            vlans = await driver.collect_vlans()
            
            # 2. 更新 Redis 缓存
            redis = redis_manager.get_client()
            pipe = redis.pipeline()
            
            # 设置 1 小时过期，保证数据鲜活
            ttl = 3600 
            
            key_base = f"device:{device_id}"
            
            if interfaces:
                pipe.set(f"{key_base}:interfaces", json.dumps(interfaces), ex=ttl)
            if routes:
                pipe.set(f"{key_base}:routes", json.dumps(routes), ex=ttl)
            if vlans:
                pipe.set(f"{key_base}:vlans", json.dumps(vlans), ex=ttl)
                
            await pipe.execute()
            
            # 3. DB 持久化 (Diff 策略)
            await self._persist_if_changed(device, interfaces, routes, vlans)
            
            # 4. 发布通知 (可选)
            await redis.publish(f"device:resource:update", json.dumps({"device_id": device_id}))
            
            logger.info(f"Sync resources for device {device_id} completed")
            
        except Exception as e:
            logger.error(f"Sync resources failed for device {device_id}: {e}", exc_info=True)

    async def _persist_if_changed(
        self, 
        device: NetworkDevice, 
        interfaces: List[Dict], 
        routes: List[Dict], 
        vlans: List[Dict]
    ):
        """比对 Hash 并持久化变更"""
        
        # 获取旧 Hash
        current_hashes = device.resource_hash or {}
        new_hashes = current_hashes.copy()
        
        has_change = False
        
        # --- Interfaces ---
        if_hash = self._calculate_hash(interfaces)
        if if_hash != current_hashes.get("interfaces"):
            logger.info(f"Device {device.id} interfaces changed, updating DB...")
            # 全量覆盖策略 (简单但有效)
            # 先清空旧数据 (Transaction 更好，这里简化)
            # 或者使用 update_or_create
            await DeviceInterface.filter(device_id=device.id).delete()
            
            objs = []
            for item in interfaces:
                objs.append(DeviceInterface(
                    device_id=device.id,
                    name=item.get("name"),
                    phy_state=item.get("phy_state"),
                    protocol_state=item.get("protocol_state"),
                    in_uti=item.get("in_uti"),
                    out_uti=item.get("out_uti"),
                    in_errors=item.get("in_errors"),
                    out_errors=item.get("out_errors"),
                    # ip/mac 等字段如果解析出来可以填入
                ))
            if objs:
                await DeviceInterface.bulk_create(objs)
            
            new_hashes["interfaces"] = if_hash
            has_change = True

        # --- VLANs ---
        vlan_hash = self._calculate_hash(vlans)
        if vlan_hash != current_hashes.get("vlans"):
            logger.info(f"Device {device.id} VLANs changed, updating DB...")
            await DeviceVlan.filter(device_id=device.id).delete()
            
            objs = []
            for item in vlans:
                objs.append(DeviceVlan(
                    device_id=device.id,
                    vlan_id=int(item.get("vlan_id", 0)),
                    type=item.get("type"),
                    status=item.get("status"),
                    mac_learning=item.get("mac_learning"),
                    ports=item.get("ports", [])
                ))
            if objs:
                await DeviceVlan.bulk_create(objs)
                
            new_hashes["vlans"] = vlan_hash
            has_change = True

        # --- Routes ---
        # 路由表通常较大，且只存 JSON
        route_hash = self._calculate_hash(routes)
        if route_hash != current_hashes.get("routes"):
            logger.info(f"Device {device.id} routing table changed, updating DB...")
            device.routing_table = routes
            device.last_routing_update = datetime.now()
            
            new_hashes["routes"] = route_hash
            has_change = True

        # 保存设备元数据变更
        if has_change:
            device.resource_hash = new_hashes
            await device.save()

    async def get_interfaces(self, device_id: int) -> List[Dict]:
        """优先查 Redis，兜底查 DB"""
        redis = redis_manager.get_client()
        cache = await redis.get(f"device:{device_id}:interfaces")
        if cache:
            return json.loads(cache)
        
        # DB Fallback
        items = await DeviceInterface.filter(device_id=device_id).all()
        return [dict(item) for item in items] # Simple dict conv

    async def get_vlans(self, device_id: int) -> List[Dict]:
        redis = redis_manager.get_client()
        cache = await redis.get(f"device:{device_id}:vlans")
        if cache:
            return json.loads(cache)
            
        items = await DeviceVlan.filter(device_id=device_id).all()
        # JSONField might need handling depending on Tortoise version
        return [
            {
                "vlan_id": item.vlan_id,
                "type": item.type,
                "status": item.status,
                "ports": item.ports,
                "mac_learning": item.mac_learning
            } for item in items
        ]

    async def get_routes(self, device_id: int) -> List[Dict]:
        redis = redis_manager.get_client()
        cache = await redis.get(f"device:{device_id}:routes")
        if cache:
            return json.loads(cache)
            
        device = await NetworkDevice.get_or_none(id=device_id)
        if device:
            return device.routing_table or []
        return []

network_resource_service = NetworkResourceService()
