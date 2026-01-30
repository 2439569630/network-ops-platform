from tortoise import fields, models


class ConfigPushJob(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    creator_id = fields.IntField()
    status = fields.CharField(max_length=32, default="pending")
    command_list = fields.JSONField()
    device_count = fields.IntField(default=0)
    success_count = fields.IntField(default=0)
    fail_count = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "config_push_jobs"


class ConfigPushJobItem(models.Model):
    id = fields.IntField(pk=True)
    job = fields.ForeignKeyField("models.ConfigPushJob", related_name="items")
    device_id = fields.IntField()
    device_name = fields.CharField(max_length=255)
    device_ip = fields.CharField(max_length=50)
    status = fields.CharField(max_length=32, default="pending")
    error_message = fields.TextField(null=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "config_push_job_items"
        unique_together = (("job_id", "device_id"),)


class ConfigPushLog(models.Model):
    id = fields.IntField(pk=True)
    job_id = fields.IntField()
    type = fields.CharField(max_length=50)
    subject = fields.CharField(max_length=255, null=True)
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "config_push_logs"
