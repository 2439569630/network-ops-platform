from fastapi import UploadFile

from app.services.image_storage_service import ImageStorageService, ImageUploadPolicy
from app.utils.remote_image_api import RemoteImageApiUploadResult


class AvatarService:
    MAX_IMAGE_BYTES = 5 * 1024 * 1024

    @staticmethod
    async def upload_avatar(file: UploadFile) -> RemoteImageApiUploadResult:
        policy = ImageUploadPolicy(
            max_bytes=AvatarService.MAX_IMAGE_BYTES,
            allowed_extensions=(".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"),
            require_image_content_type=True,
        )
        return await ImageStorageService.upload_image(file, policy)
