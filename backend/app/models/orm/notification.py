
from tortoise import fields, models

class DeviceNotification(models.Model):
    id = fields.BigIntField(pk=True)
    device_id = fields.IntField(null=True)
    level = fields.CharField(max_length=50)
    message = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "device_notifications"

class SiteMessage(models.Model):
    id = fields.BigIntField(pk=True)
    sender_id = fields.IntField(null=True)
    sender_name = fields.CharField(max_length=255, null=True)
    source = fields.CharField(max_length=50, default="系统")
    title = fields.CharField(max_length=255)
    content = fields.TextField()
    is_global = fields.BooleanField(default=False)
    target_user_id = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "site_messages"

class SiteMessageRead(models.Model):
    # This table has a composite primary key in legacy SQL (message_id, user_id).
    # Tortoise doesn't support composite PKs well natively in the same way.
    # We can use a unique constraint or add an ID field if we can migrate.
    # However, to fit existing schema without changing it too much, we might need a workaround or just add an ID.
    # But wait, looking at the SQL in NotificationService:
    # CREATE TABLE IF NOT EXISTS site_message_reads ( ... PRIMARY KEY (message_id, user_id) )
    # It doesn't have a single ID column.
    # Tortoise requires a single PK. 
    # If I can't change the schema to add an ID, I might have to stick to raw SQL for this specific table or use a workaround.
    # Workaround: Add an 'id' column to the table.
    # Let's verify if I can modify the table. Yes I can.
    # I will add an ID column to site_message_reads to make it ORM friendly.
    
    id = fields.BigIntField(pk=True)
    message_id = fields.BigIntField()
    user_id = fields.IntField()
    read_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "site_message_reads"
        unique_together = (("message_id", "user_id"),)


class UserEmailVerification(models.Model):
    id = fields.BigIntField(pk=True)
    user_id = fields.IntField()
    email = fields.CharField(max_length=255)
    token_hash = fields.CharField(max_length=255)
    expires_at = fields.DatetimeField()
    used_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    request_ip = fields.CharField(max_length=50, null=True)

    class Meta:
        table = "user_email_verifications"
