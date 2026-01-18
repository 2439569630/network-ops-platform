import asyncio
import asyncpg
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings

async def main():
    print("Connecting to database...")
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
    )
    print("Connected.")

    # Fix system_settings table
    print("Checking 'system_settings' table for timestamp columns...")
    try:
        await conn.execute("""
            ALTER TABLE system_settings 
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
        """)
        print("Columns 'created_at' and 'updated_at' added (or already exist).")
    except Exception as e:
        print(f"Error altering table: {e}")

    await conn.close()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
