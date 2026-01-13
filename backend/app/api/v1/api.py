from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    users,
    devices,
    system,
    notifications,
    repair_orders,
    rbac,
    locations,
)

api_router = APIRouter()

# 认证模块 /api/v1/auth
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])

# 用户管理 /api/v1/users
api_router.include_router(users.router, prefix="/users", tags=["Users"])

# 设备管理
# 注意：前端可能仍使用 /user/device，为兼容性暂时保持该路径或在 main.py 特殊处理
# 但为了统一 API 规范，建议迁移到 /api/v1/devices
# 这里我们注册到 /devices，如果前端需要兼容，可以在 main.py 单独挂载，或者让前端改路径
api_router.include_router(devices.router, prefix="/user/device", tags=["Device"])

api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(repair_orders.router, prefix="/repair-orders", tags=["Repair"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["RBAC"])
api_router.include_router(locations.router, prefix="/locations", tags=["Locations"])
