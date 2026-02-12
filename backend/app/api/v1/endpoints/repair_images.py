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
    try:
        img = await RepairImageService.create_image(
            file=file,
            uploader_id=int(current_user["id"]),
            order_id=order_id,
            work_log_id=work_log_id,
        )
        url = ImageStorageService.normalize_public_url(str(img.url or ""))
        return {"code": 200, "data": {"id": img.id, "url": url}}
    except RemoteImageApiError as e:
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
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}
    payload = RepairImageResponse(**dict(img)).dict()
    payload["url"] = ImageStorageService.normalize_public_url(str(payload.get("url") or ""))
    return {"code": 200, "data": payload}


@router.get("/{image_id}/content")
async def get_image_content(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:view"])),
):
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}
    if str(img.storage_provider) != "remote_api":
        return {"code": 400, "message": "当前图片不支持读取"}
    url = str(img.url or "").strip()
    if not url:
        return {"code": 404, "message": "图片链接不存在"}
    url = ImageStorageService.normalize_public_url(url)
    return RedirectResponse(url=url, status_code=307)


@router.put("/{image_id}", response_model=dict)
async def update_image(
    image_id: int,
    data: RepairImageUpdate,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:edit"])),
):
    img = await RepairImageService.get_image(image_id)
    if not img:
        return {"code": 404, "message": "图片不存在"}
    await RepairImageService.update_image(image_id, data.order_id, data.work_log_id)
    return {"code": 200, "message": "更新成功"}


@router.delete("/{image_id}", response_model=dict)
async def delete_image(
    image_id: int,
    current_user: dict = Depends(PermissionChecker(["sys:repair:image:del"])),
):
    try:
        ok = await RepairImageService.delete_image(image_id)
        if not ok:
            return {"code": 404, "message": "图片不存在"}
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
