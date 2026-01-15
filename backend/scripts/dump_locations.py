import asyncio
import asyncpg
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings

async def dump_locations():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    rows = await conn.fetch("SELECT * FROM location_nodes ORDER BY id;")
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(dump_locations())
