import logging
import colorlog
import os

def setup_logger():
    # 创建根日志器
    logger = logging.getLogger()
    
    if logger.handlers:
        return logger


    # 判断log文件夹是否存在
    if not os.path.exists('log'):
        os.makedirs('log')



    
    # 文件处理器
    file_handler = logging.FileHandler('log/myapp.log', encoding='utf-8')
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.INFO)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
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
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO) #  设置控制台处理器的日志级别为DEBUG，即输出所有级别的日志
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG)
    
    return logger