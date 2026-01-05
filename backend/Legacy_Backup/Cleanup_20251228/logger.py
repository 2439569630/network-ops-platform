import logging
import logging.handlers
import os
import sys
import colorlog

def setup_logger():
    # 1. 确保日志目录存在
    log_dir = 'log'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 定义格式器
    # 文件日志格式
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台日志格式 (带颜色)
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

    # 3. 配置 Root Logger (全局)
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清除现有的 handlers (避免重复添加导致日志打印多次)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 添加控制台输出 (Standard Output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 添加主文件输出 (myapp.log)
    main_file_handler = logging.FileHandler(os.path.join(log_dir, 'myapp.log'), encoding='utf-8')
    main_file_handler.setFormatter(file_formatter)
    root_logger.addHandler(main_file_handler)

    # 4. 配置 DeviceLayer 专用日志
    # 获取 DeviceLayer logger (注意：代码中需使用 logging.getLogger("DeviceLayer.xxx"))
    device_logger = logging.getLogger("DeviceLayer")
    device_logger.setLevel(logging.INFO)
    
    # 专用文件 handler (device_layer.log)
    device_file_handler = logging.FileHandler(os.path.join(log_dir, 'device_layer.log'), encoding='utf-8')
    device_file_handler.setFormatter(file_formatter)
    device_logger.addHandler(device_file_handler)
    
    # 允许冒泡：这样 DeviceLayer 的日志既会写入 device_layer.log，
    # 也会冒泡到 root logger，从而显示在控制台和 myapp.log 中。
    device_logger.propagate = True

    # 5. 配置 Paramiko 和 Netmiko 日志
    # 避免 SSH 库输出过多的 INFO/DEBUG 日志，设置为 WARNING
    paramiko_logger = logging.getLogger("paramiko")
    paramiko_logger.setLevel(logging.WARNING) 
    
    # Netmiko 在连接断开检测时会打印 ERROR 级别的 Traceback，这在监控场景下是预期的
    # 为了避免刷屏，将其设置为 CRITICAL，只记录最严重的错误
    netmiko_logger = logging.getLogger("netmiko")
    netmiko_logger.setLevel(logging.CRITICAL) 
    
    # 6. 确保其他库的日志也通过 root logger 输出
    # 例如 uvicorn, fastapi 等通常会检查 root logger
    
    return root_logger
