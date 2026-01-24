from __future__ import annotations

from typing import Optional


class BodyTooLargeError(RuntimeError):
    pass


class MaxBodySizeMiddleware:
    _TOO_LARGE_BODY = '{"code":413,"message":"上传内容过大"}'.encode("utf-8")

    def __init__(self, app, limits: dict[str, int]):
        self.app = app
        self.limits = {str(k): int(v) for k, v in (limits or {}).items() if k and v}

    def _limit_for_path(self, path: str) -> Optional[int]:
        p = str(path or "")
        for prefix, limit in self.limits.items():
            if p.startswith(prefix):
                return int(limit)
        return None

    @staticmethod
    def _content_length(scope) -> Optional[int]:
        try:
            headers = scope.get("headers") or []
            for k, v in headers:
                if k.lower() == b"content-length":
                    raw = v.decode("utf-8", errors="ignore").strip()
                    if not raw:
                        return None
                    return int(raw)
        except Exception:
            return None
        return None

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        limit = self._limit_for_path(path)
        if not limit:
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > limit:
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": self._TOO_LARGE_BODY,
                    "more_body": False,
                }
            )
            return

        received = 0
        response_started = False

        async def send_wrap(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        async def receive_wrap():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body") or b""
                received += len(body)
                if received > limit:
                    raise BodyTooLargeError()
            return message

        try:
            await self.app(scope, receive_wrap, send_wrap)
        except BodyTooLargeError:
            if response_started:
                raise
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": self._TOO_LARGE_BODY,
                    "more_body": False,
                }
            )
