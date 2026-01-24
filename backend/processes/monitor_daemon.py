# 导入异步 I/O 库
from ast import Yield
import asyncio
# 导入日志模块
import logging
# 导入操作系统相关功能
import os
# 导入信号处理模块，用于优雅关闭
import signal
# 导入系统相关参数与函数
import sys
# 导入 Tortoise ORM 主入口
from tortoise import Tortoise

# 计算项目根目录：当前文件再向上跳一级
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 如果项目根目录不在 Python 模块搜索路径中，则插入到最前面，确保自定义模块能被优先找到
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 从自定义包中导入所需模块
from app.core.config import settings                    # 全局配置
from app.core.database import db                       # 数据库连接管理
from app.core.logger import setup_logger               # 日志初始化函数
from app.core.redis import redis_manager               # Redis 连接管理
from app.services.notification_service import NotificationService  # 通知服务
from app.workers.monitor.manager import MonitorManager  # 监控任务管理器

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


async def _run() -> int:
    """
    监控守护进程的主协程，负责初始化各类资源、启动监控任务并等待退出信号。
    返回 0 表示正常退出。
    """
    # 初始化日志系统（级别、格式、处理器等）
    setup_logger()
    logger.info("Monitor daemon starting...")

    # 尝试初始化 Redis 连接，失败仅记录错误，进程继续
    try:
        await redis_manager.init()
    except Exception as e:
        logger.error(f"Redis init failed: {e}")

    # 尝试连接主数据库，失败仅记录错误，进程继续
    try:
        await db.connect()
    except Exception as e:
        logger.error(f"DB connect failed: {e}")
        try:
            await redis_manager.close()
        except Exception:
            pass
        return 1

    # 初始化 Tortoise ORM：传入数据库 URL 与模型模块列表，并自动生成表结构
    try:
        await Tortoise.init(
            db_url=settings.DATABASE_URL,
            modules={"models": [
                "app.models.orm.user", 
                "app.models.orm.device", 
                "app.models.orm.audit",
                "app.models.orm.notification",
                "app.models.orm.repair",
                "app.models.orm.rbac",
                "app.models.orm.location",
                "app.models.orm.config",
                "app.models.orm.alert",
            ]},
        )
        # 根据模型定义在数据库中创建缺失的表
        await Tortoise.generate_schemas()
        logger.info("Tortoise ORM initialized")
    except Exception as e:
        logger.error(f"Tortoise ORM init failed: {e}")
        try:
            await asyncio.gather(db.disconnect(), redis_manager.close())
        except Exception:
            pass
        try:
            await Tortoise.close_connections()
        except Exception:
            pass
        return 1

    # 确保站内信所需的数据表已创建，失败仅记录错误
    try:
        await NotificationService._ensure_site_message_tables()
    except Exception as e:
        logger.error(f"Ensure site message tables failed: {e}")

    # 创建监控管理器实例并启动后台监控任务
    monitor = MonitorManager()
    await monitor.start()

    # 创建一个异步事件，用于在收到退出信号时通知主循环
    stop_event = asyncio.Event()

    def _stop():
        """
        信号处理回调：当收到 SIGTERM/SIGINT 时设置 stop_event，通知主循环退出。
        """
        stop_event.set()

    # 非 Windows 平台下注册信号处理器，实现优雅关闭
    if os.name != "nt":
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _stop)
        loop.add_signal_handler(signal.SIGINT, _stop)

    # 阻塞等待 stop_event 被设置（即收到退出信号）
    await stop_event.wait()

    # 收到退出信号后进入清理阶段
    logger.info("监控守护进程正在停止...")
    
    # 停止所有监控任务（内部已包含 Redis 状态清理和并发断开连接）
    await monitor.stop()

    # 并发关闭数据库与 Redis 连接
    await asyncio.gather(db.disconnect(), redis_manager.close())
    # 关闭 Tortoise 连接池
    await Tortoise.close_connections()

    return 0


def main() -> int:
    """
    同步入口函数，使用 asyncio.run 启动主协程；
    如果用户按下 Ctrl-C，则捕获 KeyboardInterrupt 并返回 0。
    """
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 0


# 当脚本被直接运行时，使用 raise SystemExit 将 main() 的返回值作为退出码
if __name__ == "__main__":
    raise SystemExit(main())
