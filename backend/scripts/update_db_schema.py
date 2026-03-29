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

    # 1. Add is_email_notify to users
    print("Checking 'users' table for 'is_email_notify' column...")
    try:
        await conn.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS is_email_notify BOOLEAN DEFAULT FALSE;
        """)
        print("Column 'is_email_notify' added (or already exists).")
    except Exception as e:
        print(f"Error adding column: {e}")

    # 2. Add is_login_email_notify to users
    print("Checking 'users' table for 'is_login_email_notify' column...")
    try:
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_login_email_notify BOOLEAN DEFAULT FALSE;
        """)
        print("Column 'is_login_email_notify' added (or already exists).")
    except Exception as e:
        print(f"Error adding login notify column: {e}")

    # 3. Create login_logs table
    print("Creating 'login_logs' table...")
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS login_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                ip VARCHAR(50),
                user_agent VARCHAR(500),
                device VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("Table 'login_logs' created (or already exists).")
    except Exception as e:
        print(f"Error creating table: {e}")

    await conn.close()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
