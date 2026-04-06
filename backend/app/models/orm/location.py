
from tortoise import fields, models

class LocationNode(models.Model):
    id = fields.BigIntField(pk=True)
    parent_id = fields.BigIntField(null=True)
    name = fields.TextField()
    type = fields.TextField()
    code = fields.CharField(max_length=255, null=True, unique=True)
    address = fields.TextField(null=True)
    description = fields.TextField(null=True)
    status = fields.BooleanField(default=True)
    sort_order = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "location_nodes"

class LocationNodeRole(models.Model):
    # Need ID for Tortoise
    id = fields.BigIntField(pk=True)
    node_id = fields.BigIntField()
    role_id = fields.BigIntField()

    class Meta:
        table = "location_node_roles"
        unique_together = (("node_id", "role_id"),)

class LocationNodeUser(models.Model):
    # Need ID for Tortoise
    id = fields.BigIntField(pk=True)
    node_id = fields.BigIntField()
    user_id = fields.BigIntField()

    class Meta:
        table = "location_node_users"
        unique_together = (("node_id", "user_id"),)

class LocationNodeDevice(models.Model):
    id = fields.BigIntField(pk=True)
    node_id = fields.BigIntField()
    device_id = fields.IntField(unique=True)  # One device -> One location

    class Meta:
        table = "location_node_devices"
