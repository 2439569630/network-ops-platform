
import logging
import logging.handlers
import os
import sys
import time
import colorlog

class ParamikoLogFilter(logging.Filter):
    """
    Paramiko 日志过滤器
    用于拦截底层的连接错误堆栈，并转换为友好的中文提示
    """
    def __init__(self, window_seconds: float = 10.0, max_cache: int = 256):
        super().__init__()
        self.window_seconds = float(window_seconds or 0.0)
        self.max_cache = int(max_cache or 0)
        self._last_seen: dict[str, float] = {}

    def _dedupe(self, key: str) -> bool:
        if self.window_seconds <= 0:
            return True
        now = time.monotonic()
        last = float(self._last_seen.get(key, 0.0) or 0.0)
        if now - last < self.window_seconds:
            return False
        self._last_seen[key] = now
        if self.max_cache > 0 and len(self._last_seen) > self.max_cache:
            items = sorted(self._last_seen.items(), key=lambda x: x[1], reverse=True)[: self.max_cache]
            self._last_seen = dict(items)
        return True

    def filter(self, record):
        if record.levelno < logging.ERROR:
            return True

        msg = record.getMessage()
        msg_stripped = msg.strip()

        if not msg_stripped:
            return False

        msg_lstripped = msg.lstrip()
        if (
            msg_stripped == "Traceback (most recent call last):"
            or msg_stripped.startswith("During handling of the above exception")
            or msg_lstripped.startswith('File "')
            or msg_lstripped.startswith("File '")
            or msg.startswith((" ", "\t"))
        ):
            return False

        if "EOFError" in msg or (record.exc_info and "EOFError" in str(record.exc_info[0])):
            record.msg = "SSH 连接意外中断 (EOFError) - 请检查设备是否限制连接数或主动断开"
            record.args = ()
            record.exc_info = None
            record.stack_info = None
            final = record.getMessage()
            key = f"{record.name}:{record.levelno}:{final}"
            return self._dedupe(key)

        if "Error reading SSH protocol banner" in msg or (
            record.exc_info and "Error reading SSH protocol banner" in str(record.exc_info[1])
        ):
            record.msg = "读取 SSH 协议横幅失败 - 端口可能非 SSH 服务或连接被重置"
            record.args = ()
            record.exc_info = None
            record.stack_info = None
            final = record.getMessage()
            key = f"{record.name}:{record.levelno}:{final}"
            return self._dedupe(key)

        record.exc_info = None
        record.stack_info = None
        if "\n" in msg:
            record.msg = msg.splitlines()[0]
            record.args = ()
        final = record.getMessage()
        key = f"{record.name}:{record.levelno}:{final}"
        return self._dedupe(key)

def setup_logger(log_level: str = "INFO"):
    """
    配置系统日志
    
    包括控制台输出和文件输出，以及特定模块的日志级别设置
    """
    # 1. 确保日志目录存在
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 定义格式器
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )

    # 3. 配置 Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File Handler
    main_file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'), encoding='utf-8')
    main_file_handler.setFormatter(file_formatter)
    root_logger.addHandler(main_file_handler)

    # 4. 专用 Logger 配置
    # Device Drivers
    driver_logger = logging.getLogger("app.drivers")
    driver_logger.setLevel(logging.INFO)
    driver_handler = logging.FileHandler(os.path.join(log_dir, 'drivers.log'), encoding='utf-8')
    driver_handler.setFormatter(file_formatter)
    driver_logger.addHandler(driver_handler)
    driver_logger.propagate = True

    # 屏蔽噪音
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("netmiko").setLevel(logging.CRITICAL)
    
    # 挂载 Paramiko 过滤器到 paramiko.transport
    transport_logger = logging.getLogger("paramiko.transport")
    transport_logger.addFilter(ParamikoLogFilter())
    
    return root_logger
