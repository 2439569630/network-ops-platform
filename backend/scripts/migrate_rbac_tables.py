
import asyncio
import asyncpg

async def migrate():
    dsn = "postgres://lhq:isHjPEaxBrwbkQpN@123.207.72.157:54322/lhq"
    print(f"Connecting to database...")
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected.")
        
        async with conn.transaction():
            # Migrate user_roles
            print("Checking 'user_roles'...")
            row = await conn.fetchrow("SELECT column_name FROM information_schema.columns WHERE table_name='user_roles' AND column_name='id';")
            if not row:
                print("Migrating 'user_roles'...")
                await conn.execute("ALTER TABLE user_roles ADD COLUMN id BIGSERIAL;")
                # Drop old PK if exists (likely composite)
                # Need to find constraint name? Usually user_roles_pkey if it was defined as PRIMARY KEY (user_id, role_id)
                # But it might be just a unique index or no PK.
                # Let's try to drop constraint if exists.
                try:
                    await conn.execute("ALTER TABLE user_roles DROP CONSTRAINT user_roles_pkey;")
                except Exception:
                    pass # Maybe it didn't exist or different name
                
                await conn.execute("ALTER TABLE user_roles ADD PRIMARY KEY (id);")
                await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_roles_user_role ON user_roles (user_id, role_id);")
                print("user_roles migrated.")
            else:
                print("'user_roles' already has 'id'.")

            # Migrate role_permissions
            print("Checking 'role_permissions'...")
            row = await conn.fetchrow("SELECT column_name FROM information_schema.columns WHERE table_name='role_permissions' AND column_name='id';")
            if not row:
                print("Migrating 'role_permissions'...")
                await conn.execute("ALTER TABLE role_permissions ADD COLUMN id BIGSERIAL;")
                try:
                    await conn.execute("ALTER TABLE role_permissions DROP CONSTRAINT role_permissions_pkey;")
                except Exception:
                    pass
                
                await conn.execute("ALTER TABLE role_permissions ADD PRIMARY KEY (id);")
                await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_role_permissions_role_perm ON role_permissions (role_id, permission_id);")
                print("role_permissions migrated.")
            else:
                print("'role_permissions' already has 'id'.")
            
        print("RBAC Migration successful.")
        await conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
