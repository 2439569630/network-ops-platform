import asyncio
import logging
import os
import signal
import sys

from tortoise import Tortoise

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.config import settings
from app.core.database import db
from app.core.logger import setup_logger
from app.core.redis import redis_manager
from app.workers.config_push.worker import ConfigPushWorker


logger = logging.getLogger(__name__)


async def _run() -> int:
    setup_logger()
    logger.info("ConfigPush worker starting...")

    try:
        await redis_manager.init()
    except Exception as e:
        logger.error(f"Redis init failed: {e}")

    try:
        await db.connect()
    except Exception as e:
        logger.error(f"DB connect failed: {e}")
        try:
            await redis_manager.close()
        except Exception:
            pass
        return 1

    try:
        await Tortoise.init(
            db_url=settings.DATABASE_URL,
            modules={
                "models": [
                    "app.models.orm.user",
                    "app.models.orm.device",
                    "app.models.orm.audit",
                    "app.models.orm.notification",
                    "app.models.orm.repair",
                    "app.models.orm.rbac",
                    "app.models.orm.location",
                    "app.models.orm.config",
                    "app.models.orm.config_push",
                    "app.models.orm.alert",
                ]
            },
        )
        await Tortoise.generate_schemas()
        logger.info("Tortoise ORM initialized")
    except Exception as e:
        logger.error(f"Tortoise ORM init failed: {e}")
        try:
            await asyncio.gather(db.disconnect(), redis_manager.close())
        except Exception:
            pass
        try:
            await Tortoise.close_connections()
        except Exception:
            pass
        return 1

    worker = ConfigPushWorker()
    await worker.start()

    stop_event = asyncio.Event()

    def _stop():
        stop_event.set()

    if os.name != "nt":
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _stop)
        loop.add_signal_handler(signal.SIGINT, _stop)

    await stop_event.wait()

    logger.info("ConfigPush worker stopping...")
    await worker.stop()
    await asyncio.gather(db.disconnect(), redis_manager.close())
    await Tortoise.close_connections()
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
