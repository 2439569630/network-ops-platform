import asyncio
import sys
import os
import json

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

        roles_seed = [
            {"name": "管理员", "code": "admin", "description": "管理员"},
            {"name": "运维", "code": "yunwei", "description": "运维"},
            {"name": "师生", "code": "shisheng", "description": "师生"},
        ]
        for r in roles_seed:
            await db.execute(
                """
                INSERT INTO roles (name, code, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
                """,
                r["name"],
                r["code"],
                r["description"],
            )
        print("角色数据写入成功")

        permissions_seed = [
            {"name": "登录", "code": "sys:auth:login", "description": ""},
            {"name": "注册", "code": "sys:auth:register", "description": ""},
            {"name": "邮箱验证", "code": "sys:email:verify", "description": ""},
            {"name": "系统概览", "code": "sys:dashboard:view", "description": ""},
            {"name": "查看监控", "code": "sys:monitor:view", "description": ""},
            {"name": "消息中心", "code": "sys:message:access", "description": ""},
            {"name": "订阅实时告警", "code": "sys:alert:subscribe", "description": ""},
            {"name": "查看通知历史", "code": "sys:notify:history", "description": ""},
            {"name": "查看通知配置", "code": "sys:notify:config:view", "description": ""},
            {"name": "编辑通知配置", "code": "sys:notify:config:edit", "description": ""},
            {"name": "测试通知推送", "code": "sys:notify:test", "description": ""},
            {"name": "查看位置", "code": "sys:location:view", "description": ""},
            {"name": "新增位置", "code": "sys:location:add", "description": ""},
            {"name": "编辑位置", "code": "sys:location:edit", "description": ""},
            {"name": "删除位置", "code": "sys:location:del", "description": ""},
            {"name": "查看设备", "code": "sys:device:list", "description": ""},
            {"name": "新增设备", "code": "sys:device:add", "description": ""},
            {"name": "编辑设备", "code": "sys:device:edit", "description": ""},
            {"name": "删除设备", "code": "sys:device:del", "description": ""},
            {"name": "SSH连接", "code": "sys:ssh:connect", "description": ""},
            {"name": "查看用户", "code": "sys:user:view", "description": ""},
            {"name": "管理用户", "code": "sys:user:manage", "description": ""},
            {"name": "批量导入用户", "code": "sys:user:import", "description": ""},
            {"name": "查看配置", "code": "sys:config:view", "description": ""},
            {"name": "编辑配置", "code": "sys:config:edit", "description": ""},
            {"name": "全局通知", "code": "sys:notify:global", "description": ""},
        ]

        for p in permissions_seed:
            await db.execute(
                """
                INSERT INTO permissions (name, code, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
                """,
                p["name"],
                p["code"],
                p["description"],
            )
        print("权限数据写入成功")

        role_ids = {}
        rows = await db.fetch_all("SELECT id, code FROM roles")
        for row in rows:
            role_ids[row["code"]] = row["id"]

        perm_ids = {}
        rows = await db.fetch_all("SELECT id, code FROM permissions")
        for row in rows:
            perm_ids[row["code"]] = row["id"]

        role_perm_map = {
            "admin": [p["code"] for p in permissions_seed],
            "yunwei": [
                "sys:auth:login",
                "sys:dashboard:view",
                "sys:monitor:view",
                "sys:message:access",
                "sys:alert:subscribe",
                "sys:notify:history",
                "sys:notify:config:view",
                "sys:notify:config:edit",
                "sys:notify:test",
                "sys:location:view",
                "sys:location:add",
                "sys:location:edit",
                "sys:location:del",
                "sys:device:list",
                "sys:device:add",
                "sys:device:edit",
                "sys:device:del",
                "sys:ssh:connect",
            ],
            "shisheng": [
                "sys:auth:login",
                "sys:dashboard:view",
                "sys:monitor:view",
                "sys:message:access",
                "sys:notify:history",
                "sys:notify:config:view",
                "sys:notify:config:edit",
                "sys:notify:test",
            ],
        }

        for role_code, perm_codes in role_perm_map.items():
            role_id = role_ids.get(role_code)
            if not role_id:
                continue
            await db.execute("DELETE FROM role_permissions WHERE role_id = $1", role_id)
            for perm_code in perm_codes:
                perm_id = perm_ids.get(perm_code)
                if not perm_id:
                    continue
                await db.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    role_id,
                    perm_id,
                )
        print("角色权限关系写入成功")

    except Exception as e:
        print(f"数据库初始化失败: {e}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(init_rbac_db())
