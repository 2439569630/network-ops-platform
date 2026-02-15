# -*- coding: utf-8 -*-
#
# 设备告警 API 接口
#
# 此模块负责处理与设备告警相关的所有 HTTP 请求，包括：
# 1. 告警规则管理（增删改查）
# 2. 告警日志查询（支持多种条件过滤）
# 3. 告警订阅管理（订阅设备/位置/规则的告警通知）
# 4. 告警统计数据（用于仪表盘展示）
#

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from tortoise.exceptions import IntegrityError
from app.core.security import PermissionChecker, user_is_super
from app.core.config import settings
from app.core.database import db
from app.models.orm.alert import DeviceAlertRule, DeviceAlertLog
from app.models.orm.device import NetworkDevice
from app.models.orm.location import LocationNodeDevice, LocationNodeRole, LocationNodeUser
from app.models.orm.rbac import UserRole
from app.schemas.alert import (
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleOut,
    AlertLogOut,
    AlertLogPagination,
    AlertSubscriptionCreate,
    AlertSubscriptionUpdate,
    AlertSubscriptionOut,
)
from app.models.orm.alert import AlertSubscription
from app.services.alert_service import AlertService

# 创建 API 路由实例
router = APIRouter()


async def _user_can_subscribe_device(*, user: dict, device_id: int) -> bool:
    """
    检查用户是否有权限订阅指定设备的告警。
    
    权限判定逻辑：
    1. 超级管理员拥有所有权限。
    2. 如果用户是设备的创建者，允许订阅。
    3. 如果设备属于某个位置节点，且用户在该位置节点有直接绑定关系，允许订阅。
    4. 如果设备属于某个位置节点，该节点绑定了某些角色，且用户拥有这些角色之一，允许订阅。
    
    Args:
        user: 当前用户信息字典
        device_id: 目标设备ID
        
    Returns:
        bool: 是否允许订阅
    """
    if user_is_super(user):
        return True
    uid = user.get("id")
    if uid is None:
        return False
    
    # 1. 检查设备是否存在
    dev = await NetworkDevice.filter(id=int(device_id)).first()
    if not dev:
        return False
        
    # 2. 检查创建者权限
    # 设备创建者默认拥有对该设备的所有权限，包括订阅告警
    if str(dev.created_by or "").strip() == str(uid):
        return True

    # 3. 检查基于位置的权限
    # 获取设备所属的位置节点
    mapping = await LocationNodeDevice.filter(device_id=int(device_id)).first()
    if not mapping:
        # 如果设备未绑定任何位置，且用户不是创建者/超管，则无权访问
        return False
    node_id = int(mapping.node_id)

    # 3.1 检查用户是否直接绑定到该位置 (LocationNodeUser)
    # 系统允许将用户直接分配给某个位置，从而获得该位置下所有设备的权限
    if await LocationNodeUser.filter(node_id=node_id, user_id=int(uid)).exists():
        return True

    # 3.2 检查用户是否拥有该位置绑定的角色 (LocationNodeRole)
    # 获取该位置绑定的所有角色 ID
    role_ids = await LocationNodeRole.filter(node_id=node_id).values_list("role_id", flat=True)
    if not role_ids:
        return False
        
    # 检查用户是否拥有上述任意一个角色
    # 这是 RBAC 与位置权限的结合点：用户 -> 角色 -> 位置 -> 设备
    user_role_ids = await UserRole.filter(user_id=int(uid), role_id__in=list(role_ids)).exists()
    return bool(user_role_ids)


async def _user_can_subscribe_location(*, user: dict, node_id: int) -> bool:
    """
    检查用户是否有权限订阅指定位置的告警。
    
    权限判定逻辑与设备类似，主要检查用户是否直接或间接（通过角色）关联到该位置。
    
    Args:
        user: 当前用户信息字典
        node_id: 目标位置节点ID
        
    Returns:
        bool: 是否允许订阅
    """
    if user_is_super(user):
        return True
    uid = user.get("id")
    if uid is None:
        return False
        
    # 1. 检查用户是否直接绑定到该位置
    # 直接绑定关系优先级最高
    if await LocationNodeUser.filter(node_id=int(node_id), user_id=int(uid)).exists():
        return True
        
    # 2. 检查用户是否拥有该位置绑定的角色
    # 如果位置通过角色授权（例如"北京运维组"角色绑定了"北京机房"位置），
    # 那么拥有"北京运维组"角色的用户自动获得该位置权限
    role_ids = await LocationNodeRole.filter(node_id=int(node_id)).values_list("role_id", flat=True)
    if not role_ids:
        return False
    return await UserRole.filter(user_id=int(uid), role_id__in=list(role_ids)).exists()

@router.get("/statistics")
async def get_alert_statistics(
    user: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    """
    获取过去7天的告警统计数据。
    
    用于前端仪表盘展示告警趋势图。
    返回数据按日期和告警级别（严重、警告、提醒）分组。
    
    Args:
        user: 当前用户（需要 sys:device:list 权限）
        
    Returns:
        dict: 包含 xAxis（日期列表）和 series（各级别对应的数据列表）
    """
    # 1. 确定时间范围
    end_dt = datetime.now()
    # 计算7天前的起始时间（包含今天，共7天）
    # 使用 replace 确保时间从当天的 00:00:00 开始，避免因时间差异导致的数据遗漏
    start_dt = (end_dt - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    # 结束时间为明天的0点，确保覆盖今天全天
    end_exclusive = (end_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_map: Dict[str, Dict[str, int]] = {}
    x_axis_data: List[str] = []
    
    # 2. 初始化最近7天的数据结构
    # 确保即使某天没有告警，也能显示为 0，保证图表 X 轴连续
    # 这一步对于前端 ECharts 展示非常重要，否则线条会断裂或日期错位
    for i in range(7):
        current_date = start_dt + timedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        date_map[date_str] = {"critical": 0, "warning": 0, "info": 0}
        x_axis_data.append(week_days[current_date.weekday()])

    try:
        # 3. 使用原生 SQL 聚合查询
        # 按日期和严重级别分组统计告警数量
        # to_char 用于将 triggered_at 转换为日期字符串，实现按天分组
        # 使用原生 SQL 是为了性能优化，避免加载大量 ORM 对象
        rows = await db.fetch_all(
            """
            SELECT to_char(triggered_at::date, 'YYYY-MM-DD') AS day, severity, COUNT(*)::int AS cnt
            FROM device_alert_logs
            WHERE triggered_at >= $1 AND triggered_at < $2
            GROUP BY day, severity
            """,
            start_dt,
            end_exclusive,
        )
    except Exception:
        rows = []

    # 4. 填充查询结果到 map 中
    for r in rows:
        day = str(r.get("day") or "")
        sev = str(r.get("severity") or "")
        cnt = int(r.get("cnt") or 0)
        # 仅处理预期范围内的日期和级别
        if day in date_map and sev in date_map[day]:
            date_map[day][sev] += cnt

    # 5. 将 map 转换为前端 ECharts 等图表库所需的数组格式
    series_critical: List[int] = []
    series_warning: List[int] = []
    series_info: List[int] = []
    for date_str in sorted(date_map.keys()):
        counts = date_map[date_str]
        series_critical.append(int(counts.get("critical", 0)))
        series_warning.append(int(counts.get("warning", 0)))
        series_info.append(int(counts.get("info", 0)))

    return {
        "xAxis": x_axis_data,
        "series": [
            {"name": "严重", "data": series_critical},
            {"name": "警告", "data": series_warning},
            {"name": "提醒", "data": series_info}
        ]
    }

@router.get("/rules/{device_id}", response_model=List[AlertRuleOut])
async def get_device_alert_rules(
    device_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    """
    获取指定设备的告警规则列表。
    
    Args:
        device_id: 设备ID
        user: 当前用户
        
    Returns:
        List[AlertRuleOut]: 规则列表
    """
    rules = await DeviceAlertRule.filter(device_id=device_id).all()
    return rules

@router.post("/rules", response_model=AlertRuleOut)
async def create_device_alert_rule(
    rule_in: AlertRuleCreate,
    user: dict = Depends(PermissionChecker(["sys:device:edit"]))
):
    """
    创建新的告警规则。
    
    Args:
        rule_in: 规则创建参数（指标、阈值、操作符等）
        user: 当前用户
        
    Returns:
        AlertRuleOut: 创建成功的规则对象
        
    Raises:
        HTTPException: 如果规则已存在
    """
    # 检查是否已存在相同规则（同一设备、同一指标、同一操作符、同一阈值）
    exists = await DeviceAlertRule.filter(
        device_id=rule_in.device_id,
        metric=rule_in.metric,
        operator=rule_in.operator,
        threshold=rule_in.threshold
    ).exists()
    
    if exists:
        raise HTTPException(status_code=400, detail="相同的告警规则已存在")
        
    try:
        payload = rule_in.model_dump()
        payload["created_by"] = int(user.get("id"))
        rule = await DeviceAlertRule.create(**payload)
    except IntegrityError:
        raise HTTPException(status_code=400, detail="相同的告警规则已存在")
    
    # 关键步骤：刷新监控进程的规则缓存，确保新规则立即生效
    await AlertService.notify_rule_change(rule_in.device_id)
    
    return rule

@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_device_alert_rule(
    rule_id: int,
    rule_in: AlertRuleUpdate,
    user: dict = Depends(PermissionChecker(["sys:device:edit"]))
):
    """
    更新告警规则。
    
    普通用户只能修改自己创建的规则，或该设备的归属者。
    超级管理员可以修改所有规则。
    
    Args:
        rule_id: 规则ID
        rule_in: 更新参数
        
    Returns:
        AlertRuleOut: 更新后的规则
    """
    rule = await DeviceAlertRule.get_or_none(id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
        
    # 权限检查：非超管只能改自己相关设备的规则
    uid = int(user.get("id"))
    if not user_is_super(user):
        dev = await NetworkDevice.filter(id=int(rule.device_id)).first()
        device_owner = str(dev.created_by or "").strip() if dev else ""
        rule_owner = str(getattr(rule, "created_by", "") or "").strip()
        if str(uid) != device_owner and str(uid) != rule_owner:
            raise HTTPException(status_code=403, detail="无权修改该规则")

    payload = rule_in.model_dump(exclude_unset=True)
    metric_after = str(payload.get("metric") or rule.metric or "").strip()
    
    # 特殊校验：在线状态指标只能是 0 或 1
    if "threshold" in payload and metric_after == "online_status":
        try:
            v = float(payload.get("threshold"))
        except Exception:
            raise HTTPException(status_code=422, detail="online_status 的阈值必须为 0 或 1")
        if v not in (0.0, 1.0):
            raise HTTPException(status_code=422, detail="online_status 的阈值必须为 0 或 1")

    try:
        await rule.update_from_dict(payload)
        await rule.save()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="相同的告警规则已存在")
    
    # 刷新监控进程缓存
    await AlertService.notify_rule_change(rule.device_id)
    
    return rule

@router.delete("/rules/{rule_id}")
async def delete_device_alert_rule(
    rule_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:edit"]))
):
    """
    删除告警规则。
    
    Args:
        rule_id: 规则ID
        
    Returns:
        dict: 操作结果
    """
    rule = await DeviceAlertRule.get_or_none(id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
        
    uid = int(user.get("id"))
    if not user_is_super(user):
        dev = await NetworkDevice.filter(id=int(rule.device_id)).first()
        device_owner = str(dev.created_by or "").strip() if dev else ""
        rule_owner = str(getattr(rule, "created_by", "") or "").strip()
        if str(uid) != device_owner and str(uid) != rule_owner:
            raise HTTPException(status_code=403, detail="无权删除该规则")
    
    device_id = rule.device_id
    await rule.delete()
    
    # 刷新监控进程缓存
    await AlertService.notify_rule_change(device_id)
    
    return {"code": 200, "message": "删除成功"}

@router.get("/logs/{device_id}", response_model=AlertLogPagination)
async def get_device_alert_logs(
    device_id: int,
    limit: int = 50,
    offset: int = 0,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    resolved: Optional[bool] = Query(None),
    severity: Optional[str] = Query(None),
    user: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    """
    分页获取设备告警日志。
    
    支持按时间范围、解决状态、严重级别过滤。
    """
    lim = max(1, min(int(limit or 50), 200))
    off = max(0, int(offset or 0))
    query = DeviceAlertLog.filter(device_id=int(device_id))
    
    if start_time is not None:
        query = query.filter(triggered_at__gte=start_time)
    if end_time is not None:
        query = query.filter(triggered_at__lt=end_time)
    if resolved is True:
        query = query.filter(resolved_at__isnull=False)
    elif resolved is False:
        query = query.filter(resolved_at__isnull=True)
    if severity:
        query = query.filter(severity=str(severity))
        
    total = await query.count()
    logs = await query.order_by("-triggered_at")\
        .offset(off)\
        .limit(lim)\
        .all()
    return {"total": total, "items": logs}


@router.delete("/logs/purge", response_model=dict)
async def purge_device_alert_logs(
    retention_days: Optional[int] = Query(None),
    user: dict = Depends(PermissionChecker(["sys:device:edit"])),
):
    """
    清理过期的告警日志。
    
    默认使用系统配置的保留天数。
    此接口通常由定时任务调用，也可由管理员手动触发。
    """
    days = int(retention_days) if retention_days is not None else int(settings.ALERT_LOG_RETENTION_DAYS)
    days = max(1, min(days, 3650))
    cutoff = datetime.now() - timedelta(days=days)
    deleted = await DeviceAlertLog.filter(triggered_at__lt=cutoff).delete()
    return {"code": 200, "data": {"deleted": int(deleted), "retention_days": int(days)}}


@router.get("/subscriptions", response_model=List[AlertSubscriptionOut])
async def list_alert_subscriptions(
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[int] = Query(None),
    user: dict = Depends(PermissionChecker(["sys:device:list"])),
):
    """
    获取当前用户的告警订阅列表。
    
    支持按订阅范围类型（设备/位置/规则）和范围ID过滤。
    """
    uid = int(user.get("id"))
    q = AlertSubscription.filter(subscriber_user_id=uid)
    if scope_type:
        q = q.filter(scope_type=str(scope_type))
    if scope_id is not None:
        q = q.filter(scope_id=int(scope_id))
    return await q.order_by("-updated_at").all()


@router.post("/subscriptions", response_model=AlertSubscriptionOut)
async def create_alert_subscription(
    data: AlertSubscriptionCreate,
    user: dict = Depends(PermissionChecker(["sys:device:list"])),
):
    """
    创建新的告警订阅。
    
    用户可以订阅特定设备、特定位置或特定规则的告警。
    会检查用户是否有权订阅目标对象。
    """
    uid = int(user.get("id"))
    st = str(data.scope_type)
    sid = int(data.scope_id)
    
    # 权限检查
    if st == "device":
        allowed = await _user_can_subscribe_device(user=user, device_id=sid)
    elif st == "location":
        allowed = await _user_can_subscribe_location(user=user, node_id=sid)
    elif st == "rule":
        rule = await DeviceAlertRule.filter(id=sid).first()
        if not rule:
            raise HTTPException(status_code=404, detail="规则不存在")
        allowed = await _user_can_subscribe_device(user=user, device_id=int(rule.device_id))
    else:
        raise HTTPException(status_code=422, detail="不支持的 scope_type")
        
    if not allowed:
        raise HTTPException(status_code=403, detail="无权订阅该对象")

    try:
        sub = await AlertSubscription.create(
            subscriber_user_id=uid,
            scope_type=st,
            scope_id=sid,
            channels=list(data.channels or []),
            severities=list(data.severities) if data.severities is not None else None,
            is_enabled=bool(data.is_enabled),
        )
    except IntegrityError:
        raise HTTPException(status_code=400, detail="已存在相同订阅")
    return sub


@router.put("/subscriptions/{subscription_id}", response_model=AlertSubscriptionOut)
async def update_alert_subscription(
    subscription_id: int,
    data: AlertSubscriptionUpdate,
    user: dict = Depends(PermissionChecker(["sys:device:list"])),
):
    """
    更新告警订阅配置。
    
    例如修改接收渠道（邮件/站内信）或关注的告警级别。
    """
    uid = int(user.get("id"))
    sub = await AlertSubscription.filter(id=int(subscription_id), subscriber_user_id=uid).first()
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    payload = data.model_dump(exclude_unset=True)
    await sub.update_from_dict(payload)
    await sub.save()
    return sub


@router.delete("/subscriptions/{subscription_id}", response_model=dict)
async def delete_alert_subscription(
    subscription_id: int,
    user: dict = Depends(PermissionChecker(["sys:device:list"])),
):
    """取消告警订阅"""
    uid = int(user.get("id"))
    deleted = await AlertSubscription.filter(id=int(subscription_id), subscriber_user_id=uid).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {"code": 200, "message": "删除成功"}
