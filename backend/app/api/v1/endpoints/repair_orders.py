from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate, OrderReviewCreate
from app.services.repair_order_service import RepairOrderService
from app.core.security import user_is_super, user_has_role, PermissionChecker
from app.services.notification_service import NotificationService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=dict)
async def create_order(
    order_in: RepairOrderCreate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:create"]))
):
    """提交报修工单"""
    try:
        order_id = await RepairOrderService.create_order(order_in, current_user['id'])
        try:
            await NotificationService.notify_repair_order_submitted(
                order_id=int(order_id),
                title=str(order_in.title or "").strip(),
                priority=str(order_in.priority or "").strip(),
                submitter_id=int(current_user["id"]),
                submitter_name=current_user.get("username") or current_user.get("name"),
                device_id=order_in.device_id,
            )
        except Exception as e:
            logger.error(f"发布工单提交通知失败: {e}")
        return {"code": 200, "message": "工单提交成功", "data": {"id": order_id}}
    except Exception as e:
        return {"code": 500, "message": f"提交失败: {str(e)}"}

@router.get("/", response_model=dict)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    status: Optional[str] = None,
    current_user: dict = Depends(PermissionChecker(["sys:repair:view"]))
):
    """获取工单列表"""
    try:
        role_level = 0 if user_is_super(current_user) else (1 if user_has_role(current_user, "yunwei") else 2)
        result = await RepairOrderService.get_order_list(
            page=page, 
            page_size=page_size, 
            status=status,
            user_id=current_user['id'],
            role_level=role_level
        )
        return {"code": 200, "data": result}
    except Exception as e:
        return {"code": 500, "message": f"获取列表失败: {str(e)}"}

@router.get("/assignees", response_model=dict)
async def list_assignees(current_user: dict = Depends(PermissionChecker(["sys:repair:manage"]))):
    try:
        users = await RepairOrderService.list_assignees()
        return {"code": 200, "data": users}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}

@router.get("/{id}", response_model=dict)
async def get_order(
    id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:view"]))
):
    """获取工单详情"""
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
        
        role = 0 if user_is_super(current_user) else (1 if user_has_role(current_user, "yunwei") else 2)
        uid = current_user.get("id")
        if role == 0:
            return {"code": 200, "data": order}

        if order.get("submitter_id") == uid:
            return {"code": 200, "data": order}

        if role == 1:
            if order.get("assignee_id") == uid:
                return {"code": 200, "data": order}
            if order.get("status") == "pending" and order.get("assignee_id") is None:
                return {"code": 200, "data": order}
            return {"code": 403, "message": "无权查看此工单"}

        return {"code": 403, "message": "无权查看此工单"}
             
    except Exception as e:
        return {"code": 500, "message": f"获取详情失败: {str(e)}"}

@router.post("/{id}/assign", response_model=dict)
async def assign_order(
    id: int,
    assignee_id: Optional[int] = Body(None, embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:manage"]))
):
    """派发工单 (管理员)，assignee_id 为空则自动派单"""
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
        if order.get("status") != "pending":
            return {"code": 400, "message": "仅待受理工单可派单"}

        target_assignee_id = assignee_id
        auto_assign = False
        if not target_assignee_id:
            auto_assign = True
            target_assignee_id = await RepairOrderService.pick_auto_assignee_id()
            if not target_assignee_id:
                return {"code": 400, "message": "暂无可用维修人员"}

        update_data = RepairOrderUpdate(status="processing", assignee_id=target_assignee_id)
        await RepairOrderService.update_order(id, update_data, current_user["id"])
        if auto_assign:
            await RepairOrderService.log_action(
                id,
                current_user["id"],
                "auto_assign",
                "pending",
                "processing",
                f"自动派单给用户ID: {target_assignee_id}",
            )
        return {"code": 200, "message": "派单成功"}
    except Exception as e:
        return {"code": 500, "message": f"派单失败: {str(e)}"}

@router.post("/{id}/accept", response_model=dict)
async def accept_order(
    id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:handle"]))
):
    """接单 (维修人员)"""
    if not user_has_role(current_user, "yunwei"):
        return {"code": 403, "message": "权限不足"}
        
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
        if order.get("status") != "pending":
            return {"code": 400, "message": "仅待受理工单可接单"}
        if order.get("assignee_id") is not None and order.get("assignee_id") != current_user["id"]:
            return {"code": 403, "message": "该工单已被指派"}

        update_data = RepairOrderUpdate(status="processing", assignee_id=current_user["id"])
        await RepairOrderService.update_order(id, update_data, current_user["id"])
        await RepairOrderService.log_action(id, current_user["id"], "accept", "pending", "processing", "接单")
        return {"code": 200, "message": "接单成功"}
    except Exception as e:
        return {"code": 500, "message": f"接单失败: {str(e)}"}

@router.post("/{id}/complete", response_model=dict)
async def complete_order(
    id: int,
    remark: str = Body(None, embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:handle", "sys:repair:manage"]))
):
    """完成工单"""
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}

    if order.get("status") != "processing":
        return {"code": 400, "message": "仅处理中工单可完成"}
        
    is_super = user_is_super(current_user)
    is_maint = user_has_role(current_user, "yunwei")
    if not (is_super or is_maint):
        return {"code": 403, "message": "权限不足"}
        
    if is_maint and (not is_super) and order.get('assignee_id') != current_user['id']:
         return {"code": 403, "message": "只能完成指派给自己的工单"}

    try:
        update_data = RepairOrderUpdate(status="completed")
        await RepairOrderService.update_order(id, update_data, current_user['id'])
        await RepairOrderService.log_action(
            id,
            current_user["id"],
            "complete",
            "processing",
            "completed",
            (remark or "").strip(),
        )
            
        return {"code": 200, "message": "工单已完成"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

@router.post("/{id}/cancel", response_model=dict)
async def cancel_order(
    id: int,
    reason: str = Body(..., embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:create", "sys:repair:manage"]))
):
    """取消工单"""
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}

    if order.get("status") in ["closed", "cancelled"]:
        return {"code": 400, "message": "工单已结束，无法取消"}
        
    role = 0 if user_is_super(current_user) else (1 if user_has_role(current_user, "yunwei") else 2)
    uid = current_user.get("id")
    is_submitter = order.get("submitter_id") == uid
    if role == 0:
        pass
    elif is_submitter:
        if order.get("status") != "pending":
            return {"code": 400, "message": "工单已在处理中，无法取消"}
    else:
        return {"code": 403, "message": "无权操作"}
            
    try:
        update_data = RepairOrderUpdate(status="cancelled")
        await RepairOrderService.update_order(id, update_data, current_user['id'])
        await RepairOrderService.log_action(id, current_user['id'], "cancel", order['status'], "cancelled", reason)
        return {"code": 200, "message": "工单已取消"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

@router.post("/{id}/review", response_model=dict)
async def review_order(
    id: int,
    review: OrderReviewCreate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:create", "sys:repair:manage"]))
):
    """评价工单"""
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}
        
    if order['submitter_id'] != current_user['id']:
        return {"code": 403, "message": "只能评价自己的工单"}
        
    if order['status'] != 'completed':
        return {"code": 400, "message": "工单未完成，无法评价"}
        
    try:
        await RepairOrderService.submit_review(id, review)
        # Update status to closed after review
        await RepairOrderService.update_order(id, RepairOrderUpdate(status="closed"), current_user['id'])
        await RepairOrderService.log_action(
            id,
            current_user["id"],
            "review",
            "completed",
            "closed",
            (review.comment or "").strip(),
        )
        return {"code": 200, "message": "评价成功"}
    except Exception as e:
        return {"code": 500, "message": f"评价失败: {str(e)}"}
