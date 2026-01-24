import unittest
from unittest.mock import patch


class DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class DummyAsyncClient:
    last_request = None
    next_handler = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, **kwargs):
        DummyAsyncClient.last_request = {"method": method, "url": url, **kwargs}
        handler = DummyAsyncClient.next_handler
        if callable(handler):
            return handler(method, url, **kwargs)
        return handler


class TestRemoteImageApiClient(unittest.IsolatedAsyncioTestCase):
    async def test_create_token(self):
        from app.utils.remote_image_api import RemoteImageApiClient

        def handler(method, url, **kwargs):
            return DummyResponse(200, {"status": True, "data": {"token": "1|abc"}})

        DummyAsyncClient.last_request = None
        with patch("app.utils.remote_image_api.httpx.AsyncClient", DummyAsyncClient):
            DummyAsyncClient.next_handler = handler
            cli = RemoteImageApiClient("http://host/api/v1")
            token = await cli.create_token(email="a@b.com", password="x")
            self.assertEqual(token, "1|abc")
            req = DummyAsyncClient.last_request
            self.assertEqual(req["method"], "POST")
            self.assertEqual(req["url"], "http://host/api/v1/tokens")
            self.assertEqual(req["headers"]["Accept"], "application/json")
            self.assertEqual(req["json"]["email"], "a@b.com")

    async def test_upload_includes_accept_and_auth(self):
        from app.utils.remote_image_api import RemoteImageApiClient

        def handler(method, url, **kwargs):
            return DummyResponse(
                200,
                {
                    "status": True,
                    "data": {
                        "key": "k1",
                        "links": {"url": "http://img/u1", "thumbnail_url": "http://img/t1"},
                    },
                },
            )

        DummyAsyncClient.last_request = None
        with patch("app.utils.remote_image_api.httpx.AsyncClient", DummyAsyncClient):
            DummyAsyncClient.next_handler = handler
            cli = RemoteImageApiClient("http://host/api/v1")
            out = await cli.upload(
                filename="a.png",
                content=b"123",
                content_type="image/png",
                strategy_id=3,
                token="1|abc",
            )
            self.assertEqual(out.key, "k1")
            self.assertEqual(out.url, "http://img/u1")
            req = DummyAsyncClient.last_request
            self.assertEqual(req["method"], "POST")
            self.assertEqual(req["url"], "http://host/api/v1/upload")
            self.assertEqual(req["headers"]["Accept"], "application/json")
            self.assertEqual(req["headers"]["Authorization"], "Bearer 1|abc")
            self.assertEqual(req["data"]["strategy_id"], "3")
            self.assertIn("file", req["files"])

    async def test_delete_requires_auth(self):
        from app.core.system_config import SystemConfig
        from app.utils.remote_image_api import RemoteImageApiClient, RemoteImageApiError, _TOKEN_CACHE

        SystemConfig._config["repair_image_api_email"] = ""
        SystemConfig._config["repair_image_api_password"] = ""
        _TOKEN_CACHE["token"] = ""

        with patch("app.utils.remote_image_api.httpx.AsyncClient", DummyAsyncClient):
            cli = RemoteImageApiClient("http://host/api/v1")
            with self.assertRaises(RemoteImageApiError):
                await cli.delete("k1")


if __name__ == "__main__":
    unittest.main()
