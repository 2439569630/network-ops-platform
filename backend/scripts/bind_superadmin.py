import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import db

async def bind_superadmin():
    print("正在绑定超级管理员角色...")
    await db.connect()
    try:
        # Get superadmin role id
        role = await db.fetch_one("SELECT id FROM roles WHERE code = 'superadmin'")
        if not role:
            print("未找到 superadmin 角色")
            return
        
        role_id = role["id"]
        
        # Get user 123456
        user = await db.fetch_one("SELECT id FROM users WHERE username = '123456'")
        if not user:
            print("未找到用户 123456")
            return
            
        user_id = user["id"]
        
        await db.execute(
            """
            INSERT INTO user_roles (user_id, role_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, role_id) DO NOTHING
            """,
            user_id,
            role_id
        )
        print(f"用户 123456 已绑定到 superadmin 角色 (ID: {role_id})")
        
    except Exception as e:
        print(f"绑定失败: {e}")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(bind_superadmin())