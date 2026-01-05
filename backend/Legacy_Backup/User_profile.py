import logging
from fastapi import APIRouter, Depends
from DataBase import PostgreSQL
from auth.security import verify_token
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/user/profile", tags=["User Profile"])
logger = logging.getLogger(__name__)

class ProfileUpdate(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

@router.get("/info")
async def get_profile(user = Depends(verify_token)):
    """获取当前用户信息"""
    user_id = user.get('id')
    sql = """
        SELECT id, username, nickname, email, permission_level, created_at
        FROM users
        WHERE id = $1
    """
    profile = await PostgreSQL.execute(sql, user_id, fetch_row=True)
    
    if not profile:
        return {"code": 404, "message": "用户不存在"}
        
    return {"code": 200, "data": dict(profile)}

@router.post("/update")
async def update_profile(data: ProfileUpdate, user = Depends(verify_token)):
    """更新用户信息"""
    user_id = user.get('id')
    
    try:
        # 1. 如果要修改密码
        if data.new_password:
            if not data.old_password:
                 return {"code": 400, "message": "修改密码需要提供旧密码"}
            
            # 验证旧密码
            auth_sql = "SELECT id FROM users WHERE id = $1 AND password = $2"
            valid = await PostgreSQL.execute(auth_sql, user_id, data.old_password, fetch_val=True)
            if not valid:
                return {"code": 400, "message": "旧密码错误"}
                
            # 更新密码
            await PostgreSQL.execute("UPDATE users SET password = $1 WHERE id = $2", data.new_password, user_id)
            
        # 2. 更新基础信息 (nickname, email)
        updates = []
        values = []
        idx = 1
        
        if data.nickname is not None:
            updates.append(f"nickname = ${idx}")
            values.append(data.nickname)
            idx += 1
            
        if data.email is not None:
            updates.append(f"email = ${idx}")
            values.append(data.email)
            idx += 1
            
        if updates:
            values.append(user_id)
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ${idx}"
            await PostgreSQL.execute(sql, *values)
        
    except Exception as e:
        logger.error(f"更新个人信息失败: {e}")
        return {"code": 500, "message": str(e)}
        
    return {"code": 200, "message": "更新成功"}
