import asyncio
import asyncpg
from app.core.config import settings

async def main():
    db_url = settings.DATABASE_URL
    print(f"Using db_url: {db_url}")
    conn = await asyncpg.connect(db_url)
    try:
        result = await conn.execute("DELETE FROM device_notifications WHERE message LIKE '%新工单%'")
        print(f"Deleted rows: {result}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
