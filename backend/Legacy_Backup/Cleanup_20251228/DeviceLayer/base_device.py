import asyncio
import logging
from netmiko import ConnectHandler
from typing import Dict, Optional, Any

# 使用专门的 DeviceLayer logger
logger = logging.getLogger("DeviceLayer.BaseDevice")    

class BaseDevice:
    def __init__(self, device_info: Dict):
        self.device_id = device_info['id']
        self.ip = str(device_info['ipv4'])
        self.username = device_info.get('user_name', 'root')
        self.password = device_info.get('password', 'password')
        self.port = device_info.get('port', 22)
        # 默认设备类型，子类可以覆盖
        self.device_type = 'linux' 
        # 默认采集间隔 (秒)，子类可以覆盖
        self.interval = 60
        # 在线监测间隔 (秒)，用于快速检测设备状态
        self.monitor_interval = 10
        
        self.connection = None
        self.connected = False
        self._lock = asyncio.Lock()
        
        # 静态信息（一次性采集的数据）
        self.static_info = {}
        # 上次采集时间
        self.last_collect_time = 0

    async def connect(self) -> bool:
        """建立 SSH 连接"""
        if self.connected and self.check_connection():
            return True
            
        async with self._lock:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._connect_sync)
                self.connected = True
                logger.info(f"已连接到设备 {self.ip}")
                return True
            except Exception as e:
                logger.error(f"连接设备 {self.ip} 失败: {e}")
                self.connected = False
                return False

    def _connect_sync(self):
        # 增加 keepalive 配置
        device_params = {
            'device_type': self.device_type,
            'host': self.ip,
            'username': self.username,
            'password': self.password,
            'port': self.port,
            'timeout': 10,
            # 'global_delay_factor': 2,
            # Netmiko keepalive settings (应用层 Keepalive，我们禁用它，改用 Transport 层)
            # 'keepalive': 10, 
        }
        self.connection = ConnectHandler(**device_params)
        
        # 配置 Paramiko Transport 层 Keepalive
        # 注意：在某些设备（如 eNSP 模拟器）上，Transport Keepalive 可能会导致连接不稳定（误判断开）
        # 如果发现频繁断连，请注释掉下面这行
        # if self.connection and self.connection.remote_conn:
        #     transport = self.connection.remote_conn.transport
        #     transport.set_keepalive(5)

    def check_connection(self) -> bool:
        """检查连接状态"""
        if self.connection:
            try:
                # 回退到最稳定的方案：向通道写入一个回车符
                # 只要 TCP 连接正常，写入操作会立即成功（写入缓冲区）
                # 如果 TCP 连接已断开（收到 RST 或 FIN），写入会抛出异常
                self.connection.write_channel('\n')
                return True
            except Exception as e:
                # 捕获所有异常，确保不会崩溃
                # logger.warning(f"设备 {self.ip} 连接检查异常: {e}")
                self.connected = False
                return False
        self.connected = False
        return False

    async def check_online(self) -> bool:
        """快速检测在线状态（不采集数据）"""
        if not self.connected:
            return await self.connect()
        
        # 简单的 write_channel 操作非常快，通常不需要 run_in_executor，
        # 但为了保险起见，避免任何潜在的阻塞，保持异步调用
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check_connection)

    async def disconnect(self):
        """断开连接"""
        if self.connection:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.connection.disconnect)
            except:
                pass
            self.connection = None
        self.connected = False

    async def send_command(self, cmd: str) -> str:
        """发送命令并返回结果"""
        # 尝试自动重连
        if not await self.connect():
             # 如果重连失败，抛出异常或返回空
             # 这里抛出异常，让上层捕获并处理离线状态
            raise ConnectionError(f"无法连接到 {self.ip}")
            
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_command_sync, cmd)

    def _send_command_sync(self, cmd: str) -> str:
        logger.debug(f"设备 {self.ip} 执行命令: {cmd}")
        try:
            # netmiko 的 send_command 自动处理回显
            output = self.connection.send_command(cmd)
            
            if output:
                logger.debug(f"设备 {self.ip} 命令返回:\n{output.strip()}")
            else:
                logger.debug(f"设备 {self.ip} 命令无返回")

            return output
        except Exception as e:
            if cmd.strip():
                logger.error(f"设备 {self.ip} 执行命令出错: {e}")
            
            # 遇到命令执行错误（特别是 EOFError, SocketError），标记为断开
            if self.connected:
                logger.warning(f"设备 {self.ip} 连接因命令执行错误而断开")
            
            self.connected = False
            # 尝试清理连接对象
            try:
                self.connection.disconnect()
            except:
                pass
            self.connection = None
            return ""

    async def collect_status(self) -> Dict[str, Any]:
        """采集设备状态（需子类实现）"""
        raise NotImplementedError

    async def collect_once(self) -> Dict[str, Any]:
        """连接后执行一次的采集任务（需子类实现）"""
        return {}
