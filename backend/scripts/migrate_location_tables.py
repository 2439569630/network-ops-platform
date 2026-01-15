
import asyncio
import asyncpg

async def migrate():
    dsn = "postgres://lhq:isHjPEaxBrwbkQpN@123.207.72.157:54322/lhq"
    print(f"Connecting to database...")
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected.")
        
        async with conn.transaction():
            # Migrate location_node_roles
            print("Checking 'location_node_roles'...")
            # Check if table exists first (it might not if LocationService._ensure_tables wasn't called)
            # But likely it exists.
            
            row = await conn.fetchrow("SELECT column_name FROM information_schema.columns WHERE table_name='location_node_roles' AND column_name='id';")
            if not row:
                # Check if table exists
                tbl = await conn.fetchrow("SELECT table_name FROM information_schema.tables WHERE table_name='location_node_roles';")
                if tbl:
                    print("Migrating 'location_node_roles'...")
                    await conn.execute("ALTER TABLE location_node_roles ADD COLUMN id BIGSERIAL;")
                    try:
                        await conn.execute("ALTER TABLE location_node_roles DROP CONSTRAINT location_node_roles_pkey;")
                    except Exception:
                        pass
                    await conn.execute("ALTER TABLE location_node_roles ADD PRIMARY KEY (id);")
                    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_loc_node_roles_node_role ON location_node_roles (node_id, role_id);")
            else:
                print("'location_node_roles' already has 'id'.")

            # Migrate location_node_users
            print("Checking 'location_node_users'...")
            row = await conn.fetchrow("SELECT column_name FROM information_schema.columns WHERE table_name='location_node_users' AND column_name='id';")
            if not row:
                tbl = await conn.fetchrow("SELECT table_name FROM information_schema.tables WHERE table_name='location_node_users';")
                if tbl:
                    print("Migrating 'location_node_users'...")
                    await conn.execute("ALTER TABLE location_node_users ADD COLUMN id BIGSERIAL;")
                    try:
                        await conn.execute("ALTER TABLE location_node_users DROP CONSTRAINT location_node_users_pkey;")
                    except Exception:
                        pass
                    await conn.execute("ALTER TABLE location_node_users ADD PRIMARY KEY (id);")
                    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_loc_node_users_node_user ON location_node_users (node_id, user_id);")
            else:
                print("'location_node_users' already has 'id'.")
            
        print("Location Migration successful.")
        await conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
