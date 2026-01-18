from tortoise import fields, models
from app.models.orm.device import NetworkDevice

class DeviceVlan(models.Model):
    """
    网络设备 VLAN 表
    存储设备的 VLAN 配置信息
    """
    id = fields.IntField(pk=True)
    device = fields.ForeignKeyField('models.NetworkDevice', related_name='vlans', on_delete=fields.CASCADE)
    
    vlan_id = fields.IntField(description="VLAN ID")
    type = fields.CharField(max_length=50, null=True, description="VLAN 类型 (common/dynamic)")
    status = fields.CharField(max_length=50, null=True, description="VLAN 状态 (enable/disable)")
    mac_learning = fields.CharField(max_length=50, null=True, description="MAC 地址学习状态")
    
    # 端口列表通常较长，可以使用 JSONField 或 TextField 存储
    # 例如: ["GigabitEthernet0/0/1", "GigabitEthernet0/0/2"]
    ports = fields.JSONField(default=list, description="包含的端口列表")
    
    description = fields.CharField(max_length=512, null=True, description="VLAN 描述")
    
    last_updated = fields.DatetimeField(auto_now=True, description="最后更新时间")

    class Meta:
        table = "device_vlans"
        unique_together = (("device", "vlan_id"),)
