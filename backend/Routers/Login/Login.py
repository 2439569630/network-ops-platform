from fastapi import APIRouter
import asyncio
from pydantic import BaseModel
from DataBase import PostgreSQL
from DataBase.Redis import RedisManager

router = APIRouter()

#登录表单
class LoginForm(BaseModel):
    username: str
    password: str

@router.post("/login")
async def read_users():
    Redis = await RedisManager().get_redis()
    await Redis.set('qqq', 'www')

    print(await Redis.get('qqq'))
    return {
        "status": "success",
        "message": "登录成功"

    }