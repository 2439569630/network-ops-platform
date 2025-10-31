import logging
from typing import Optional

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.params import Cookie

from  auth import jwtTools as jwt

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
logger = logging.getLogger(__name__)




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
        return jwt.verify_token(token)
    except Exception as e:
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
#     )
