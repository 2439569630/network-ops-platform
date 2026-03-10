
from tortoise import fields, models

class Role(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    code = fields.CharField(max_length=50, unique=True)
    description = fields.TextField(null=True)
    is_default = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "roles"

class Permission(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    code = fields.CharField(max_length=100, unique=True)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "permissions"

class UserRole(models.Model):
    # Composite PK (user_id, role_id) in legacy SQL.
    # Tortoise needs single PK. We will add 'id' column via migration if needed, 
    # or check if it exists.
    # Usually join tables don't have ID in manual schema, but Tortoise ManyToMany usually manages it.
    # However, these are existing tables.
    # I'll add an ID field to the table via migration script like I did for site_message_reads.
    id = fields.BigIntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="user_roles")
    role = fields.ForeignKeyField("models.Role", related_name="user_roles")

    class Meta:
        table = "user_roles"
        unique_together = (("user", "role"),)

class RolePermission(models.Model):
    # Same here, likely needs ID.
    id = fields.BigIntField(pk=True)
    role = fields.ForeignKeyField("models.Role", related_name="role_permissions")
    permission = fields.ForeignKeyField("models.Permission", related_name="role_permissions")

    class Meta:
        table = "role_permissions"
        unique_together = (("role_id", "permission_id"),)
