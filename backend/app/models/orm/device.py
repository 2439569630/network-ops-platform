
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
    
    # New fields to match DB
    vendor = fields.CharField(max_length=255, null=True)
    model = fields.CharField(max_length=255, null=True)
    serial_number = fields.CharField(max_length=255, null=True)
    description = fields.TextField(null=True)
    telnet_port = fields.IntField(null=True)
    last_seen = fields.DatetimeField(null=True)
    last_backup = fields.DatetimeField(null=True)
    
    created_by = fields.CharField(max_length=50, null=True)
    updated_by = fields.CharField(max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "network_devices"
