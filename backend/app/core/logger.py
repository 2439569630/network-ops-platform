
import logging
import logging.handlers
import os
import sys
import colorlog

def setup_logger(log_level: str = "INFO"):
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
    
    return root_logger
