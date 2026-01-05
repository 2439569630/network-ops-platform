from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate, OrderReviewCreate
from app.services.repair_order_service import RepairOrderService
from app.api import deps

router = APIRouter()

@router.post("/", response_model=dict)
async def create_order(
    order_in: RepairOrderCreate,
    current_user: dict = Depends(deps.get_current_user)
):
    """提交报修工单"""
    try:
        order_id = await RepairOrderService.create_order(order_in, current_user['id'])
        return {"code": 200, "message": "工单提交成功", "data": {"id": order_id}}
    except Exception as e:
        return {"code": 500, "message": f"提交失败: {str(e)}"}

@router.get("/", response_model=dict)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    status: Optional[str] = None,
    current_user: dict = Depends(deps.get_current_user)
):
    """获取工单列表"""
    try:
        result = await RepairOrderService.get_order_list(
            page=page, 
            page_size=page_size, 
            status=status,
            user_id=current_user['id'],
            role_level=current_user.get('permission_level', 2)
        )
        return {"code": 200, "data": result}
    except Exception as e:
        return {"code": 500, "message": f"获取列表失败: {str(e)}"}

@router.get("/{id}", response_model=dict)
async def get_order(
    id: int,
    current_user: dict = Depends(deps.get_current_user)
):
    """获取工单详情"""
    try:
        order = await RepairOrderService.get_order_detail(id)
        if not order:
            return {"code": 404, "message": "工单不存在"}
        
        # Permission check: Submitter, Admin, or Maintenance
        if current_user['permission_level'] == 2 and order['submitter_id'] != current_user['id']:
             return {"code": 403, "message": "无权查看此工单"}
             
        return {"code": 200, "data": order}
    except Exception as e:
        return {"code": 500, "message": f"获取详情失败: {str(e)}"}

@router.post("/{id}/assign", response_model=dict)
async def assign_order(
    id: int,
    assignee_id: int = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user)
):
    """派发工单 (管理员)"""
    if current_user['permission_level'] > 1: # Only Admin/SuperAdmin
        return {"code": 403, "message": "权限不足"}
        
    try:
        update_data = RepairOrderUpdate(status="processing", assignee_id=assignee_id)
        await RepairOrderService.update_order(id, update_data, current_user['id'])
        return {"code": 200, "message": "派单成功"}
    except Exception as e:
        return {"code": 500, "message": f"派单失败: {str(e)}"}

@router.post("/{id}/accept", response_model=dict)
async def accept_order(
    id: int,
    current_user: dict = Depends(deps.get_current_user)
):
    """接单 (维修人员)"""
    if current_user['permission_level'] != 1: # Only Maintenance
        return {"code": 403, "message": "权限不足"}
        
    try:
        update_data = RepairOrderUpdate(status="processing", assignee_id=current_user['id'])
        await RepairOrderService.update_order(id, update_data, current_user['id'])
        return {"code": 200, "message": "接单成功"}
    except Exception as e:
        return {"code": 500, "message": f"接单失败: {str(e)}"}

@router.post("/{id}/complete", response_model=dict)
async def complete_order(
    id: int,
    remark: str = Body(None, embed=True),
    current_user: dict = Depends(deps.get_current_user)
):
    """完成工单"""
    # Only Assignee or Admin can complete
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}
        
    if current_user['permission_level'] == 2:
        return {"code": 403, "message": "权限不足"}
        
    if current_user['permission_level'] == 1 and order.get('assignee_id') != current_user['id']:
         return {"code": 403, "message": "只能完成指派给自己的工单"}

    try:
        update_data = RepairOrderUpdate(status="completed")
        await RepairOrderService.update_order(id, update_data, current_user['id'])
        # Log remark if any
        if remark:
            await RepairOrderService.log_action(id, current_user['id'], "remark", "completed", "completed", remark)
            
        return {"code": 200, "message": "工单已完成"}
    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

@router.post("/{id}/cancel", response_model=dict)
async def cancel_order(
    id: int,
    reason: str = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user)
):
    """取消工单"""
    order = await RepairOrderService.get_order_detail(id)
    if not order:
        return {"code": 404, "message": "工单不存在"}
        
    # Submitter can cancel if pending; Admin can cancel anytime
    if current_user['permission_level'] == 2:
        if order['submitter_id'] != current_user['id']:
            return {"code": 403, "message": "无权操作"}
        if order['status'] != 'pending':
            return {"code": 400, "message": "工单已在处理中，无法取消"}
            
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
    current_user: dict = Depends(deps.get_current_user)
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
        return {"code": 200, "message": "评价成功"}
    except Exception as e:
        return {"code": 500, "message": f"评价失败: {str(e)}"}
