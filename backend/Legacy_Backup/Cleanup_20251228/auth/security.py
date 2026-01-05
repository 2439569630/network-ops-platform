import logging
from typing import Optional

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.params import Cookie

from  auth import jwtTools as jwt

from fastapi import HTTPException, Request, WebSocket, Query
from fastapi.responses import JSONResponse
logger = logging.getLogger(__name__)


async def verify_token_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket 鉴权依赖
    """
    if token is None:
        # 尝试从 Cookie 获取 (如果 ws 握手带了 cookie)
        token = websocket.cookies.get("token")

    if token is None:
        await websocket.close(code=4001, reason="未登录")
        return None

    try:
        payload = jwt.verify_token(token)
        if isinstance(payload, dict) and "code" in payload:
             await websocket.close(code=4001, reason=payload.get("message", "Token无效"))
             return None
        return payload
    except Exception as e:
        logger.error(f"WS Token验证异常: {e}")
        await websocket.close(code=4001, reason="身份验证失败")
        return None



# def verify_token(token: str = Cookie(None)):
#     if token is None:
#         raise HTTPException(
#             status_code=401,
#             detail={"code": 401, "message": "未登录"}
#         )
#
#     try:
#         return jwt.verify_token(token)  # 成功时直接返回用户数据
#     except Exception as e:
#         logger.error(f"验证token失败: {e}")
#         raise HTTPException(
#             status_code=401,
#             detail={"code": 401, "message": "身份验证失败"}
#         )


class UnicornException(Exception):
    def __init__(self, code: int, message: str):

        """
        初始化独角兽异常类

        参数:
            code: 错误代码，用于标识具体的错误类型
            message: 错误信息，用于描述具体的错误内容
        """
        self.code = code  # 设置错误代码属性
        self.message = message  # 设置错误信息属性
        self.status = "error"  # 设置状态属性，固定为"error"


# 定义异常处理器函数（但不使用装饰器）
def unicorn_exception_handler(request: Request, exc: UnicornException):
    return JSONResponse(
        status_code=exc.code,
        content={
            "code": exc.code,
            "status": exc.status,
            "message": exc.message
        }
    )


def verify_token(token: str = Cookie(None)):
    if token is None:
        raise UnicornException(401, "未登录")

    try:
        # 你的验证逻辑
        payload = jwt.verify_token(token)
        # 检查是否返回了错误信息（通过检测是否包含 code 字段且不为 200）
        # 注意：正常的 payload 不应该包含 code 字段，或者如果包含则必须为 200
        if isinstance(payload, dict) and "code" in payload:
             # 如果是错误字典
             raise UnicornException(payload["code"], payload.get("message", "Token无效"))
        
        return payload
    except UnicornException as ue:
        raise ue
    except Exception as e:
        logger.error(f"Token验证异常: {e}")
        raise UnicornException(401, "身份验证失败")


# # 新增 Pydantic 验证错误处理器
# def validation_exception_handler(request: Request, exc: RequestValidationError):
#     # 提取第一个错误信息（通常是最相关的）
#     first_error = exc.errors()[0] if exc.errors() else {}
#     error_type = first_error.get('type', 'validation_error')
#     error_loc = "->".join(str(loc) for loc in first_error.get('loc', []))
#     error_msg = first_error.get('msg', '验证错误')
#
#     # 自定义错误消息
#     custom_messages = {
#         'missing': f"缺少必要参数: {error_loc}",
#         'value_error': f"参数值错误: {error_loc}",
#         'type_error': f"参数类型错误: {error_loc}"
#     }
#
#     message = custom_messages.get(error_type, f"参数错误: {error_msg}")
#
#     return JSONResponse(
#         status_code=400,
#         content={
#             "code": 400,
#             "status": "error",
#             "message": message
#         }
from fastapi import Depends
class RoleChecker:
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(verify_token)):
        user_role = user.get("permission_level")
        if user_role not in self.allowed_roles:
             raise UnicornException(403, "权限不足")
        return user

class PermissionChecker:
    def __init__(self, required_perm: str):
        self.required_perm = required_perm

    def __call__(self, user: dict = Depends(verify_token)):
        # 1. 超级管理员 (Level 0) 拥有所有权限，直接放行
        # 注意：这取决于业务需求，通常超管绕过检查
        if user.get("permission_level") == 0:
            return user
            
        # 2. 检查权限列表
        permissions = user.get("permissions", [])
        if self.required_perm not in permissions:
             raise UnicornException(403, f"权限不足，缺少权限: {self.required_perm}")
        
        return user

# 常用权限依赖
allow_admin = RoleChecker([0]) # 仅超级管理员
allow_operator = RoleChecker([0, 1]) # 运维及以上

