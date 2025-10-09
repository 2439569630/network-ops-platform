from typing import Union, List, Dict, Any

import asyncpg
import logging

logger = logging.getLogger(__name__)

# 全局连接池变量
pool = None


async def init():
    global pool
    logger.info('正在连接数据库')
    try:
        # 创建连接池
        pool = await asyncpg.create_pool(
            host='www.mynameislhq.xyz',
            port=5432,
            user='user',
            password='kf4PTkCsBFWWaNCp',
            database='user',
            min_size=5,
            max_size=20,
            command_timeout=30,
            max_inactive_connection_lifetime=300
        )

        # 测试连接
        async with pool.acquire() as conn:
            result = await conn.fetchval('SELECT 1')
            if result == 1:
                logger.info('数据库连接测试成功')
            else:
                logger.warning(f'数据库连接测试返回异常值: {result}')

        return True
    except Exception as e:
        logger.error(f'数据库连接失败: {e}')
        return False


async def close():
    global pool
    if pool:
        logger.info('正在关闭数据库连接池')
        await pool.close()
        pool = None




# 获取连接池的公共接口
def get_pool():
    return pool


async def execute(
        sql: str,
        *args,
        fetch: bool = False,
        fetch_row: bool = False,
        fetch_val: bool = False
) -> Union[List[Dict[str, Any]], Dict[str, Any], Any, int, None]:
    """
    执行SQL语句的通用接口

    参数:
        sql: SQL语句
        *args: SQL参数
        fetch: 是否获取所有结果（返回列表）
        fetch_row: 是否只获取单行结果（返回字典）
        fetch_val: 是否只获取单个值

    返回:
        根据参数返回不同结果：
        - fetch=True: 结果列表（每行为字典）
        - fetch_row=True: 单行结果（字典）
        - fetch_val=True: 单个值
        - 默认: 受影响的行数
    """
    if not pool:
        logger.error("数据库连接池未初始化")
        return None

    try:
        async with pool.acquire() as conn:
            if fetch:
                # 获取所有结果
                records = await conn.fetch(sql, *args)
                return [dict(record) for record in records]
            elif fetch_row:
                # 获取单行结果
                record = await conn.fetchrow(sql, *args)
                return dict(record) if record else None
            elif fetch_val:
                # 获取单个值
                return await conn.fetchval(sql, *args)
            else:
                # 执行命令并返回受影响的行数
                result = await conn.execute(sql, *args)
                # 解析受影响的行数 (格式: "INSERT 0 1" -> 1)
                if ' ' in result:
                    return int(result.split()[-1])
                return 0
    except Exception as e:
        logger.error(f"SQL执行失败: {e}\nSQL: {sql}\n参数: {args}")
        raise