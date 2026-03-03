
"""
ASGI 入口文件
定义 FastAPI 应用实例、生命周期管理 (数据库连接、Redis、ORM 初始化)、中间件和路由注册。
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from tortoise.context import TortoiseContext
except Exception:
    # 兼容处理：如果导入失败，定义一个简单的 TortoiseContext 模拟类
    from tortoise import Tortoise

    class TortoiseContext:
        """
        TortoiseContext 上下文管理器，用于管理数据库连接的生命周期
        """
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            # 退出上下文时关闭连接
            await Tortoise.close_connections()

        async def init(self, *, db_url: str, modules: dict, **kwargs):
            # 初始化 Tortoise ORM
            await Tortoise.init(db_url=db_url, modules=modules)

        async def generate_schemas(self):
            # 生成数据库表结构
            await Tortoise.generate_schemas()

# 导入应用模块
from app.api.v1.api import api_router
from app.api.v1.endpoints import devices
from app.core.config import settings
from app.core.database import db
from app.core.redis import redis_manager
from app.core.logger import setup_logger
from app.core.security import UnicornException, unicorn_exception_handler, get_password_hash
from app.core.system_config import SystemConfig
from app.services.rbac_service import RbacService
from app.utils.remote_image_api import RemoteImageApiClient
from app.core.max_body_size_middleware import MaxBodySizeMiddleware

# 获取日志记录器
logger = logging.getLogger(__name__)

# 配置日志
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理器
    在应用启动时执行初始化操作 (Redis, DB, ORM, 权限同步等)
    在应用关闭时执行清理操作 (关闭连接)
    """
    logger.info('服务初始化...')
    tortoise_ctx: TortoiseContext | None = None

    # 1. 初始化 Redis 连接
    try:
        await redis_manager.init()
    except Exception as e:
        logger.error(f"Redis 初始化失败: {e}")

    # 2. 初始化数据库连接 (asyncpg)
    try:
        await db.connect()
        await db.fetch_val('select 1')
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise

    # 3. 初始化 Tortoise ORM
    try:
        tortoise_ctx = TortoiseContext()
        await tortoise_ctx.__aenter__()
        await tortoise_ctx.init(
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
                "app.models.orm.config_push",
                "app.models.orm.alert",
                "app.models.orm.log",
            ]},
            _enable_global_fallback=True,
        )
        # 自动生成/更新表结构
        await tortoise_ctx.generate_schemas()
        logger.info("Tortoise ORM 初始化成功")

        # 4. 手动执行一些 SQL 迁移脚本 (处理 ORM 无法自动处理的变更)
        try:
            # 为告警规则表添加冷却时间字段
            await db.execute(
                'ALTER TABLE IF EXISTS "device_alert_rules" '
                'ADD COLUMN IF NOT EXISTS "cooldown" INT NOT NULL DEFAULT 0;'
            )
        except Exception as e:
            logger.error(f"告警规则表结构初始化失败: {e}")

        try:
            # 为设备配置表添加同步间隔字段
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

        try:
            # 为用户表添加软删除相关字段
            await db.execute('ALTER TABLE IF EXISTS "users" ADD COLUMN IF NOT EXISTS "is_deleted" BOOLEAN NOT NULL DEFAULT FALSE;')
            await db.execute('ALTER TABLE IF EXISTS "users" ADD COLUMN IF NOT EXISTS "deleted_at" TIMESTAMPTZ NULL;')
            await db.execute('ALTER TABLE IF EXISTS "users" ADD COLUMN IF NOT EXISTS "deleted_by" INT NULL;')
        except Exception as e:
            logger.error(f"用户表结构初始化失败: {e}")

        # 5. 同步系统权限数据
        try:
            sync_res = await RbacService.sync_system_permissions()
            logger.info(f"系统权限同步完成: {sync_res}")
            
            # 自动给 admin 角色赋予新权限
            await RbacService.grant_permission_to_role_code("admin", "sys:audit:view")
            await RbacService.grant_permission_to_role_code("admin", "sys:role:manage")
        except Exception as e:
            logger.error(f"系统权限同步失败: {e}")

        # 6. 初始化超级管理员账号 (如果未初始化)
        try:
            bootstrap_key = "bootstrap:superadmin_done"
            row = await db.fetch_one("SELECT value FROM system_settings WHERE key = $1", bootstrap_key)
            already_done = False
            if row:
                v = str(row.get("value") or "").strip().lower()
                already_done = v in {"1", "true", "yes", "y"}

            if not already_done:
                username = "admin"
                password = "Admin@123456"

                # 创建超级管理员角色
                role_id = await db.fetch_val("SELECT id FROM roles WHERE code = $1 LIMIT 1", "superadmin")
                if not role_id:
                    await db.execute(
                        "INSERT INTO roles (name, code, description, is_default) VALUES ($1, $2, $3, FALSE) ON CONFLICT DO NOTHING",
                        "超级管理员",
                        "superadmin",
                        "系统预置超级管理员角色",
                    )
                    role_id = await db.fetch_val("SELECT id FROM roles WHERE code = $1 LIMIT 1", "superadmin")

                # 创建超级管理员用户
                user_id = await db.fetch_val("SELECT id FROM users WHERE username = $1 LIMIT 1", username)
                if not user_id:
                    hashed_pw = get_password_hash(password)
                    await db.execute(
                        "INSERT INTO users (username, password, nickname, email, is_approved, permissions) "
                        "VALUES ($1, $2, $3, NULL, TRUE, $4::jsonb) ON CONFLICT DO NOTHING",
                        username,
                        hashed_pw,
                        "超级管理员",
                        json.dumps([]),
                    )
                    user_id = await db.fetch_val("SELECT id FROM users WHERE username = $1 LIMIT 1", username)

                # 关联用户和角色
                if user_id and role_id:
                    await db.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        int(user_id),
                        int(role_id),
                    )

                # 标记初始化完成
                await db.execute(
                    "INSERT INTO system_settings (key, value, group_name, description) "
                    "VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                    bootstrap_key,
                    "1",
                    "system",
                    "默认超级管理员初始化完成标记",
                )
                logger.warning('已创建/确保默认超级管理员账号存在：username="admin"，请尽快修改密码')
        except Exception as e:
            logger.error(f"默认超级管理员初始化失败: {e}")

        # 7. 预热外部图片服务 Token
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
            if tortoise_ctx is not None:
                await tortoise_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        raise

    # 应用启动完成，开始处理请求
    try:
        yield
    except asyncio.CancelledError:
        pass

    # 应用关闭，开始清理资源
    logger.info('服务关闭中...')
    
    # 1. 关闭 Tortoise ORM 连接
    try:
        if tortoise_ctx is not None:
            await tortoise_ctx.__aexit__(None, None, None)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Tortoise 关闭连接失败: {e}")

    # 2. 关闭数据库和 Redis 连接
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


# 创建 FastAPI 应用实例
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 添加请求体大小限制中间件
app.add_middleware(
    MaxBodySizeMiddleware,
    limits={
        "/api/v1/users/avatar/upload": 8 * 1024 * 1024,  # 头像上传限制 8MB
        "/api/v1/repair-images/upload": 30 * 1024 * 1024, # 报修图片上传限制 30MB
    },
)

# 配置 CORS (跨域资源共享)
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 注册全局异常处理器
app.add_exception_handler(UnicornException, unicorn_exception_handler)

# 注册 API 路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 注册其他路由 (SSH, 设备管理兼容路径)
app.include_router(devices.ssh_router, tags=["SSH"])
app.include_router(devices.router, prefix="/user/device", tags=["Device (Legacy)"])
