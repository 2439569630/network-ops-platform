from tortoise import fields, models

class User(models.Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    password = fields.CharField(max_length=128)
    nickname = fields.CharField(max_length=50, null=True)
    email = fields.CharField(max_length=255, null=True)
    is_approved = fields.BooleanField(default=True)
    permissions = fields.JSONField(default=list)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
