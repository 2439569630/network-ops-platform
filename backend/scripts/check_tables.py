"""
数据库表检查脚本
检查关键业务表是否存在。
"""

import asyncio
import asyncpg
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings

async def check_tables():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    tables = ['location_nodes', 'location_node_roles', 'location_node_users']
    for t in tables:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1);", 
            t
        )
        print(f"Table {t} exists: {exists}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_tables())
