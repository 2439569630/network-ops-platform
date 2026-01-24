from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.system_config import SystemConfig


class RemoteImageApiError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _normalize_base_url(value: str) -> str:
    v = str(value or "").strip()
    return v.rstrip("/")


def _join(base_url: str, path: str) -> str:
    b = _normalize_base_url(base_url)
    p = "/" + str(path or "").lstrip("/")
    return f"{b}{p}" if b else p


@dataclass
class RemoteImageApiUploadResult:
    key: str
    url: str
    thumbnail_url: Optional[str] = None
    raw: Optional[dict] = None


_TOKEN_CACHE: dict[str, str] = {"token": ""}


class RemoteImageApiClient:
    def __init__(self, base_url: str):
        self.base_url = _normalize_base_url(base_url)

    def _headers(self, token: Optional[str]) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request_json(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        timeout = kwargs.pop("timeout", 30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)
        if resp.status_code == 429:
            raise RemoteImageApiError("外部图片服务请求受限(429)", status_code=429)
        if resp.status_code in (401, 403):
            raise RemoteImageApiError("外部图片服务授权失败", status_code=resp.status_code)
        if resp.status_code >= 500:
            raise RemoteImageApiError("外部图片服务异常", status_code=resp.status_code)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RemoteImageApiError(f"外部图片服务请求失败: HTTP {resp.status_code}", status_code=resp.status_code)
        try:
            return resp.json()
        except Exception:
            raise RemoteImageApiError("外部图片服务返回非JSON内容", status_code=resp.status_code)

    async def create_token(self, email: str, password: str) -> str:
        url = _join(self.base_url, "/tokens")
        payload = {"email": str(email or "").strip(), "password": str(password or "")}
        data = await self._request_json(
            "POST",
            url,
            headers={"Accept": "application/json"},
            json=payload,
        )
        ok = bool(data.get("status"))
        if not ok:
            raise RemoteImageApiError(str(data.get("message") or "外部图片服务返回失败"))
        token = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("token")
        token = str(token or "").strip()
        if not token:
            raise RemoteImageApiError("外部图片服务未返回 token")
        _TOKEN_CACHE["token"] = token
        return token

    async def get_token(self) -> str:
        cached = str(_TOKEN_CACHE.get("token") or "").strip()
        if cached:
            return cached
        email = str(SystemConfig.get("repair_image_api_email", "") or "").strip()
        password = str(SystemConfig.get("repair_image_api_password", "") or "")
        if not email or not password:
            return ""
        return await self.create_token(email=email, password=password)

    async def upload(
        self,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        strategy_id: Optional[int] = None,
        token: Optional[str] = None,
    ) -> RemoteImageApiUploadResult:
        url = _join(self.base_url, "/upload")
        token_norm = token if token is not None else await self.get_token()
        if not token_norm:
            raise RemoteImageApiError("未配置外部图片服务账号密码，无法获取 token")

        files = {"file": (str(filename or "image"), content, str(content_type or "application/octet-stream"))}
        form = {}
        if strategy_id is not None:
            form["strategy_id"] = str(int(strategy_id))

        data = await self._request_json("POST", url, headers=self._headers(token_norm), files=files, data=form)
        ok = bool(data.get("status"))
        if not ok:
            raise RemoteImageApiError(str(data.get("message") or "外部图片服务上传失败"))
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        key = str(payload.get("key") or "").strip()
        links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
        img_url = str(links.get("url") or "").strip()
        thumb = str(links.get("thumbnail_url") or "").strip() or None
        if not key or not img_url:
            raise RemoteImageApiError("外部图片服务返回数据缺失(key/url)")
        return RemoteImageApiUploadResult(key=key, url=img_url, thumbnail_url=thumb, raw=payload)

    async def upload_file(
        self,
        *,
        filename: str,
        fileobj: Any,
        content_type: Optional[str] = None,
        strategy_id: Optional[int] = None,
        token: Optional[str] = None,
    ) -> RemoteImageApiUploadResult:
        url = _join(self.base_url, "/upload")
        token_norm = token if token is not None else await self.get_token()

        files = {"file": (str(filename or "image"), fileobj, str(content_type or "application/octet-stream"))}
        form = {}
        if strategy_id is not None:
            form["strategy_id"] = str(int(strategy_id))

        data = await self._request_json("POST", url, headers=self._headers(token_norm or None), files=files, data=form)
        ok = bool(data.get("status"))
        if not ok:
            raise RemoteImageApiError(str(data.get("message") or "外部图片服务上传失败"))
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        key = str(payload.get("key") or "").strip()
        links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
        img_url = str(links.get("url") or "").strip()
        thumb = str(links.get("thumbnail_url") or "").strip() or None
        if not key or not img_url:
            raise RemoteImageApiError("外部图片服务返回数据缺失(key/url)")
        return RemoteImageApiUploadResult(key=key, url=img_url, thumbnail_url=thumb, raw=payload)

    async def delete(self, key: str, token: Optional[str] = None) -> bool:
        key_norm = str(key or "").strip()
        if not key_norm:
            raise RemoteImageApiError("图片 key 为空")
        url = _join(self.base_url, f"/images/{key_norm}")
        token_norm = token if token is not None else await self.get_token()
        if not token_norm:
            raise RemoteImageApiError("未配置外部图片服务账号密码，无法获取 token")
        data = await self._request_json("DELETE", url, headers=self._headers(token_norm))
        ok = bool(data.get("status"))
        if not ok:
            raise RemoteImageApiError(str(data.get("message") or "外部图片服务删除失败"))
        return True
