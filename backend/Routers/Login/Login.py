from fastapi import APIRouter
import asyncio
from pydantic import BaseModel


router = APIRouter()

#登录表单
class LoginForm(BaseModel):
    username: str
    password: str

@router.post("/login")
async def read_users():
    return {
        "status": "success",
        "message": "登录成功"

    }