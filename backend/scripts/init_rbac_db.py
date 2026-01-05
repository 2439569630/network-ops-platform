import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import db


async def init_rbac_db():
    print("正在初始化角色与权限管理数据库...")
    await db.connect()

    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                code VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        print("表 roles 创建成功")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS permissions (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                code VARCHAR(150) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        print("表 permissions 创建成功")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
                PRIMARY KEY (role_id, permission_id)
            );
            """
        )
        print("表 role_permissions 创建成功")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, role_id)
            );
            """
        )
        print("表 user_roles 创建成功")

    except Exception as e:
        print(f"数据库初始化失败: {e}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(init_rbac_db())

