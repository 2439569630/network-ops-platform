
from tortoise import fields, models

class NetworkDevice(models.Model):
    """网络设备模型"""
    id = fields.IntField(pk=True)
    device_name = fields.CharField(max_length=255)
    ipv4 = fields.CharField(max_length=50, null=True)
    ipv6 = fields.CharField(max_length=50, null=True)
    mac = fields.CharField(max_length=17, null=True)
    device_type = fields.CharField(max_length=50)
    
    # SSH Credentials
    user_name = fields.CharField(max_length=100, default="root")
    password = fields.CharField(max_length=100, default="")
    ssh_port = fields.IntField(default=22)
    is_active = fields.BooleanField(default=True)
    
    created_by = fields.CharField(max_length=50, null=True)
    updated_by = fields.CharField(max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "network_devices"
        unique_together = (("ipv4", "ssh_port"),)


class DeviceConfigEntry(models.Model):
    """设备监控配置模型"""
    device_id = fields.IntField(pk=True)

    interval = fields.FloatField(null=True)
    monitor_interval = fields.FloatField(null=True)

    offline_fail_threshold = fields.IntField(null=True)
    recovery_success_threshold = fields.IntField(null=True)

    connect_timeout = fields.FloatField(null=True)
    auth_timeout = fields.FloatField(null=True)
    banner_timeout = fields.FloatField(null=True)
    global_delay_factor = fields.FloatField(null=True)

    connect_max_retries = fields.IntField(null=True)
    connect_retry_delay_seconds = fields.FloatField(null=True)
    offline_retry_delay_seconds = fields.FloatField(null=True)
    
    resource_sync_interval = fields.FloatField(default=3600.0)
    interfaces_sync_interval = fields.FloatField(default=3600.0)
    interfaces_slot0_sync_interval = fields.FloatField(default=3600.0)
    routes_sync_interval = fields.FloatField(default=3600.0)
    vlans_sync_interval = fields.FloatField(default=3600.0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "device_configs"
