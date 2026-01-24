import json
import logging
from typing import Any, Dict, Optional

from app.core.redis import redis_manager

logger = logging.getLogger(__name__)

DEVICE_UPDATE_CHANNEL = "monitor:devices:update"


class DeviceEventService:
    @staticmethod
    async def publish_device_event(action: str, device_id: int, extra: Optional[Dict[str, Any]] = None) -> None:
        payload: Dict[str, Any] = {"action": str(action or "").strip(), "device_id": int(device_id)}
        if extra:
            payload.update(extra)
        try:
            redis = redis_manager.get_client()
            if not redis:
                return
            await redis.publish(DEVICE_UPDATE_CHANNEL, json.dumps(payload, ensure_ascii=False))
            logger.debug(f"Published device event: {payload}")
        except Exception as e:
            logger.warning(f"Failed to publish device event: {e}")
