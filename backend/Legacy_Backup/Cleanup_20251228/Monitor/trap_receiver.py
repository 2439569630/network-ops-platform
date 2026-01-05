import asyncio
import logging
from pysnmp.entity import engine, config
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.proto.api import v2c
from app.core.redis import redis_manager
from app.core.system_config import SystemConfig
import json
import time

logger = logging.getLogger(__name__)

class TrapReceiver:
    def __init__(self, host='0.0.0.0', port=162):
        self.host = host
        self.port = port
        self.snmp_engine = engine.SnmpEngine()
        self.redis = redis_manager
        self.transport_dispatcher = None

    async def start(self):
        """启动 Trap 接收服务"""
        logger.info(f"启动 SNMP Trap 接收服务监听 {self.host}:{self.port}")
        
        # 配置传输层 (UDP)
        try:
            config.addTransport(
                self.snmp_engine,
                udp.domainName + (1,),
                udp.UdpTransport().openServerMode((self.host, self.port))
            )
        except Exception as e:
            logger.error(f"Trap 服务绑定端口失败 (可能权限不足或端口被占用): {e}")
            return

        # 配置 Community (v1/v2c)
        # 接收所有 Community 为 'public' 的 Trap
        # TODO: 可以从数据库动态加载 Community 列表
        config.addV1System(self.snmp_engine, 'my-area', 'public')

        # 注册回调函数
        ntfrcv.NotificationReceiver(self.snmp_engine, self._trap_callback)

        # 获取底层 Dispatcher
        self.transport_dispatcher = self.snmp_engine.transportDispatcher
        
        # 启动 asyncio job
        # pysnmp 的 asyncio 集成比较特殊，通常通过 runDispatcher() 运行
        # 但我们需要集成到现有的 asyncio loop 中
        # 这里使用 pysnmp 推荐的 asyncio 适配方式，或者简单的 run_in_executor
        
        # 由于 pysnmp 4.4.x 的 asyncio 支持可能需要特定配置，
        # 我们这里使用它的 jobStarted 机制，它会自动挂载到当前的 asyncio loop (如果已配置)
        
        self.transport_dispatcher.jobStarted(1) # 1 means maintain one job

    async def stop(self):
        """停止服务"""
        if self.transport_dispatcher:
            self.transport_dispatcher.jobFinished(1)
            self.transport_dispatcher.closeDispatcher()
        logger.info("SNMP Trap 服务已停止")

    def _trap_callback(self, snmpEngine, stateReference, contextEngineId, contextName,
                       varBinds, cbCtx):
        """
        处理接收到的 Trap 消息
        注意：此回调可能在 pysnmp 的内部循环中执行，需要注意线程安全或异步转换
        """
        try:
            transportDomain, transportAddress = snmpEngine.msgAndPduDsp.getTransportInfo(stateReference)
            src_ip = transportAddress[0]
            
            logger.info(f"收到来自 {src_ip} 的 Trap 消息")
            
            trap_data = {
                "source_ip": src_ip,
                "timestamp": time.time(),
                "oids": []
            }

            for name, val in varBinds:
                oid = name.prettyPrint()
                value = val.prettyPrint()
                trap_data["oids"].append({"oid": oid, "value": value})
                # logger.debug(f"Trap OID: {oid} = {value}")

            # 异步处理：将 Trap 推送到 Redis
            # 由于这是回调函数，不能直接 await，需要 create_task
            asyncio.create_task(self._process_trap(trap_data))

        except Exception as e:
            logger.error(f"Trap 回调处理异常: {e}")

    async def _process_trap(self, data: dict):
        """解析并推送 Trap 数据"""
        try:
            # 1. 解析 Trap 类型 (LinkUp/LinkDown 等)
            # 简单解析：检查 OID 是否包含特定特征
            # LinkDown: 1.3.6.1.6.3.1.1.5.3
            # LinkUp: 1.3.6.1.6.3.1.1.5.4
            
            event_type = "Generic Trap"
            description = "收到未知类型的 SNMP Trap"
            level = "info"
            
            for item in data['oids']:
                oid = item['oid']
                if '1.3.6.1.6.3.1.1.5.3' in oid or 'linkDown' in item['value']:
                    event_type = "Link Down"
                    description = f"接口链路断开 (来自 {data['source_ip']})"
                    level = "error"
                    break
                elif '1.3.6.1.6.3.1.1.5.4' in oid or 'linkUp' in item['value']:
                    event_type = "Link Up"
                    description = f"接口链路恢复 (来自 {data['source_ip']})"
                    level = "success"
                    break
            
            # 2. 构造告警消息
            alert = {
                "type": event_type,
                "description": description,
                "level": level,
                "source": data['source_ip'],
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data['timestamp'])),
                "raw": data
            }
            
            # 3. 推送到 Redis Pub/Sub (供 WebSocket 消费)
            redis_client = self.redis.get_client()
            await redis_client.publish("system_alerts", json.dumps(alert))
            
            # 4. 可选：持久化到数据库 (system_notifications 表)
            # await self._save_to_db(alert)
            
            logger.info(f"Trap 处理完成: {description}")

        except Exception as e:
            logger.error(f"Trap 异步处理失败: {e}")
