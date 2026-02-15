from fastapi import Depends
from app.core.security import verify_token

async def get_current_user(token_data: dict = Depends(verify_token)) -> dict:
    """
    依赖注入：获取当前用户
    从 Token 中解析用户信息。
    Token 验证逻辑由 app.core.security.verify_token 处理。
    
    Returns:
        dict: 包含用户信息的字典 (通常包含 sub, user_id 等)
    """
    return token_data
