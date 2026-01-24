from tortoise import fields, models

class DeviceAlertRule(models.Model):
    """设备告警规则模型"""
    id = fields.IntField(pk=True)
    device = fields.ForeignKeyField("models.NetworkDevice", related_name="alert_rules")
    
    metric = fields.CharField(max_length=50)  # cpu_usage, memory_usage, disk_usage, online_status, response_time
    operator = fields.CharField(max_length=10)  # >, <, =, >=, <=
    threshold = fields.FloatField()
    
    severity = fields.CharField(max_length=20, default="warning")  # info, warning, critical
    duration = fields.IntField(default=0)  # 持续时间(秒)
    cooldown = fields.IntField(default=0)  # 冷却时间(秒)
    
    is_enabled = fields.BooleanField(default=True)
    notification_channels = fields.JSONField(null=True)  # ["email", "webhook"]
    created_by = fields.IntField(null=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "device_alert_rules"
        unique_together = (("device", "metric", "operator", "threshold"),)


class DeviceAlertLog(models.Model):
    """设备告警记录模型"""
    id = fields.IntField(pk=True)
    device = fields.ForeignKeyField("models.NetworkDevice", related_name="alert_logs")
    rule = fields.ForeignKeyField("models.DeviceAlertRule", related_name="logs", null=True, on_delete=fields.SET_NULL)
    
    metric = fields.CharField(max_length=50)
    value = fields.FloatField()
    message = fields.TextField()
    severity = fields.CharField(max_length=20)
    
    triggered_at = fields.DatetimeField(auto_now_add=True)
    resolved_at = fields.DatetimeField(null=True)
    
    class Meta:
        table = "device_alert_logs"
        indexes = [
            ("device_id", "triggered_at"),
            ("rule_id", "resolved_at"),
        ]


class AlertSubscription(models.Model):
    id = fields.BigIntField(pk=True)
    subscriber_user_id = fields.IntField()
    scope_type = fields.CharField(max_length=20)
    scope_id = fields.BigIntField()
    channels = fields.JSONField(default=list)
    severities = fields.JSONField(null=True)
    is_enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "alert_subscriptions"
        unique_together = (("subscriber_user_id", "scope_type", "scope_id"),)
