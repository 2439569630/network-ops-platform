import asyncio
import logging
import time
import threading
from netmiko import ConnectHandler
from typing import Dict, Optional, Any, Callable
from app.drivers.models.status import DeviceStatus, DeviceConfig

# 使用新的 logger 名称
logger = logging.getLogger("app.drivers.base")    

class BaseDevice:
    def __init__(self, device_info: Dict):
        self.device_id = device_info['id']
        self.ip = str(device_info['ipv4'])
        self.config = DeviceConfig.from_device_info(device_info)
        self.username = self.config.username
        self.password = self.config.password
        self.port = self.config.port
        # 默认设备类型，子类可以覆盖
        self.device_type = 'linux' 
        # 默认采集间隔 (秒)，子类可以覆盖
        self.interval = float(self.config.interval or 60)
        # 在线监测间隔 (秒)，用于快速检测设备状态
        self.monitor_interval = float(self.config.monitor_interval or 10)
        
        self.connection = None
        self.connected = False
        self._lock = asyncio.Lock()
        self._shutdown = False
        self._connect_abort = threading.Event()
        
        # 静态信息（一次性采集的数据）
        self.static_info = {}
        # 上次采集时间
        self.last_collect_time = 0
        self.status = DeviceStatus()
        self.offline_fail_threshold = int(self.config.offline_fail_threshold)
        self.recovery_success_threshold = int(self.config.recovery_success_threshold)

        self.last_metrics = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "disk_usage": 0.0,
            "uptime": "",
        }
        self.last_metrics_updated = 0.0
        self.last_heartbeat = 0.0

    @staticmethod
    def _compact_exception_message(e: Exception) -> str:
        try:
            s = str(e) if e is not None else ""
        except Exception:
            return ""
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        first = s.split("\n", 1)[0].strip()
        return first

    @property
    def fsm_state(self) -> str:
        return str(self.status.fsm_state or "")

    @fsm_state.setter
    def fsm_state(self, value: str) -> None:
        self.status.set_fsm(str(value or "").strip() or "init", self.status.fsm_reason)

    @property
    def fsm_reason(self) -> str:
        return str(self.status.fsm_reason or "")

    @fsm_reason.setter
    def fsm_reason(self, value: str) -> None:
        self.status.set_fsm(self.status.fsm_state, str(value or ""))

    @property
    def fsm_updated(self) -> float:
        return float(self.status.fsm_updated or 0.0)

    @fsm_updated.setter
    def fsm_updated(self, value: float) -> None:
        self.status.fsm_updated = float(value or 0.0)

    @property
    def offline_fail_threshold(self) -> int:
        return int(self.status.offline_fail_threshold)

    @offline_fail_threshold.setter
    def offline_fail_threshold(self, value: int) -> None:
        self.status.offline_fail_threshold = int(value or 0)

    @property
    def recovery_success_threshold(self) -> int:
        return int(self.status.recovery_success_threshold)

    @recovery_success_threshold.setter
    def recovery_success_threshold(self, value: int) -> None:
        self.status.recovery_success_threshold = int(value or 0)

    @property
    def consecutive_failures(self) -> int:
        return int(self.status.consecutive_failures)

    @consecutive_failures.setter
    def consecutive_failures(self, value: int) -> None:
        self.status.consecutive_failures = int(value or 0)

    @property
    def consecutive_successes(self) -> int:
        return int(self.status.consecutive_successes)

    @consecutive_successes.setter
    def consecutive_successes(self, value: int) -> None:
        self.status.consecutive_successes = int(value or 0)

    @property
    def state_phase(self) -> str:
        return str(self.status.phase or "")

    @state_phase.setter
    def state_phase(self, value: str) -> None:
        self.status.set_phase(str(value or "").strip() or "unknown", self.status.phase_reason)

    @property
    def state_reason(self) -> str:
        return str(self.status.phase_reason or "")

    @state_reason.setter
    def state_reason(self, value: str) -> None:
        self.status.set_phase(self.status.phase, str(value or ""))

    @property
    def state_updated(self) -> float:
        return float(self.status.phase_updated or 0.0)

    @state_updated.setter
    def state_updated(self, value: float) -> None:
        self.status.phase_updated = float(value or 0.0)

    def set_state_phase(self, phase: str, reason: Optional[str] = None) -> bool:
        return self.status.set_phase(phase, reason)

    def record_success(self) -> bool:
        return bool(self.status.record_success())

    def record_failure(self, reason: Optional[str] = None) -> tuple[bool, bool]:
        return self.status.record_failure(reason)

    def apply_config(self, config: DeviceConfig) -> None:
        self.config = config
        self.username = self.config.username
        self.password = self.config.password
        self.port = self.config.port
        self.interval = float(self.config.interval or self.interval or 60)
        self.monitor_interval = float(self.config.monitor_interval or self.monitor_interval or 10)
        self.offline_fail_threshold = int(self.config.offline_fail_threshold)
        self.recovery_success_threshold = int(self.config.recovery_success_threshold)

    async def connect(self, progress_cb: Optional[Callable[[str, str], Any]] = None) -> bool:
        """建立 SSH 连接"""
        async def _emit_progress(phase: str, reason: str) -> None:
            if not progress_cb:
                return
            try:
                ret = progress_cb(phase, reason)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception:
                return

        if self._shutdown:
            self.connected = False
            return False
        if self.connected and self.check_connection():
            return True
            
        async with self._lock:
            if self._shutdown:
                self.connected = False
                return False
            self._connect_abort.clear()
            try:
                loop = asyncio.get_event_loop()
                max_retries = int(getattr(self.config, "connect_max_retries", 3) or 3)
                if max_retries <= 0:
                    max_retries = 1
                retry_delay = float(getattr(self.config, "connect_retry_delay_seconds", 2.0) or 2.0)
                if retry_delay < 0:
                    retry_delay = 0
                for attempt in range(max_retries):
                    if self._shutdown or self._connect_abort.is_set():
                        self.connected = False
                        return False
                    try:
                        conn = await loop.run_in_executor(None, self._connect_once_sync)
                        if not conn:
                            self.connected = False
                            return False
                        if self._shutdown or self._connect_abort.is_set():
                            try:
                                conn.disconnect()
                            except Exception:
                                pass
                            self.connected = False
                            return False
                        self.connection = conn
                        self.connected = True
                        logger.info(f"已连接到设备 {self.ip}")
                        return True
                    except Exception as e:
                        msg = self._compact_exception_message(e)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"设备 {self.ip} 连接尝试 {attempt + 1}/{max_retries} 失败: {msg}，正在重试..."
                            )
                            await _emit_progress("loading", f"连接尝试 {attempt + 1}/{max_retries} 失败: {msg}，正在重试...")
                            steps = int(retry_delay / 0.1) if retry_delay else 0
                            for _ in range(max(1, steps) if retry_delay else 1):
                                if self._shutdown or self._connect_abort.is_set():
                                    self.connected = False
                                    return False
                                await asyncio.sleep(0.1)
                            continue
                        raise
            except asyncio.CancelledError:
                self._connect_abort.set()
                raise
            except Exception as e:
                # 简化错误日志，只保留关键信息
                error_msg = str(e).split('\n')[0] # 只取第一行错误信息
                logger.error(f"连接设备 {self.ip} 失败: {error_msg}")
                await _emit_progress("failure", f"连接失败: {error_msg}")
                self.connected = False
                return False
                
    def request_shutdown(self) -> None:
        self._shutdown = True
        self._connect_abort.set()

    def _connect_once_sync(self):
        if self._shutdown or self._connect_abort.is_set():
            return None
        # 增加 keepalive 配置
        device_params = {
            'device_type': self.device_type,
            'host': self.ip,
            'username': self.username,
            'password': self.password,
            'port': self.port,
            'timeout': float(getattr(self.config, "connect_timeout", 30.0) or 30.0),
            'auth_timeout': float(getattr(self.config, "auth_timeout", 30.0) or 30.0),
            'global_delay_factor': float(getattr(self.config, "global_delay_factor", 2.0) or 2.0),
            # Netmiko keepalive settings (应用层 Keepalive，我们禁用它，改用 Transport 层)
            # 'keepalive': 10, 
            # 增加 banner_timeout 以解决 SSH banner 读取超时问题
            'banner_timeout': float(getattr(self.config, "banner_timeout", 100.0) or 100.0),
        }
        
        conn = ConnectHandler(**device_params)
        if self._shutdown or self._connect_abort.is_set():
            try:
                conn.disconnect()
            except Exception:
                pass
            return None
        return conn
        
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

    async def check_online(self, progress_cb: Optional[Callable[[str, str], Any]] = None) -> bool:
        """快速检测在线状态（不采集数据）"""
        if not self.connected:
            return await self.connect(progress_cb=progress_cb)
        
        # 简单的 write_channel 操作非常快，通常不需要 run_in_executor，
        # 但为了保险起见，避免任何潜在的阻塞，保持异步调用
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check_connection)

    async def disconnect(self):
        """断开连接"""
        self._connect_abort.set()
        if self.connection:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.connection.disconnect)
            except:
                pass
            self.connection = None
        self.connected = False
        if not self._shutdown:
            self._connect_abort.clear()

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
                logger.error(f"设备 {self.ip} 执行命令出错: {self._compact_exception_message(e)}")
            
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
