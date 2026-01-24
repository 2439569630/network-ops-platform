
"""
ASGI 入口文件
定义 FastAPI 应用实例、生命周期管理 (数据库连接、Redis、ORM 初始化)、中间件和路由注册。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tortoise import Tortoise

from app.api.v1.api import api_router
from app.api.v1.endpoints import devices
from app.core.config import settings
from app.core.database import db
from app.core.redis import redis_manager
from app.core.logger import setup_logger
from app.core.security import UnicornException, unicorn_exception_handler
from app.core.system_config import SystemConfig
from app.services.notification_service import NotificationService
from app.services.device_service import device_service
from app.services.rbac_service import RbacService
from app.utils.remote_image_api import RemoteImageApiClient
from app.core.max_body_size_middleware import MaxBodySizeMiddleware

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

    # Init Tortoise ORM
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
        await Tortoise.generate_schemas()
        logger.info("Tortoise ORM 初始化成功")

        try:
            await db.execute(
                'ALTER TABLE IF EXISTS "device_alert_rules" '
                'ADD COLUMN IF NOT EXISTS "cooldown" INT NOT NULL DEFAULT 0;'
            )
        except Exception as e:
            logger.error(f"告警规则表结构初始化失败: {e}")

        try:
            await db.execute(
                'ALTER TABLE IF EXISTS "device_configs" '
                'ADD COLUMN IF NOT EXISTS "interfaces_sync_interval" DOUBLE PRECISION NOT NULL DEFAULT 3600.0;'
            )
            await db.execute(
                'ALTER TABLE IF EXISTS "device_configs" '
                'ADD COLUMN IF NOT EXISTS "routes_sync_interval" DOUBLE PRECISION NOT NULL DEFAULT 3600.0;'
            )
            await db.execute(
                'ALTER TABLE IF EXISTS "device_configs" '
                'ADD COLUMN IF NOT EXISTS "vlans_sync_interval" DOUBLE PRECISION NOT NULL DEFAULT 3600.0;'
            )
        except Exception as e:
            logger.error(f"设备深度巡检配置表结构初始化失败: {e}")

        # 同步系统权限
        try:
            sync_res = await RbacService.sync_system_permissions()
            logger.info(f"系统权限同步完成: {sync_res}")
            
            # 自动给 admin 角色赋予新权限
            await RbacService.grant_permission_to_role_code("admin", "sys:role:distribution")
        except Exception as e:
            logger.error(f"系统权限同步失败: {e}")

        try:
            await SystemConfig.load()
            base_url = str(SystemConfig.get("repair_image_api_base_url", "") or "").strip() or "http://45.192.104.13:40027/api/v1"
            token = await RemoteImageApiClient(base_url=base_url).get_token()
            if token:
                logger.info("外部图片服务 token 预热成功")
            else:
                logger.warning("外部图片服务 token 未配置（缺少邮箱/密码）")
        except Exception as e:
            logger.error(f"外部图片服务 token 预热失败: {e}")

    except Exception as e:
        logger.error(f"Tortoise ORM 初始化失败: {e}")

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

    try:
        yield
    except asyncio.CancelledError:
        pass

    logger.info('服务关闭中...')

    if monitor:
        try:
            await monitor.stop()
        except asyncio.CancelledError:
            logger.warning("监控服务停止过程被取消")
        except Exception as e:
            logger.error(f"监控服务停止失败: {e}")
    
    try:
        await Tortoise.close_connections()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Tortoise 关闭连接失败: {e}")

    close_tasks = [
        db.disconnect(),
        redis_manager.close()
    ]
    try:
        await asyncio.gather(*close_tasks)
    except asyncio.CancelledError:
        logger.info("资源释放过程被取消")
    except Exception as e:
        logger.error(f"资源释放失败: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    MaxBodySizeMiddleware,
    limits={
        "/api/v1/users/avatar/upload": 8 * 1024 * 1024,
        "/api/v1/repair-images/upload": 30 * 1024 * 1024,
    },
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
