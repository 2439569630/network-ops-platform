
from tortoise import fields, models

class NetworkDevice(models.Model):
    id = fields.IntField(pk=True)
    device_name = fields.CharField(max_length=255)
    ipv4 = fields.CharField(max_length=50, null=True)
    ipv6 = fields.CharField(max_length=50, null=True)
    mac = fields.CharField(max_length=50, null=True)
    device_type = fields.CharField(max_length=50, null=True)
    user_name = fields.CharField(max_length=50, null=True)
    password = fields.CharField(max_length=128, null=True)
    ssh_port = fields.IntField(default=22)
    online_status = fields.BooleanField(default=False)
    is_active = fields.BooleanField(default=True)
    
    vendor = fields.CharField(max_length=255, null=True)
    model = fields.CharField(max_length=255, null=True)
    serial_number = fields.CharField(max_length=255, null=True)
    last_seen = fields.DatetimeField(null=True)
    
    created_by = fields.CharField(max_length=50, null=True)
    updated_by = fields.CharField(max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "network_devices"


class DeviceConfigEntry(models.Model):
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

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "device_configs"
