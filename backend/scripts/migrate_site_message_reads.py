
import asyncio
import asyncpg

async def migrate():
    dsn = "postgres://lhq:isHjPEaxBrwbkQpN@123.207.72.157:54322/lhq"
    print(f"Connecting to database...")
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected.")
        
        # Check if id column exists in site_message_reads
        check_sql = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='site_message_reads' AND column_name='id';
        """
        row = await conn.fetchrow(check_sql)
        
        if not row:
            print("Migrating 'site_message_reads' table...")
            async with conn.transaction():
                # Add id column
                await conn.execute("ALTER TABLE site_message_reads ADD COLUMN id BIGSERIAL;")
                
                # Drop old PK if exists
                # We need to find the name of the PK constraint first, usually site_message_reads_pkey
                await conn.execute("ALTER TABLE site_message_reads DROP CONSTRAINT IF EXISTS site_message_reads_pkey;")
                
                # Set new PK
                await conn.execute("ALTER TABLE site_message_reads ADD PRIMARY KEY (id);")
                
                # Add unique constraint for (message_id, user_id) to maintain logic
                await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_site_message_reads_msg_user ON site_message_reads (message_id, user_id);")
                
            print("Migration successful.")
        else:
            print("'site_message_reads' already has 'id' column.")
            
        await conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
