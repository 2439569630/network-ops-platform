from fastapi import Depends
from app.core.security import verify_token

async def get_current_user(token_data: dict = Depends(verify_token)) -> dict:
    """
    Dependency to get the current user from the token.
    The token verification logic is handled by app.core.security.verify_token.
    """
    return token_data
