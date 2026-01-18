from tortoise import fields, models
from app.models.orm.device import NetworkDevice

class DeviceInterface(models.Model):
    """
    网络设备接口表
    存储设备的物理/逻辑接口信息
    """
    id = fields.IntField(pk=True)
    device = fields.ForeignKeyField('models.NetworkDevice', related_name='interfaces', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255, description="接口名称")
    
    # 状态信息
    phy_state = fields.CharField(max_length=50, null=True, description="物理状态 (up/down)")
    protocol_state = fields.CharField(max_length=50, null=True, description="协议状态 (up/down)")
    
    # 统计信息
    in_uti = fields.CharField(max_length=50, null=True, description="入流量利用率")
    out_uti = fields.CharField(max_length=50, null=True, description="出流量利用率")
    in_errors = fields.CharField(max_length=50, null=True, description="入方向错误包")
    out_errors = fields.CharField(max_length=50, null=True, description="出方向错误包")
    
    # 详细信息
    description = fields.CharField(max_length=512, null=True, description="接口描述")
    ip_address = fields.CharField(max_length=100, null=True, description="接口IP地址")
    mac_address = fields.CharField(max_length=100, null=True, description="MAC地址")
    
    last_updated = fields.DatetimeField(auto_now=True, description="最后更新时间")

    class Meta:
        table = "device_interfaces"
        unique_together = (("device", "name"),)
