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

router = APIRouter()


async def _user_can_subscribe_device(*, user: dict, device_id: int) -> bool:
    if user_is_super(user):
        return True
    uid = user.get("id")
    if uid is None:
        return False
    dev = await NetworkDevice.filter(id=int(device_id)).first()
    if not dev:
        return False
    if str(dev.created_by or "").strip() == str(uid):
        return True

    mapping = await LocationNodeDevice.filter(device_id=int(device_id)).first()
    if not mapping:
        return False
    node_id = int(mapping.node_id)

    if await LocationNodeUser.filter(node_id=node_id, user_id=int(uid)).exists():
        return True

    role_ids = await LocationNodeRole.filter(node_id=node_id).values_list("role_id", flat=True)
    if not role_ids:
        return False
    user_role_ids = await UserRole.filter(user_id=int(uid), role_id__in=list(role_ids)).exists()
    return bool(user_role_ids)


async def _user_can_subscribe_location(*, user: dict, node_id: int) -> bool:
    if user_is_super(user):
        return True
    uid = user.get("id")
    if uid is None:
        return False
    if await LocationNodeUser.filter(node_id=int(node_id), user_id=int(uid)).exists():
        return True
    role_ids = await LocationNodeRole.filter(node_id=int(node_id)).values_list("role_id", flat=True)
    if not role_ids:
        return False
    return await UserRole.filter(user_id=int(uid), role_id__in=list(role_ids)).exists()

@router.get("/statistics")
async def get_alert_statistics(
    user: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    """获取过去7天的告警统计数据"""
    end_dt = datetime.now()
    start_dt = (end_dt - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_exclusive = (end_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_map: Dict[str, Dict[str, int]] = {}
    x_axis_data: List[str] = []
    for i in range(7):
        current_date = start_dt + timedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        date_map[date_str] = {"critical": 0, "warning": 0, "info": 0}
        x_axis_data.append(week_days[current_date.weekday()])

    try:
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

    for r in rows:
        day = str(r.get("day") or "")
        sev = str(r.get("severity") or "")
        cnt = int(r.get("cnt") or 0)
        if day in date_map and sev in date_map[day]:
            date_map[day][sev] += cnt

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
    """获取设备的告警规则列表"""
    rules = await DeviceAlertRule.filter(device_id=device_id).all()
    return rules

@router.post("/rules", response_model=AlertRuleOut)
async def create_device_alert_rule(
    rule_in: AlertRuleCreate,
    user: dict = Depends(PermissionChecker(["sys:device:edit"]))
):
    """创建告警规则"""
    # 检查是否已存在相同规则
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
    
    # 刷新监控进程缓存
    await AlertService.notify_rule_change(rule_in.device_id)
    
    return rule

@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_device_alert_rule(
    rule_id: int,
    rule_in: AlertRuleUpdate,
    user: dict = Depends(PermissionChecker(["sys:device:edit"]))
):
    """更新告警规则"""
    rule = await DeviceAlertRule.get_or_none(id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    uid = int(user.get("id"))
    if not user_is_super(user):
        dev = await NetworkDevice.filter(id=int(rule.device_id)).first()
        device_owner = str(dev.created_by or "").strip() if dev else ""
        rule_owner = str(getattr(rule, "created_by", "") or "").strip()
        if str(uid) != device_owner and str(uid) != rule_owner:
            raise HTTPException(status_code=403, detail="无权修改该规则")

    payload = rule_in.model_dump(exclude_unset=True)
    metric_after = str(payload.get("metric") or rule.metric or "").strip()
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
    """删除告警规则"""
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
    """获取设备告警记录"""
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
    uid = int(user.get("id"))
    st = str(data.scope_type)
    sid = int(data.scope_id)
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
    uid = int(user.get("id"))
    deleted = await AlertSubscription.filter(id=int(subscription_id), subscriber_user_id=uid).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {"code": 200, "message": "删除成功"}
