
import asyncio
import asyncpg

async def migrate():
    dsn = "postgres://lhq:isHjPEaxBrwbkQpN@123.207.72.157:54322/lhq"
    print(f"Connecting to database...")
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected.")
        
        # Check if constraint exists
        check_sql = """
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name='device_change_log' AND constraint_name='device_change_log_device_id_fkey';
        """
        row = await conn.fetchrow(check_sql)
        
        if row:
            print("Dropping foreign key constraint 'device_change_log_device_id_fkey'...")
            await conn.execute("ALTER TABLE device_change_log DROP CONSTRAINT device_change_log_device_id_fkey;")
            print("Constraint dropped successfully.")
        else:
            print("Constraint does not exist.")
            
        await conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
