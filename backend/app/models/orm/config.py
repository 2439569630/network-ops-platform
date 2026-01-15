
from tortoise import fields, models

class SystemSetting(models.Model):
    # key seems to be the primary key or at least unique
    key = fields.CharField(max_length=255, pk=True)
    value = fields.TextField(null=True)
    group_name = fields.CharField(max_length=50, default="system")
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "system_settings"
