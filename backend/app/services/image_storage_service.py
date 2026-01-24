from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Iterable

from fastapi import UploadFile

from app.core.system_config import SystemConfig
from app.utils.remote_image_api import RemoteImageApiClient, RemoteImageApiUploadResult


@dataclass
class ImageUploadPolicy:
    max_bytes: int
    allowed_extensions: tuple[str, ...]
    require_image_content_type: bool = True


class ImageStorageService:
    @staticmethod
    def _remote_client() -> RemoteImageApiClient:
        base_url = str(SystemConfig.get("repair_image_api_base_url", "") or "").strip()
        if not base_url:
            base_url = "http://45.192.104.13:40027/api/v1"
        return RemoteImageApiClient(base_url=base_url)

    @staticmethod
    def _normalize_exts(exts: Iterable[str]) -> tuple[str, ...]:
        items = []
        for e in exts:
            v = str(e or "").strip().lower()
            if not v:
                continue
            if not v.startswith("."):
                v = "." + v
            items.append(v)
        return tuple(dict.fromkeys(items))

    @staticmethod
    def _guess_size(file: UploadFile) -> Optional[int]:
        try:
            f = getattr(file, "file", None)
            if not f:
                return None
            pos = f.tell()
            f.seek(0, 2)
            size = int(f.tell())
            f.seek(pos, 0)
            return max(size, 0)
        except Exception:
            return None

    @staticmethod
    def _validate_image(file: UploadFile, policy: ImageUploadPolicy) -> None:
        filename = str(getattr(file, "filename", "") or "").strip()
        if not filename:
            raise ValueError("缺少文件名")
        lowered = filename.lower()

        allowed_exts = ImageStorageService._normalize_exts(policy.allowed_extensions)
        if allowed_exts and not any(lowered.endswith(ext) for ext in allowed_exts):
            raise ValueError(f"仅支持图片格式: {', '.join([e.lstrip('.') for e in allowed_exts])}")

        content_type = str(getattr(file, "content_type", "") or "").strip().lower()
        if policy.require_image_content_type and content_type and not content_type.startswith("image/"):
            raise ValueError("仅支持图片文件")

        size = ImageStorageService._guess_size(file)
        if size is not None and int(size) > int(policy.max_bytes):
            raise ValueError(f"图片过大(最大 {int(policy.max_bytes // (1024 * 1024))}MB)")

    @staticmethod
    async def upload_image(file: UploadFile, policy: ImageUploadPolicy) -> RemoteImageApiUploadResult:
        ImageStorageService._validate_image(file, policy)
        await file.seek(0)
        return await ImageStorageService._remote_client().upload_file(
            filename=str(file.filename or "image"),
            fileobj=file.file,
            content_type=str(getattr(file, "content_type", None) or "") or None,
        )

    @staticmethod
    async def delete_remote(key: str) -> bool:
        return await ImageStorageService._remote_client().delete(key=str(key or "").strip())
