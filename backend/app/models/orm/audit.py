from tortoise import fields, models

class DeviceChangeLog(models.Model):
    id = fields.BigIntField(pk=True)
    device_id = fields.IntField()
    change_type = fields.CharField(max_length=50)
    change_description = fields.TextField()
    changed_by = fields.CharField(max_length=50)
    changed_at = fields.DatetimeField(auto_now_add=True)
    old_values = fields.JSONField(null=True)
    new_values = fields.JSONField(null=True)

    class Meta:
        table = "device_change_log"

class SshCommandAuditLog(models.Model):
    id = fields.BigIntField(pk=True)
    device_id = fields.IntField()
    device_ip = fields.CharField(max_length=50)
    command = fields.TextField()
    executed_by = fields.CharField(max_length=50)
    executed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ssh_command_audit_log"
