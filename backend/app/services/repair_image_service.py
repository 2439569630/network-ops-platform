from typing import Optional
from fastapi import UploadFile

from app.models.orm.repair import RepairImage
from app.services.image_storage_service import ImageStorageService, ImageUploadPolicy
from app.utils.remote_image_api import RemoteImageApiError


class RepairImageService:
    MAX_IMAGE_BYTES = 20 * 1024 * 1024

    @staticmethod
    async def create_remote_image(
        file: UploadFile,
        uploader_id: int,
        order_id: Optional[int] = None,
        work_log_id: Optional[int] = None,
    ) -> RepairImage:
        policy = ImageUploadPolicy(
            max_bytes=RepairImageService.MAX_IMAGE_BYTES,
            allowed_extensions=(".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"),
            require_image_content_type=True,
        )
        result = await ImageStorageService.upload_image(file, policy)
        size = ImageStorageService._guess_size(file)

        return await RepairImage.create(
            order_id=order_id,
            work_log_id=work_log_id,
            uploader_id=int(uploader_id),
            storage_provider="remote_api",
            object_key=str(result.key),
            url=str(result.url),
            mime_type=str(getattr(file, "content_type", None) or "") or None,
            size=int(size) if size is not None else None,
        )

    @staticmethod
    async def create_image(
        file: UploadFile,
        uploader_id: int,
        order_id: Optional[int] = None,
        work_log_id: Optional[int] = None,
    ) -> RepairImage:
        return await RepairImageService.create_remote_image(
            file=file,
            uploader_id=uploader_id,
            order_id=order_id,
            work_log_id=work_log_id,
        )

    @staticmethod
    async def get_image(image_id: int) -> Optional[RepairImage]:
        return await RepairImage.filter(id=int(image_id)).first()

    @staticmethod
    async def update_image(image_id: int, order_id: Optional[int], work_log_id: Optional[int]) -> bool:
        updates = {}
        if order_id is not None:
            updates["order_id"] = order_id
        if work_log_id is not None:
            updates["work_log_id"] = work_log_id
        if not updates:
            return True
        await RepairImage.filter(id=int(image_id)).update(**updates)
        return True

    @staticmethod
    async def delete_image(image_id: int) -> bool:
        img = await RepairImageService.get_image(image_id)
        if not img:
            return False
        await ImageStorageService.delete_remote(str(img.object_key or ""))
        await RepairImage.filter(id=int(image_id)).delete()
        return True
