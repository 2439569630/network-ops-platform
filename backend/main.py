import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from Routers.Login.Login import router as Login


from DataBase import PostgreSQL
from logger import setup_logger

from DataBase.Redis import RedisManager

import DataBase.PostgreSQL

logger = logging.getLogger(__name__)
# 首先配置日志系统
setup_logger()



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('初始化')
    await PostgreSQL.init()
    pool = PostgreSQL.get_pool()

    data = await PostgreSQL.execute('select 1', fetch_val=True, fetch=True)
    print(
        data
    )
    Redis = RedisManager()
    await Redis.init_pool()



    yield
    await PostgreSQL.close()
    await Redis.close_pool()

app = FastAPI(lifespan=lifespan)

app.include_router(Login)