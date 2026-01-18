
from tortoise import fields, models

class RepairOrder(models.Model):
    """报修工单模型"""
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    submitter_id = fields.IntField()
    device_id = fields.IntField(null=True)
    location_id = fields.BigIntField(null=True)
    assignee_id = fields.IntField(null=True)
    priority = fields.CharField(max_length=50, default="normal") # low, normal, high, emergency
    status = fields.CharField(max_length=50, default="pending") # pending, processing, completed, closed, need_info
    actual_completion_time = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "repair_orders"

class OrderLog(models.Model):
    """工单操作日志模型"""
    id = fields.BigIntField(pk=True)
    order_id = fields.IntField()
    operator_id = fields.IntField()
    action = fields.CharField(max_length=50)
    from_status = fields.CharField(max_length=50, null=True)
    to_status = fields.CharField(max_length=50, null=True)
    remark = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "order_logs"

class OrderReview(models.Model):
    """工单评价模型"""
    id = fields.BigIntField(pk=True)
    order_id = fields.IntField()
    rating = fields.IntField()
    comment = fields.TextField(null=True)
    response_time_rating = fields.IntField(null=True)
    service_quality_rating = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "order_reviews"

class WorkLog(models.Model):
    """工单工作记录模型"""
    id = fields.BigIntField(pk=True)
    order_id = fields.IntField()
    operator_id = fields.IntField(null=True)
    content = fields.TextField()
    images = fields.JSONField(default=[]) # List of image URLs
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "work_logs"
