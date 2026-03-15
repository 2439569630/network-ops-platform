import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import db


LEGACY_CODES = [
    "sys:auth:login",
    "sys:auth:register",
    "sys:email:verify",
]


async def main():
    await db.connect()
    try:
        rows = await db.fetch_all(
            "SELECT id, code FROM permissions WHERE code = ANY($1::text[]) ORDER BY id",
            [str(c) for c in LEGACY_CODES],
        )
        ids = [int(r["id"]) for r in (rows or []) if r and r.get("id") is not None]
        if not ids:
            print("No legacy permissions found.")
            return

        await db.execute("DELETE FROM role_permissions WHERE permission_id = ANY($1::int[])", ids)
        await db.execute("DELETE FROM permissions WHERE id = ANY($1::int[])", ids)
        print(f"Deleted legacy permissions: {', '.join([str(r.get('code')) for r in (rows or []) if r and r.get('code')])}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

