import logging
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)

ALERT_RULES_UPDATE_CHANNEL = "alert:rules:update"

class AlertService:
    """
    预警服务层
    负责协调 Web 进程与监控进程之间的预警规则同步。
    """
    
    @staticmethod
    async def notify_rule_change(device_id: int):
        """
        通知监控进程规则已变更
        
        Args:
            device_id: 设备ID
        """
        try:
            redis = redis_manager.get_client()
            if redis:
                # 发布消息到 Redis 频道，消息内容为 device_id
                await redis.publish(ALERT_RULES_UPDATE_CHANNEL, str(device_id))
                logger.info(f"Published alert rule update for device {device_id}")
            else:
                logger.warning("Redis client not available, cannot publish alert rule update")
        except Exception as e:
            logger.error(f"Failed to publish alert rule update: {e}")
