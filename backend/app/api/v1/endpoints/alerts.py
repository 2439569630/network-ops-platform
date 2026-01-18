from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import PermissionChecker
from app.models.orm.alert import DeviceAlertRule, DeviceAlertLog
from app.schemas.alert import AlertRuleCreate, AlertRuleUpdate, AlertRuleOut, AlertLogOut
from app.workers.monitor.manager import MonitorManager

router = APIRouter()

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
        
    rule = await DeviceAlertRule.create(**rule_in.model_dump())
    
    # 刷新监控进程缓存
    monitor = MonitorManager()
    await monitor.refresh_alert_rules(rule_in.device_id)
    
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
        
    await rule.update_from_dict(rule_in.model_dump(exclude_unset=True))
    await rule.save()
    
    # 刷新监控进程缓存
    monitor = MonitorManager()
    await monitor.refresh_alert_rules(rule.device_id)
    
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
    
    device_id = rule.device_id
    await rule.delete()
    
    # 刷新监控进程缓存
    monitor = MonitorManager()
    await monitor.refresh_alert_rules(device_id)
    
    return {"code": 200, "message": "删除成功"}

@router.get("/logs/{device_id}", response_model=List[AlertLogOut])
async def get_device_alert_logs(
    device_id: int,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(PermissionChecker(["sys:device:list"]))
):
    """获取设备告警记录"""
    logs = await DeviceAlertLog.filter(device_id=device_id)\
        .order_by("-triggered_at")\
        .offset(offset)\
        .limit(limit)\
        .all()
    return logs
