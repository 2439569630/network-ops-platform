from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import RedirectResponse
from typing import Optional

from app.core.security import PermissionChecker
from app.schemas.repair_image import RepairImageResponse, RepairImageUpdate
from app.services.image_storage_service import ImageStorageService
from app.services.repair_image_service import RepairImageService
from app.utils.remote_image_api import RemoteImageApiError


router = APIRouter()


@router.get("/upload_config", response_model=dict)
async def get_upload_config(
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:add"])),
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
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:add"])),
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
        # 1. 调用 Service 处理图片上传
        # Service 内部会根据配置决定上传到本地还是远程对象存储
        img = await RepairImageService.create_image(
            file=file,
            uploader_id=int(current_user["id"]),
            order_id=order_id,
            work_log_id=work_log_id,
        )
        # 2. 规范化图片 URL (处理相对路径/绝对路径)
        url = ImageStorageService.normalize_public_url(str(img.url or ""))
        return {"code": 200, "data": {"id": img.id, "url": url}}
    except RemoteImageApiError as e:
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
        return {"code": 500, "message": f"上传失败: {str(e)}"}


@router.get("/{image_id}", response_model=dict)
async def get_image(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:view"])),
):
    """
    获取图片详情
    
    返回图片的元数据信息，包括 URL、关联的工单等。
    """
    # 1. 查询数据库中的图片记录
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}
    
    # 2. 转换数据模型
    payload = RepairImageResponse(**dict(img)).dict()
    
    # 3. 规范化图片 URL
    # 确保存储的相对路径被转换为完整可访问的 URL (包含域名/端口)
    payload["url"] = ImageStorageService.normalize_public_url(str(payload.get("url") or ""))
    
    return {"code": 200, "data": payload}


@router.get("/{image_id}/content")
async def get_image_content(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:view"])),
):
    """
    获取图片内容 (重定向)
    
    直接重定向到图片的真实访问地址。
    """
    # 1. 获取图片信息
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}
    
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
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:del"])),
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
