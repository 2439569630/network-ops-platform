import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from Routers.Login.Login import router as Login
from Routers.User.device import router as device

from DataBase import PostgreSQL
from logger import setup_logger

from DataBase.Redis import RedisManager
from fastapi.middleware.cors import CORSMiddleware
import DataBase.PostgreSQL

# 导入异常消息处理
from auth.security import UnicornException, unicorn_exception_handler

logger = logging.getLogger(__name__)
# 首先配置日志系统
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('初始化')

    # 初始化 Redis 实例
    redis = RedisManager()

    # 并发执行初始化
    init_tasks = [
        PostgreSQL.init(),
        redis.init_pool()
    ]
    await asyncio.gather(*init_tasks)

    # 获取连接池
    pool = PostgreSQL.get_pool()

    # 测试数据库连接
    data = await PostgreSQL.execute('select 1', fetch_val=True, fetch=True)
    print(data)

    yield

    # 并发执行关闭任务
    close_tasks = [
        PostgreSQL.close(),
        redis.close_pool()
    ]
    await asyncio.gather(*close_tasks)

app = FastAPI(lifespan=lifespan)


# 跨域配置
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# 导入并注册路由模块
# include_router()用于将路由注册到FastAPI应用中
app.include_router(Login)  # 注册登录相关的路由模块
app.include_router(device)  # 注册设备相关的路由模块

# 注册异常处理器
app.add_exception_handler(UnicornException, unicorn_exception_handler)
