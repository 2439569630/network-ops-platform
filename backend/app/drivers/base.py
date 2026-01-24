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
    """
    设备驱动基类
    定义了所有设备驱动通用的接口和状态管理逻辑。
    """
    def __init__(self, device_info: Dict):
        # 设备唯一标识与基础连接信息
        self.device_id = device_info['id']
        self.ip = str(device_info['ipv4'])
        self.device_name = str(device_info.get('device_name', 'Unknown'))
        self.config = DeviceConfig.from_device_info(device_info)
        self.username = self.config.username
        self.password = self.config.password
        self.port = self.config.port
        # 默认设备类型，子类可以覆盖
        self.device_type = 'linux' 
        # 默认采集间隔 (秒)，子类可以覆盖
        try:
            self.interval = float(getattr(self.config, "interval", 60.0))
        except Exception:
            self.interval = 60.0
        # 在线监测间隔 (秒)，用于快速检测设备状态
        try:
            self.monitor_interval = float(getattr(self.config, "monitor_interval", 10.0))
        except Exception:
            self.monitor_interval = 10.0
        self.schedule_rev = 0
        
        self.connection = None
        self.connected = False
        # 用于串行化连接建立/重连，避免并发 connect 导致状态错乱
        self._lock = asyncio.Lock()
        # 关闭标记：用于在监控退出/进程退出时终止连接与重试
        self._shutdown = False
        # 连接中止信号：用于取消连接/断开时快速打断重试流程
        self._connect_abort = threading.Event()
        
        # 静态信息（一次性采集的数据）
        device_type = str(device_info.get("device_type") or "").strip()
        if device_type in {"路由器", "交换机", "huawei"}:
            from app.drivers.models.huawei_runtime import HuaweiDisplayVersionRuntime

            self.static_info = HuaweiDisplayVersionRuntime(raw="")
        else:
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
        self.last_connect_error: Exception | None = None

        self.last_interfaces: list[dict[str, Any]] | None = None
        self.last_interfaces_updated = 0.0
        self.last_interfaces_detailed_by_slot: dict[int, list[dict[str, Any]]] = {}
        self.last_interfaces_detailed_updated_by_slot: dict[int, float] = {}
        self._active_inspection_id: str | None = None
        self._active_inspection_commands: list[str] = []
        self._active_inspection_max_commands: int = 0

    @staticmethod
    def _compact_exception_message(e: Exception) -> str:
        try:
            s = str(e) if e is not None else ""
        except Exception:
            s = ""
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        first = s.split("\n", 1)[0].strip()
        name = type(e).__name__ if e is not None else ""
        if first:
            return f"{name}: {first}" if name and not first.startswith(name) else first
        return name or ""

    @staticmethod
    def _normalize_command_for_log(cmd: str, max_len: int = 120) -> str:
        try:
            s = str(cmd or "")
        except Exception:
            s = ""
        s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        if max_len > 0 and len(s) > max_len:
            return s[: max(1, max_len - 1)] + "…"
        return s

    def begin_inspection(self, inspect_id: str, max_commands: int = 8) -> None:
        self._active_inspection_id = str(inspect_id or "").strip() or None
        self._active_inspection_commands = []
        try:
            self._active_inspection_max_commands = max(0, int(max_commands))
        except Exception:
            self._active_inspection_max_commands = 0

    def end_inspection(self) -> list[str]:
        cmds = list(self._active_inspection_commands or [])
        self._active_inspection_id = None
        self._active_inspection_commands = []
        self._active_inspection_max_commands = 0
        return cmds

    def _record_inspection_command(self, cmd: str) -> None:
        if not self._active_inspection_id:
            return
        max_n = int(self._active_inspection_max_commands or 0)
        if max_n <= 0:
            return
        if len(self._active_inspection_commands) >= max_n:
            return
        c = self._normalize_command_for_log(cmd, max_len=120)
        if c:
            self._active_inspection_commands.append(c)

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

    def record_success(self) -> bool:
        return bool(self.status.record_success())

    def record_failure(self, reason: Optional[str] = None) -> tuple[bool, bool]:
        return self.status.record_failure(reason)

    def apply_config(self, config: DeviceConfig) -> None:
        self.config = config
        self.username = self.config.username
        self.password = self.config.password
        self.port = self.config.port
        try:
            self.interval = float(self.config.interval)
        except Exception:
            pass
        try:
            self.monitor_interval = float(self.config.monitor_interval)
        except Exception:
            pass
        self.offline_fail_threshold = int(self.config.offline_fail_threshold)
        self.recovery_success_threshold = int(self.config.recovery_success_threshold)
        try:
            self.schedule_rev = int(getattr(self, "schedule_rev", 0) or 0) + 1
        except Exception:
            self.schedule_rev = 1

    async def connect(
        self,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
        purpose: str = "startup",
        max_retries: Optional[int] = None,
        retry_delay_seconds: Optional[float] = None,
    ) -> bool:
        """建立 SSH 连接"""
        async def _emit_progress(phase: str, reason: str) -> None:
            # 连接过程中的阶段回调：用于外部实时更新 UI/状态机
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
            # connect 入口用锁保护：同一时间只允许一个协程做真实的 connect/retry
            if self._shutdown:
                self.connected = False
                return False
            self._connect_abort.clear()
            try:
                loop = asyncio.get_event_loop()
                p = str(purpose or "").strip().lower()
                if p not in {"startup", "steady"}:
                    p = "startup"
                max_retries_val = max_retries
                if max_retries_val is None:
                    max_retries_val = int(getattr(self.config, "connect_max_retries", 3) or 3)
                try:
                    max_retries_val = int(max_retries_val)
                except Exception:
                    max_retries_val = 1
                if max_retries_val <= 0:
                    max_retries_val = 1
                retry_delay = retry_delay_seconds
                if retry_delay is None:
                    retry_delay = float(getattr(self.config, "connect_retry_delay_seconds", 2.0) or 2.0)
                try:
                    retry_delay = float(retry_delay)
                except Exception:
                    retry_delay = 0.0
                if retry_delay < 0:
                    retry_delay = 0.0

                if p == "steady":
                    max_retries_val = 1
                    retry_delay = 0.0
                for attempt in range(max_retries_val):
                    if self._shutdown or self._connect_abort.is_set():
                        self.connected = False
                        return False
                    try:
                        # ConnectHandler 是阻塞调用，放到线程池避免卡住事件循环
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
                        self.last_connect_error = None
                        logger.info(f"已连接到设备 {self.device_name}({self.ip})")
                        return True
                    except Exception as e:
                        self.last_connect_error = e
                        msg = self._compact_exception_message(e)
                        if attempt < max_retries_val - 1:
                            level = logging.WARNING if attempt == 0 else logging.DEBUG
                            logger.log(
                                level,
                                f"设备 {self.device_name}({self.ip}) 连接尝试 {attempt + 1}/{max_retries_val} 失败: {msg}，正在重试...",
                            )
                            if attempt == 0:
                                await _emit_progress(
                                    "loading",
                                    f"连接尝试 {attempt + 1}/{max_retries_val} 失败: {msg}，正在重试...",
                                )
                            steps = int(retry_delay / 0.1) if retry_delay else 0
                            for _ in range(max(1, steps) if retry_delay else 1):
                                if self._shutdown or self._connect_abort.is_set():
                                    self.connected = False
                                    return False
                                await asyncio.sleep(0.1)
                            continue
                        raise
            except asyncio.CancelledError:
                # connect 任务被取消时，通知重试流程尽快终止
                self._connect_abort.set()
                raise
            except Exception as e:
                # 简化错误日志，只保留关键信息
                error_msg = self._compact_exception_message(e) or "连接失败"
                self.last_connect_error = e
                logger.error(f"连接设备 {self.device_name}({self.ip}) 失败: {error_msg}")
                await _emit_progress("failure", f"连接失败: {error_msg}")
                self.connected = False
                return False
                
    def request_shutdown(self) -> None:
        self._shutdown = True
        self._connect_abort.set()

    def _connect_once_sync(self):
        if self._shutdown or self._connect_abort.is_set():
            return None
        # 真正的“单次连接”逻辑（同步/阻塞），由 connect() 放入线程池执行
        device_params = {
            'device_type': self.device_type,
            'host': self.ip,
            'username': self.username,
            'password': self.password,
            'port': self.port,
            'timeout': float(getattr(self.config, "connect_timeout", 30.0) or 30.0),
            'conn_timeout': float(getattr(self.config, "connect_timeout", 30.0) or 30.0),
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
                # 这里用“写入回车”来探活：
                # - TCP 正常：写入缓冲立即成功
                # - TCP 已断：写入会抛异常（RST/FIN/通道关闭）
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
            return await self.connect(progress_cb=progress_cb, purpose="steady")
        
        # check_connection 理论上很快，但为避免底层实现偶发阻塞，这里仍放线程池
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check_connection)

    async def disconnect(self):
        """断开连接"""
        self._connect_abort.set()
        if self.connection:
            try:
                loop = asyncio.get_event_loop()
                # disconnect 可能阻塞，同样放线程池执行
                await loop.run_in_executor(None, self.connection.disconnect)
            except Exception:
                pass
            self.connection = None
        self.connected = False
        if not self._shutdown:
            self._connect_abort.clear()

    async def send_command(self, cmd: str) -> str:
        """发送命令并返回结果"""
        try:
            self._record_inspection_command(cmd)
        except Exception:
            pass
        # 尝试自动重连
        if not await self.connect(purpose="steady"):
             # 如果重连失败，抛出异常或返回空
             # 这里抛出异常，让上层捕获并处理离线状态
            raise ConnectionError(f"无法连接到 {self.ip}")
            
        loop = asyncio.get_event_loop()
        # send_command 是阻塞调用，放线程池避免阻塞事件循环
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
            # 命令执行异常时，尝试清理连接对象，让下次 send_command 触发重连
            try:
                self.connection.disconnect()
            except Exception:
                pass
            self.connection = None
            return ""

    async def collect_status(self) -> Dict[str, Any]:
        """采集设备状态（需子类实现）"""
        raise NotImplementedError

    async def collect_once(self) -> Any:
        """连接后执行一次的采集任务（需子类实现）"""
        return {}
