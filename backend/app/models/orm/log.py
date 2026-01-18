from tortoise import fields, models

class LoginLog(models.Model):
    """登录日志"""
    id = fields.IntField(pk=True)
    user_id = fields.IntField(index=True)
    ip = fields.CharField(max_length=50, null=True)
    user_agent = fields.CharField(max_length=500, null=True)
    device = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "login_logs"
