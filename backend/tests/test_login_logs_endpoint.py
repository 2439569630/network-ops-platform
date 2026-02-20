import unittest
from unittest.mock import AsyncMock

from fastapi import HTTPException


class TestMyLoginLogsEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_returns_items_and_meta(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        auth_endpoint.db.fetch_val = AsyncMock(return_value=5)
        auth_endpoint.db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": 10,
                    "ip": "127.0.0.1",
                    "user_agent": "ua",
                    "device": "web",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        )

        resp = await auth_endpoint.get_my_login_logs(page=2, page_size=2, token_payload={"id": 7})

        self.assertEqual(resp.get("code"), 200)
        self.assertEqual(resp.get("meta", {}).get("total"), 5)
        self.assertEqual(resp.get("meta", {}).get("page"), 2)
        self.assertEqual(resp.get("meta", {}).get("page_size"), 2)

        data = resp.get("data") or []
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get("id"), 10)

        args, _kwargs = auth_endpoint.db.fetch_all.call_args
        self.assertEqual(args[1:], (7, 2, 2))

    async def test_requires_login(self):
        from app.api.v1.endpoints import auth as auth_endpoint

        with self.assertRaises(HTTPException) as cm:
            await auth_endpoint.get_my_login_logs(page=1, page_size=10, token_payload={})

        self.assertEqual(getattr(cm.exception, "status_code", None), 401)


if __name__ == "__main__":
    unittest.main()
