
import asyncio
import asyncpg

async def migrate():
    # Connection details from settings
    dsn = "postgres://lhq:isHjPEaxBrwbkQpN@123.207.72.157:54322/lhq"
    
    print(f"Connecting to database...")
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected.")
        
        # Check if column exists first to be safe
        check_sql = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' AND column_name='updated_at';
        """
        row = await conn.fetchrow(check_sql)
        
        if not row:
            print("Adding 'updated_at' column to 'users' table...")
            # Using timestamp without time zone to match created_at
            await conn.execute("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
            print("Column added successfully.")
        else:
            print("Column 'updated_at' already exists.")
            
        await conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
