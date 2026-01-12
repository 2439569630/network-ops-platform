import asyncio
import logging
import os
import signal
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.database import db
from app.core.logger import setup_logger
from app.core.redis import redis_manager
from app.services.notification_service import NotificationService
from app.workers.monitor.manager import MonitorManager


logger = logging.getLogger(__name__)


async def _run() -> int:
    setup_logger()
    logger.info("Monitor daemon starting...")

    try:
        await redis_manager.init()
    except Exception as e:
        logger.error(f"Redis init failed: {e}")

    try:
        await db.connect()
    except Exception as e:
        logger.error(f"DB connect failed: {e}")

    try:
        await NotificationService._ensure_site_message_tables()
    except Exception as e:
        logger.error(f"Ensure site message tables failed: {e}")

    monitor = MonitorManager()
    await monitor.start()

    stop_event = asyncio.Event()

    def _stop():
        stop_event.set()

    if os.name != "nt":
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _stop)
        loop.add_signal_handler(signal.SIGINT, _stop)

    await stop_event.wait()

    logger.info("Monitor daemon stopping...")
    await monitor.stop()
    await asyncio.gather(db.disconnect(), redis_manager.close())
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
