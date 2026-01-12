import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.api.v1.endpoints import devices
from app.core.config import settings
from app.core.database import db
from app.core.redis import redis_manager
from app.core.logger import setup_logger
from app.core.security import UnicornException, unicorn_exception_handler
from app.services.notification_service import NotificationService
from app.services.device_service import device_service

logger = logging.getLogger(__name__)

setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('服务初始化...')
    disable_internal_monitor = str(os.getenv("DISABLE_INTERNAL_MONITOR", "")).strip() in {"1", "true", "TRUE", "yes", "YES"}

    try:
        await redis_manager.init()
    except Exception as e:
        logger.error(f"Redis 初始化失败: {e}")

    try:
        await db.connect()
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")

    try:
        await db.fetch_val('select 1')
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")

    try:
        await NotificationService._ensure_site_message_tables()
    except Exception as e:
        logger.error(f"站内消息表初始化失败: {e}")

    try:
        await device_service.ensure_ssh_command_audit_table()
    except Exception as e:
        logger.error(f"SSH 命令审计表初始化失败: {e}")

    monitor = None
    if not disable_internal_monitor:
        from app.workers.monitor.manager import MonitorManager

        monitor = MonitorManager()
        await monitor.start()

    yield

    logger.info('服务关闭中...')

    if monitor:
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

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_exception_handler(UnicornException, unicorn_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(devices.ssh_router, tags=["SSH"])
app.include_router(devices.router, prefix="/user/device", tags=["Device (Legacy)"])
