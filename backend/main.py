import asyncio
import logging
import subprocess
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.api.v1.endpoints import devices
from app.workers.monitor.manager import MonitorManager
from app.core.config import settings
from app.core.database import db
from app.core.redis import redis_manager
from app.core.logger import setup_logger
from app.core.security import UnicornException, unicorn_exception_handler

logger = logging.getLogger(__name__)

# 配置日志系统
setup_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('服务初始化...')

    # 1. 初始化资源
    await redis_manager.init()
    await db.connect()

    # 测试数据库连接
    try:
        await db.fetch_val('select 1')
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")

    # 2. 启动监控服务
    monitor = MonitorManager()
    await monitor.start()

    yield

    # 4. 清理资源
    logger.info('服务关闭中...')
    
    # 关闭 SSH 子进程
    global ssh_process
    if ssh_process:
        logger.info("正在停止 SSH 子进程...")
        ssh_process.terminate()
        try:
            # 等待子进程退出
            ssh_process.wait(timeout=5)
            logger.info("SSH 子进程已停止")
        except subprocess.TimeoutExpired:
            logger.warning("SSH 子进程停止超时，强制关闭")
            ssh_process.kill()
    
    await monitor.stop()
    
    close_tasks = [
        db.disconnect(),
        redis_manager.close()
    ]
    await asyncio.gather(*close_tasks)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 跨域配置
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 注册异常处理器
app.add_exception_handler(UnicornException, unicorn_exception_handler)

# 路由注册
# 标准 API (挂载在 /api/v1)
app.include_router(api_router, prefix=settings.API_V1_STR)

app.include_router(devices.ssh_router, tags=["SSH"])

app.include_router(devices.router, prefix="/user/device", tags=["Device (Legacy)"])
