from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional, List
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate, OrderReviewCreate
from app.services.repair_order_service import RepairOrderService
from app.core.security import user_is_super, user_has_role, PermissionChecker, user_has_permission
from app.services.notification_service import NotificationService
from app.utils.remote_image_api import RemoteImageApiError
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=dict)
async def create_order(
    order_in: RepairOrderCreate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:create", "sys:repair:manage"]))
):
    """
    提交报修工单
    
    用户提交新的报修请求。
    提交后会自动通知相关人员。
    
    Args:
        order_in: 工单创建信息 (标题、内容、优先级、关联设备等)
    """
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
    scope: Optional[str] = None,
    current_user: dict = Depends(PermissionChecker(["sys:repair:view", "sys:repair:list_all", "sys:repair:manage"]))
):
    """
    获取工单列表
    
    支持分页、状态过滤和范围筛选。
    
    权限规则：
    1. 超级管理员或拥有 sys:repair:list_all 权限者可查看所有工单。
    2. 维修人员 (sys:repair:accept 或 yunwei 角色) 可查看分配给自己的工单和待处理工单。
    3. 普通用户只能查看自己提交的工单。
    
    Args:
        page: 页码，默认 1
        page_size: 每页数量，默认 10
        status: 工单状态 (pending, processing, completed, closed, cancelled)
        scope: 范围过滤 (例如 'my' 表示只看我的，'all' 表示看所有)
    """
    try:
        # Determine view permissions
        # 1. 超级管理员或拥有 list_all 权限的用户可以查看所有工单
        can_view_all = user_is_super(current_user) or await user_has_permission(current_user, "sys:repair:manage") or await user_has_permission(current_user, "sys:repair:list_all")
        # 2. 维修人员 (拥有 accept 权限或 yunwei 角色) 可以查看分配给自己的工单
        can_view_assigned = await user_has_permission(current_user, "sys:repair:accept") or user_has_role(current_user, "yunwei")

        # 调用 Service 层获取列表，传入权限标志
        result = await RepairOrderService.get_order_list(
            page=page, 
            page_size=page_size, 
            status=status,
            user_id=current_user['id'],
            role_level=2, # Deprecated in service, pass 0 to ignore or use defaults
            scope=scope,
            can_view_all=can_view_all,
            can_view_assigned=can_view_assigned
        )
        return {"code": 200, "data": result}
    except Exception as e:
        return {"code": 500, "message": f"获取列表失败: {str(e)}"}

@router.get("/assignees", response_model=dict)
async def list_assignees(current_user: dict = Depends(PermissionChecker(["sys:repair:manage"]))):
    """
    获取可用维修人员列表
    
    返回所有拥有维修权限 (yunwei 角色) 的用户列表。
    用于管理员手动派单。
    """
    try:
        users = await RepairOrderService.list_assignees()
        return {"code": 200, "data": users}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}

@router.get("/{id}", response_model=dict)
async def get_order(
    id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:view", "sys:repair:list_all", "sys:repair:manage"]))
):
    """
    获取工单详情
    
    返回工单的详细信息，包括：
    - 基本信息 (标题、内容、状态等)
    - 关联设备
    - 工作日志 (Work Logs)
    - 图片附件
    
    权限检查同列表接口，仅允许有权查看的人员访问。
    """
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
        
        uid = current_user.get("id")
        
        # Check permissions
        can_view_all = await user_has_permission(current_user, "sys:repair:manage") or await user_has_permission(current_user, "sys:repair:list_all")
        can_view_assigned = await user_has_permission(current_user, "sys:repair:accept") or user_has_role(current_user, "yunwei")

        # 1. Submitter always has access
        if order.get("submitter_id") == uid:
            return {"code": 200, "data": order}

        # 2. Admin or Manager with list_all
        if can_view_all:
            return {"code": 200, "data": order}

        # 3. Maintenance staff
        if can_view_assigned:
            if order.get("assignee_id") == uid:
                return {"code": 200, "data": order}
            if order.get("status") == "pending" and order.get("assignee_id") is None:
                return {"code": 200, "data": order}
            return {"code": 403, "message": "无权查看此工单"}

        return {"code": 403, "message": "无权查看此工单"}
             
    except Exception as e:
        return {"code": 500, "message": f"获取详情失败: {str(e)}"}


@router.put("/{id}", response_model=dict)
async def update_order_info(
    id: int,
    data: RepairOrderUpdate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:create", "sys:repair:manage"]))
):
    try:
        order = await RepairOrderService.get_order_detail(int(id))
        if not order:
            return {"code": 404, "message": "工单不存在"}

        uid = current_user.get("id")
        if uid is None:
            return {"code": 401, "message": "未登录"}

        is_admin = await user_has_permission(current_user, "sys:repair:manage")
        if not is_admin:
            if order.get("submitter_id") != uid:
                return {"code": 403, "message": "无权编辑此工单"}
            if order.get("status") != "pending":
                return {"code": 400, "message": "仅待受理工单可编辑"}
            if order.get("assignee_id") is not None:
                return {"code": 400, "message": "工单已派单，无法编辑"}

        if data.status is not None:
            return {"code": 400, "message": "不支持通过编辑接口修改状态"}
        if data.assignee_id is not None:
            return {"code": 400, "message": "不支持通过编辑接口修改指派人"}

        payload = RepairOrderUpdate(
            title=data.title,
            description=data.description,
            priority=data.priority,
            device_id=data.device_id,
            location_id=data.location_id,
        )
        ok = await RepairOrderService.update_order(int(id), payload, int(uid), skip_log=True)
        if not ok:
            return {"code": 404, "message": "工单不存在"}

        await RepairOrderService.log_action(int(id), int(uid), "edit", str(order.get("status") or ""), str(order.get("status") or ""), "编辑工单信息")
        return {"code": 200, "message": "更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}

@router.post("/{id}/assign", response_model=dict)
async def assign_order(
    id: int,
    assignee_id: Optional[int] = Body(None, embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:manage"]))
):
    """
    派发工单 (管理员)
    
    管理员将工单指派给具体的维修人员。
    
    Args:
        id: 工单 ID
        assignee_id: 维修人员用户 ID。如果不传，系统将尝试自动派单 (负载均衡策略)。
    """
    try:
        # 1. 获取工单详情
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
        # 2. 状态检查：只有 pending (待受理) 的工单可以进行派单
        if order.get("status") != "pending":
            return {"code": 400, "message": "仅待受理工单可派单"}

        target_assignee_id = assignee_id
        auto_assign = False

        try:
            current_assignee_id = int(order.get("assignee_id")) if order.get("assignee_id") is not None else None
        except Exception:
            current_assignee_id = None
        
        # 3. 如果未指定 assignee_id，尝试自动派单
        if target_assignee_id is None:
            auto_assign = True
            if current_assignee_id is not None:
                return {"code": 200, "message": "工单已指派，无需自动派单"}
            # 调用 Service 层获取最合适的维修人员 (例如负载最小的)
            target_assignee_id = await RepairOrderService.pick_auto_assignee_id()
            if not target_assignee_id:
                return {"code": 400, "message": "暂无可用维修人员"}
        else:
            try:
                target_assignee_id = int(target_assignee_id)
            except Exception:
                return {"code": 400, "message": "无效的处理人ID"}
            if target_assignee_id <= 0:
                return {"code": 400, "message": "无效的处理人ID"}
            if current_assignee_id is not None and current_assignee_id == int(target_assignee_id):
                return {"code": 200, "message": "工单已指派给该人员"}

        # 4. 更新工单状态为 pending (待确认) 并设置 assignee
        # 注意：这里状态仍为 pending，意味着工单已指派但维修人员尚未接单 (accept)
        # 也可以设计为 assigned 状态，但目前业务逻辑复用了 pending
        update_data = RepairOrderUpdate(status="pending", assignee_id=target_assignee_id)
        
        assign_reason = "自动派单 (负载均衡)" if auto_assign else "管理员指派"
        ok = await RepairOrderService.update_order(id, update_data, current_user["id"], skip_log=True, assign_reason=assign_reason)
        if not ok:
            return {"code": 404, "message": "工单不存在"}
        
        # 5. 记录操作日志
        log_detail = f"自动派单给用户ID: {target_assignee_id} (待接单)" if auto_assign else f"指派给用户ID: {target_assignee_id} (待接单)"
        log_type = "auto_assign" if auto_assign else "assign"
        
        await RepairOrderService.log_action(
            id,
            current_user["id"],
            log_type,
            "pending",
            "pending",
            log_detail,
        )
        return {"code": 200, "message": "派单成功，等待维修人员接单"}
    except Exception as e:
        return {"code": 500, "message": f"派单失败: {str(e)}"}

@router.post("/{id}/accept", response_model=dict)
async def accept_order(
    id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:accept"]))
):
    """
    接单 (维修人员)
    
    维修人员主动领取待处理的工单。
    接单后，工单状态变更为 "processing"，且当前用户成为该工单的 assignee。
    """
    try:
        # 1. 验证工单状态和归属
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
            
        # 2. 状态检查：只能接 pending 状态的工单
        if order.get("status") != "pending":
            return {"code": 400, "message": "仅待受理工单可接单"}
            
        # 3. 归属检查：如果已经指派给其他人，当前用户无法接单
        if order.get("assignee_id") is not None and order.get("assignee_id") != current_user["id"]:
            return {"code": 403, "message": "该工单已被指派"}

        # 4. 更新工单状态为 processing (处理中) 并确认 assignee
        update_data = RepairOrderUpdate(status="processing", assignee_id=current_user["id"])
        await RepairOrderService.update_order(id, update_data, current_user["id"], skip_log=True)
        
        # 5. 记录接单日志
        await RepairOrderService.log_action(id, current_user["id"], "accept", "pending", "processing", "接单")
        return {"code": 200, "message": "接单成功"}
    except Exception as e:
        return {"code": 500, "message": f"接单失败: {str(e)}"}

@router.post("/{id}/work_logs", response_model=dict)
async def add_work_log(
    id: int,
    content: str = Body(..., embed=True),
    images: list = Body([], embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:accept"]))
):
    """
    添加工作记录 (维修人员)
    
    在维修过程中记录工作进展。
    
    Args:
        id: 工单 ID
        content: 工作记录内容
        images: 关联的图片 ID 列表 (可选)
    
    仅工单的 assignee 或管理员可添加。
    """
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
            
        # Only assignee can add logs, or admin
        can_manage = await user_has_permission(current_user, "sys:repair:manage")
        is_assignee = order.get("assignee_id") == current_user["id"]
        
        if not (can_manage or is_assignee):
            return {"code": 403, "message": "无权添加工作记录"}
            
        if order.get("status") not in ["processing"]:
            return {"code": 400, "message": "仅处理中的工单可添加工作记录"}

        await RepairOrderService.add_work_log(id, current_user["id"], content, images)
        return {"code": 200, "message": "记录添加成功"}
    except Exception as e:
        return {"code": 500, "message": f"添加失败: {str(e)}"}

@router.post("/{id}/complete", response_model=dict)
async def complete_order(
    id: int,
    remark: str = Body(None, embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:handle", "sys:repair:manage"]))
):
    """
    完成工单 (维修人员)
    
    维修人员完成维修任务后，提交完成操作。
    工单状态变更为 "completed"。
    
    Args:
        id: 工单 ID
        remark: 完成备注 (可选)
    
    仅工单的 assignee 或管理员可操作。
    """
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}

    # 1. 状态检查：只有处理中 (processing) 的工单才能被标记为完成
    if order.get("status") != "processing":
        return {"code": 400, "message": "仅处理中工单可完成"}
        
    # 2. 权限检查
    can_manage = await user_has_permission(current_user, "sys:repair:manage")
    if not can_manage:
        if order.get("assignee_id") != current_user.get("id"):
            return {"code": 403, "message": "只能完成指派给自己的工单"}

    try:
        # 3. 更新状态为 completed
        update_data = RepairOrderUpdate(status="completed")
        await RepairOrderService.update_order(id, update_data, current_user['id'], skip_log=True)
        
        # 4. 记录完成日志和备注
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
    """
    取消工单
    
    创建者或管理员可以取消未完成的工单。
    工单状态变更为 "cancelled"。
    
    Args:
        id: 工单 ID
        reason: 取消原因 (必填)
    """
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}

    if order.get("status") in ["closed", "cancelled"]:
        return {"code": 400, "message": "工单已结束，无法取消"}
        
    uid = current_user.get("id")
    can_manage = await user_has_permission(current_user, "sys:repair:manage")
    is_submitter = order.get("submitter_id") == uid
    if not can_manage:
        if not is_submitter:
            return {"code": 403, "message": "无权操作"}
        if order.get("status") not in ["pending", "processing"]:
            return {"code": 400, "message": "工单已完成或关闭，无法取消"}
            
    try:
        update_data = RepairOrderUpdate(status="cancelled")
        await RepairOrderService.update_order(id, update_data, current_user['id'], skip_log=True)
        await RepairOrderService.log_action(id, current_user['id'], "cancel", order['status'], "cancelled", reason)
        return {"code": 200, "message": "工单已取消"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}


@router.delete("/{id}", response_model=dict)
async def delete_order(
    id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:manage"]))
):
    try:
        ok = await RepairOrderService.delete_order(int(id))
        if not ok:
            return {"code": 404, "message": "工单不存在"}
        return {"code": 200, "message": "删除成功"}
    except RemoteImageApiError as e:
        http_status = getattr(e, "status_code", None)
        if http_status == 429:
            return {"code": 429, "message": str(e)}
        if http_status in (401, 403):
            return {"code": 401, "message": str(e)}
        return {"code": 500, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}

@router.post("/{id}/review", response_model=dict)
async def review_order(
    id: int,
    review: OrderReviewCreate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:create", "sys:repair:manage"]))
):
    """
    评价工单
    
    工单完成后，创建者可以对服务进行评价。
    评价后工单状态变更为 "closed" (关闭/归档)。
    
    Args:
        id: 工单 ID
        review: 评价信息 (评分、评语)
    """
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
        await RepairOrderService.update_order(id, RepairOrderUpdate(status="closed"), current_user['id'], skip_log=True)
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

@router.post("/{id}/status", response_model=dict)
async def force_update_status(
    id: int,
    status: str = Body(..., embed=True),
    remark: str = Body(None, embed=True),
    current_user: dict = Depends(PermissionChecker(["sys:repair:manage"]))
):
    """
    强制修改工单状态 (管理员)
    
    管理员手动干预工单状态。
    通常用于处理异常情况或纠正错误状态。
    
    Args:
        id: 工单 ID
        status: 目标状态
        remark: 修改备注
    """
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
            
        old_status = order.get("status")
        new_status = str(status).strip()
        
        valid_statuses = ["pending", "processing", "completed", "closed", "cancelled", "need_info"]
        if new_status not in valid_statuses:
             return {"code": 400, "message": f"无效的状态: {new_status}"}

        if old_status == new_status:
            return {"code": 200, "message": "状态未变更"}

        update_data = RepairOrderUpdate(status=new_status)
        await RepairOrderService.update_order(id, update_data, current_user['id'], skip_log=True)
        
        await RepairOrderService.log_action(
            id,
            current_user["id"],
            "update_status",
            old_status,
            new_status,
            f"管理员强制修改状态: {remark or '无'}",
        )
        return {"code": 200, "message": "状态修改成功"}
    except Exception as e:
        return {"code": 500, "message": f"修改失败: {str(e)}"}
