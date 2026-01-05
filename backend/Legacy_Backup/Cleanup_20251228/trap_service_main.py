import asyncio
import logging
import signal
import sys
import os
from logging.handlers import RotatingFileHandler
from app.workers.trap.listener import TrapReceiver

# 配置日志
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE = os.path.join(LOG_DIR, 'trap_service.log')

# 配置根日志记录器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler() # 同时输出到控制台，方便调试
    ]
)

logger = logging.getLogger("TrapService")

async def main():
    logger.info("Trap Service 正在启动...")
    
    # 默认端口 162，可以通过环境变量或命令行参数覆盖
    port = int(os.getenv("TRAP_PORT", 162))
    
    receiver = TrapReceiver(port=port)
    
    # 信号处理
    stop_event = asyncio.Event()
    
    def handle_signal():
        logger.info("收到停止信号，正在关闭服务...")
        stop_event.set()

    # Windows 下不支持 add_signal_handler 处理 SIGINT/SIGTERM (Limited support)
    # 对于 Windows，通常依靠 KeyboardInterrupt 或 task cancellation
    # 这里我们简单处理，如果是 Linux 可以用 signal.SIGTERM
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handle_signal)
        loop.add_signal_handler(signal.SIGINT, handle_signal)
    
    try:
        await receiver.start()
        logger.info(f"Trap Service 已启动，监听端口: {port}")
        
        # Windows 下的简单等待循环
        while not stop_event.is_set():
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"Trap Service 异常退出: {e}")
    finally:
        await receiver.stop()
        logger.info("Trap Service 已停止")

if __name__ == '__main__':
    try:
        if sys.platform == 'win32':
            # Windows 平台下 ProactorEventLoop 支持更好
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
