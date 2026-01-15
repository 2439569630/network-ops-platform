import asyncio
import asyncpg
import sys
import os

# Add project root to sys.path so we can import app.core.config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

async def migrate():
    print(f"Connecting to {settings.DATABASE_URL}...")
    
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    print("Connected.")

    # 1. Add location_id to repair_orders
    try:
        # Check if column exists
        row = await conn.fetchrow("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='repair_orders' AND column_name='location_id';
        """)
        
        if not row:
            print("Adding location_id column to repair_orders...")
            await conn.execute("ALTER TABLE repair_orders ADD COLUMN location_id BIGINT;")
            print("Column added.")
        else:
            print("Column location_id already exists.")
            
    except Exception as e:
        print(f"Error modifying repair_orders: {e}")

    # 2. Check location_nodes and add sample data if empty
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM location_nodes;")
        print(f"Current location nodes count: {count}")
        
        if count == 0:
            print("Adding sample location data...")
            # Insert Root
            # We need to handle the fields correctly based on the model:
            # id (BigInt, pk), parent_id, name, type, code, ...
            
            # Root: Campus
            await conn.execute("""
                INSERT INTO location_nodes (id, parent_id, name, type, code, sort_order, status, created_at, updated_at)
                VALUES (1, NULL, '主校区', 'campus', '1', 0, TRUE, NOW(), NOW());
            """)
            
            # Building A
            await conn.execute("""
                INSERT INTO location_nodes (id, parent_id, name, type, code, sort_order, status, created_at, updated_at)
                VALUES (2, 1, '教学楼A', 'building', '1.1', 0, TRUE, NOW(), NOW());
            """)
            
            # Room 101
            await conn.execute("""
                INSERT INTO location_nodes (id, parent_id, name, type, code, sort_order, status, created_at, updated_at)
                VALUES (3, 2, '101教室', 'room', '1.1.1', 0, TRUE, NOW(), NOW());
            """)
            
            # Reset sequence if needed
            try:
                await conn.execute("SELECT setval('location_nodes_id_seq', (SELECT MAX(id) FROM location_nodes));")
            except Exception as seq_err:
                print(f"Sequence update warning (might be ok if not using serial): {seq_err}")

            print("Sample data added.")
            
    except Exception as e:
        print(f"Error checking/adding location nodes: {e}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
