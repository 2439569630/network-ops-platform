from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import RedirectResponse
from typing import Optional

from app.core.security import PermissionChecker, user_has_permission, user_has_role, user_is_super
from app.schemas.repair_image import RepairImageResponse, RepairImageUpdate
from app.services.image_storage_service import ImageStorageService
from app.services.repair_image_service import RepairImageService
from app.utils.remote_image_api import RemoteImageApiError

import logging


router = APIRouter()
logger = logging.getLogger(__name__)

async def _can_view_image(img, current_user: dict) -> bool:
    if user_is_super(current_user):
        return True
    uid = int(current_user.get("id") or 0)
    if uid and int(getattr(img, "uploader_id", 0) or 0) == uid:
        return True

    if await user_has_permission(current_user, "sys:repair:manage"):
        return True

    oid = getattr(img, "order_id", None)
    if oid is None:
        return False

    from app.services.repair_order_service import RepairOrderService
    order = await RepairOrderService.get_order_detail(int(oid))
    if not order:
        return False

    can_view_all = await user_has_permission(current_user, "sys:repair:list_all") or await user_has_permission(current_user, "sys:repair:manage")
    can_view_assigned = await user_has_permission(current_user, "sys:repair:accept") or user_has_role(current_user, "yunwei")

    if int(order.get("submitter_id") or 0) == uid:
        return True
    if can_view_all:
        return True
    if can_view_assigned:
        if int(order.get("assignee_id") or 0) == uid:
            return True
        if order.get("status") == "pending" and order.get("assignee_id") is None:
            return True
    return False


@router.get("/upload_config", response_model=dict)
async def get_upload_config(
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:add", "sys:repair:create", "sys:repair:manage"])),
):
    """
    获取图片上传配置
    
    返回上传接口的 URL 地址。
    """
    return {
        "code": 200,
        "data": {
            "upload_url": "/api/v1/repair-images/upload",
        },
    }


@router.post("/upload", response_model=dict)
async def upload_image(
    file: UploadFile = File(...),
    order_id: Optional[int] = Form(None),
    work_log_id: Optional[int] = Form(None),
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:add", "sys:repair:create", "sys:repair:manage"])),
):
    """
    上传维修图片
    
    支持关联到具体的维修单 (order_id) 或工单日志 (work_log_id)。
    图片将被上传到配置的存储服务 (如本地存储或远程对象存储)。
    
    Args:
        file: 图片文件对象
        order_id: 关联的维修单 ID (可选)
        work_log_id: 关联的工单日志 ID (可选)
    """
    try:
        if order_id is not None:
            from app.models.orm.repair import RepairOrder
            exists = await RepairOrder.filter(id=int(order_id)).exists()
            if not exists:
                return {"code": 404, "message": "工单不存在，无法上传图片"}
        if work_log_id is not None:
            from app.models.orm.repair import WorkLog
            exists = await WorkLog.filter(id=int(work_log_id)).exists()
            if not exists:
                return {"code": 404, "message": "工作记录不存在，无法上传图片"}

        max_bytes = None
        if order_id is not None and work_log_id is None:
            max_bytes = RepairImageService.MAX_ORDER_IMAGE_BYTES

        # 1. 调用 Service 处理图片上传
        # Service 内部会根据配置决定上传到本地还是远程对象存储
        img = await RepairImageService.create_image(
            file=file,
            uploader_id=int(current_user["id"]),
            order_id=order_id,
            work_log_id=work_log_id,
            max_bytes=max_bytes,
        )
        # 2. 规范化图片 URL (处理相对路径/绝对路径)
        url = ImageStorageService.normalize_public_url(str(img.url or ""))
        return {"code": 200, "data": {"id": img.id, "url": url}}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except RemoteImageApiError as e:
        logger.error(f"repair image upload failed: {e}")
        # 3. 处理远程存储服务的特定错误
        # 429: 请求过于频繁 (Rate Limit)
        # 401/403: 认证失败或权限不足
        http_status = getattr(e, "status_code", None)
        if http_status == 429:
            return {"code": 429, "message": str(e)}
        if http_status in (401, 403):
            return {"code": 401, "message": str(e)}
        return {"code": 500, "message": str(e)}
    except Exception as e:
        logger.exception("repair image upload failed")
        return {"code": 500, "message": f"上传失败: {str(e)}"}


@router.get("/{image_id}", response_model=dict)
async def get_image(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:view", "sys:repair:view", "sys:repair:manage"])),
):
    """
    获取图片详情
    
    返回图片的元数据信息，包括 URL、关联的工单等。
    """
    # 1. 查询数据库中的图片记录
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}

    if not await _can_view_image(img, current_user):
        return {"code": 403, "message": "无权查看此图片"}
    
    # 2. 转换数据模型
    payload = RepairImageResponse(**dict(img)).dict()
    
    # 3. 规范化图片 URL
    # 确保存储的相对路径被转换为完整可访问的 URL (包含域名/端口)
    payload["url"] = ImageStorageService.normalize_public_url(str(payload.get("url") or ""))
    
    return {"code": 200, "data": payload}


@router.get("/{image_id}/content")
async def get_image_content(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:view", "sys:repair:view", "sys:repair:manage"])),
):
    """
    获取图片内容 (重定向)
    
    直接重定向到图片的真实访问地址。
    """
    # 1. 获取图片信息
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}

    if not await _can_view_image(img, current_user):
        return {"code": 403, "message": "无权查看此图片"}
    
    # 2. 检查存储类型
    # 目前仅支持重定向远程 API 存储的图片
    if str(img.storage_provider) != "remote_api":
        return {"code": 400, "message": "当前图片不支持读取"}
    
    # 3. 获取并规范化 URL
    url = str(img.url or "").strip()
    if not url:
        return {"code": 404, "message": "图片链接不存在"}
    url = ImageStorageService.normalize_public_url(url)
    
    # 4. 执行 HTTP 307 临时重定向
    return RedirectResponse(url=url, status_code=307)


@router.put("/{image_id}", response_model=dict)
async def update_image(
    image_id: int,
    data: RepairImageUpdate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:edit"])),
):
    """
    更新图片关联信息
    
    主要用于更新图片关联的维修单 ID 或工单日志 ID。
    """
    # 1. 检查图片是否存在
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}
        
    # 2. 更新关联信息
    # 允许将图片重新关联到其他维修单或日志
    await RepairImageService.update_image(image_id, data.order_id, data.work_log_id)
    return {"code": 200, "message": "更新成功"}


@router.delete("/{image_id}", response_model=dict)
async def delete_image(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:del", "sys:repair:manage"])),
):
    """
    删除图片
    
    从数据库和存储服务中彻底删除图片。
    """
    try:
        # 1. 调用 Service 执行删除
        # 同时删除数据库记录和远程/本地存储文件
        ok = await RepairImageService.delete_image(image_id)
        if not ok:
            return {"code": 404, "message": "图片不存在"}
        return {"code": 200, "message": "删除成功"}
    except RemoteImageApiError as e:
        # 2. 处理远程 API 异常
        http_status = getattr(e, "status_code", None)
        if http_status == 429:
            return {"code": 429, "message": str(e)}
        if http_status in (401, 403):
            return {"code": 401, "message": str(e)}
        return {"code": 500, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"删除失败: {str(e)}"}
