from tortoise import fields, models

class User(models.Model):
    """用户模型"""
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    password = fields.CharField(max_length=128)
    nickname = fields.CharField(max_length=50, null=True)
    email = fields.CharField(max_length=255, null=True)
    avatar_url = fields.CharField(max_length=1024, null=True)
    avatar_key = fields.CharField(max_length=1024, null=True)
    is_email_notify = fields.BooleanField(default=False)
    is_approved = fields.BooleanField(default=True)
    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)
    deleted_by = fields.ForeignKeyField("models.User", related_name="deleted_users", null=True, source_field="deleted_by")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
