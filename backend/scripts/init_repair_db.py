import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import db

async def init_repair_db():
    print("正在初始化工单系统数据库...")
    await db.connect()
    
    try:
        # 1. 工单主表 repair_orders
        await db.execute("""
            CREATE TABLE IF NOT EXISTS repair_orders (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                submitter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                device_id INTEGER REFERENCES network_devices(id) ON DELETE SET NULL,
                priority VARCHAR(50) NOT NULL DEFAULT 'medium',
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                estimated_time TIMESTAMP WITH TIME ZONE,
                actual_completion_time TIMESTAMP WITH TIME ZONE
            );
        """)
        print("表 repair_orders 创建成功")

        # 2. 工单日志表 order_logs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_logs (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES repair_orders(id) ON DELETE CASCADE,
                operator_id INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(50) NOT NULL,
                from_status VARCHAR(50),
                to_status VARCHAR(50),
                remark TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("表 order_logs 创建成功")

        # 3. 评价表 order_reviews
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_reviews (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL UNIQUE REFERENCES repair_orders(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                response_time_rating INTEGER CHECK (response_time_rating >= 1 AND response_time_rating <= 5),
                service_quality_rating INTEGER CHECK (service_quality_rating >= 1 AND service_quality_rating <= 5),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("表 order_reviews 创建成功")
        
    except Exception as e:
        print(f"数据库初始化失败: {e}")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(init_repair_db())
