import asyncio
import sys
import os

# Ensure we can import app
sys.path.append(os.getcwd())

from app.core.database import db

async def add_column():
    print("Connecting to DB...")
    try:
        await db.connect()
        print("Connected.")
        
        # Check if column exists
        val = await db.fetch_val("SELECT column_name FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'is_default'")
        if not val:
            print("Adding is_default column...")
            await db.execute("ALTER TABLE roles ADD COLUMN is_default BOOLEAN DEFAULT FALSE")
            print("Column added.")
        else:
            print("Column already exists.")

        user_perm_level = await db.fetch_val(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'permission_level'"
        )
        if user_perm_level:
            print("Dropping users.permission_level column...")
            await db.execute("ALTER TABLE users DROP COLUMN permission_level")
            print("Column dropped.")
        else:
            print("users.permission_level column not found.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await db.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(add_column())
