import logging
import random
import string
import json
from fastapi import APIRouter, Depends, Response
from DataBase import PostgreSQL
from auth.security import allow_admin
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/user/role", tags=["Role Management"])
logger = logging.getLogger(__name__)

class UserRoleUpdate(BaseModel):
    user_id: int
    permission_level: int

class UserPermsUpdate(BaseModel):
    user_id: int
    permissions: List[str]

class UserCreate(BaseModel):
    username: str
    password: str
    nickname: Optional[str] = None
    permission_level: int = 2 # 默认普通用户
    permissions: Optional[List[str]] = None

class UserDelete(BaseModel):
    user_id: int

class UserStatusUpdate(BaseModel):
    user_id: int
    is_approved: bool

@router.get("/list")
async def list_users(user = Depends(allow_admin)):
    """获取所有用户及其角色 (仅管理员)"""
    sql = "SELECT id, username, nickname, permission_level, is_approved, permissions FROM users ORDER BY id"
    users = await PostgreSQL.execute(sql, fetch=True)
    return {"code": 200, "data": users}

@router.post("/update_perms")
async def update_user_perms(data: UserPermsUpdate, user = Depends(allow_admin)):
    """更新用户细粒度权限 (仅管理员)"""
    try:
        # 防止修改自己的权限导致失去管理权
        if data.user_id == user.get('id'):
             # 可以加个判断，如果去掉了管理权限则阻止，这里简单起见暂不阻止，前端做控制
             pass

        sql = "UPDATE users SET permissions = $1 WHERE id = $2"
        await PostgreSQL.execute(sql, json.dumps(data.permissions), data.user_id)
        return {"code": 200, "message": "权限修改成功"}
    except Exception as e:
        logger.error(f"修改权限失败: {e}")
        return {"code": 500, "message": str(e)}

@router.post("/update")
async def update_user_role(data: UserRoleUpdate, user = Depends(allow_admin)):
    """更新用户角色 (仅管理员)"""
    try:
        # 防止修改自己的权限导致失去管理权
        if data.user_id == user.get('id'):
             return {"code": 400, "message": "不能修改自己的权限等级"}

        sql = "UPDATE users SET permission_level = $1 WHERE id = $2"
        await PostgreSQL.execute(sql, data.permission_level, data.user_id)
        return {"code": 200, "message": "权限修改成功"}
    except Exception as e:
        logger.error(f"修改权限失败: {e}")
        return {"code": 500, "message": str(e)}

@router.post("/create")
async def create_user(data: UserCreate, user = Depends(allow_admin)):
    """创建新用户 (仅管理员)"""
    try:
        # 检查用户名是否已存在
        check_sql = "SELECT id FROM users WHERE username = $1"
        exists = await PostgreSQL.execute(check_sql, data.username, fetch_val=True)
        if exists:
            return {"code": 400, "message": "用户名已存在"}

        sql = """
            INSERT INTO users (username, password, nickname, permission_level, is_approved, permissions)
            VALUES ($1, $2, $3, $4, true, $5)
        """
        # 如果没有昵称，默认使用用户名
        nickname = data.nickname if data.nickname else data.username
        
        # 默认权限：如果是普通用户，赋予基本查看权限
        perms = data.permissions
        if perms is None:
            if data.permission_level == 2:
                perms = ["sys:monitor:view", "sys:device:list"]
            elif data.permission_level == 1:
                 perms = [
                    "sys:monitor:view",
                    "sys:device:list", "sys:device:add", "sys:device:edit", "sys:device:del",
                    "sys:ssh:connect",
                    "sys:user:view"
                ]
            else:
                 perms = [] # 超管或未定义，暂时给空，后续逻辑可能依赖 permission_level=0 绕过检查

        await PostgreSQL.execute(sql, data.username, data.password, nickname, data.permission_level, json.dumps(perms))
        return {"code": 200, "message": "用户创建成功"}
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        return {"code": 500, "message": str(e)}

@router.post("/delete")
async def delete_user(data: UserDelete, user = Depends(allow_admin)):
    """删除用户 (仅管理员)"""
    try:
        if data.user_id == user.get('id'):
             return {"code": 400, "message": "不能删除自己"}

        sql = "DELETE FROM users WHERE id = $1"
        await PostgreSQL.execute(sql, data.user_id)
        return {"code": 200, "message": "用户删除成功"}
    except Exception as e:
        logger.error(f"删除用户失败: {e}")
        return {"code": 500, "message": str(e)}

@router.post("/status")
async def update_user_status(data: UserStatusUpdate, user = Depends(allow_admin)):
    """封禁/解封用户 (仅管理员)"""
    try:
        if data.user_id == user.get('id'):
             return {"code": 400, "message": "不能封禁自己"}

        sql = "UPDATE users SET is_approved = $1 WHERE id = $2"
        await PostgreSQL.execute(sql, data.is_approved, data.user_id)
        return {"code": 200, "message": "状态更新成功"}
    except Exception as e:
        logger.error(f"更新用户状态失败: {e}")
        return {"code": 500, "message": str(e)}

@router.post("/batch_create")
async def batch_create_users(count: int = 5, user = Depends(allow_admin)):
    """一键生成测试用户 (仅管理员)"""
    try:
        if count > 20:
            return {"code": 400, "message": "一次最多生成20个用户"}
            
        created_count = 0
        for i in range(count):
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            username = f"user_{random_suffix}"
            password = "password123"
            nickname = f"Test User {random_suffix}"
            
            # 检查重复 (虽然概率低)
            check_sql = "SELECT id FROM users WHERE username = $1"
            if await PostgreSQL.execute(check_sql, username, fetch_val=True):
                continue
                
            sql = """
                INSERT INTO users (username, password, nickname, permission_level, is_approved)
                VALUES ($1, $2, $3, 2, true)
            """
            await PostgreSQL.execute(sql, username, password, nickname)
            created_count += 1
            
        return {"code": 200, "message": f"成功生成 {created_count} 个用户", "data": {"count": created_count}}
    except Exception as e:
        logger.error(f"批量创建用户失败: {e}")
        return {"code": 500, "message": str(e)}

