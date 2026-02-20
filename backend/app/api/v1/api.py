# -*- coding: utf-8 -*-
#
# API 路由注册模块 (v1 版本)
#
# 此模块负责聚合所有 v1 版本的 API 路由。
# 它将各个功能模块（如认证、用户、设备等）的 Router 注册到主 APIRouter 中。
# 这样做的好处是可以将不同功能的 API 拆分到不同的文件中，保持代码结构清晰。
#
from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,           # 认证相关接口 (登录/注册/Token)
    users,          # 用户管理接口 (CRUD)
    devices,        # 设备管理接口 (列表/详情/配置)
    dashboard,      # 系统概览 WS
    system,         # 系统管理接口 (配置/审计)
    notifications,  # 通知中心接口 (站内信/邮件)
    repair_orders,  # 报修工单接口 (工单流程)
    repair_images,  # 报修图片接口 (图片上传/管理)
    rbac,           # 角色权限接口 (RBAC 模型)
    locations,      # 位置管理接口 (区域树)
    alerts,         # 告警管理接口 (规则/日志)
    config_push,    # 配置下发接口 (批量配置)
)

# 创建 API 路由实例，作为 v1 API 的根路由
api_router = APIRouter()

# --- 注册各个子模块的路由 ---

# 认证模块
# 处理登录、注册、密码重置、Token 刷新等操作
# 路由前缀: /auth
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])

# 用户管理模块
# 处理用户的增删改查、个人信息更新、头像上传等
# 路由前缀: /users
api_router.include_router(users.router, prefix="/users", tags=["Users"])

# 设备管理模块
# 处理网络设备的列表查询、详情查看、SSH连接、配置查看等
# 注意：为了兼容旧版前端代码，这里使用了 /user/device 作为前缀
# 建议在未来版本中迁移到更规范的 /devices 前缀
api_router.include_router(devices.router, prefix="/user/device", tags=["Device"])

# 设备告警模块
# 处理设备告警规则的配置、告警日志的查询、告警订阅等
# 路由前缀: /user/device/alerts (作为设备管理的子模块)
api_router.include_router(alerts.router, prefix="/user/device/alerts", tags=["Device Alerts"])

# 系统概览模块
# 路由前缀: /dashboard
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# 系统管理模块
# 处理系统全局配置、审计日志查询等管理功能
# 路由前缀: /system
api_router.include_router(system.router, prefix="/system", tags=["System"])

# 通知模块
# 处理站内信、邮件通知配置、消息推送等
# 路由前缀: /notifications
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# 报修工单模块
# 处理故障报修的全流程（提交、派单、接单、维修、验收）
# 路由前缀: /repair-orders
api_router.include_router(repair_orders.router, prefix="/repair-orders", tags=["Repair"])

# 报修图片模块
# 专门处理报修流程中的图片上传和管理，支持本地存储或远程存储
# 路由前缀: /repair-images
api_router.include_router(repair_images.router, prefix="/repair-images", tags=["Repair Images"])

# 角色权限管理 (RBAC) 模块
# 处理角色定义、权限分配、用户角色绑定等安全控制逻辑
# 路由前缀: /rbac
api_router.include_router(rbac.router, prefix="/rbac", tags=["RBAC"])

# 位置管理模块
# 处理设备所在的物理位置或逻辑区域（如校区/楼栋/机房）的树形结构管理
# 路由前缀: /locations
api_router.include_router(locations.router, prefix="/locations", tags=["Locations"])

# 配置推送模块
# 处理对网络设备的批量配置下发任务，支持模板和即时命令
# 路由前缀: /config-push
api_router.include_router(config_push.router, prefix="/config-push", tags=["Config Push"])
