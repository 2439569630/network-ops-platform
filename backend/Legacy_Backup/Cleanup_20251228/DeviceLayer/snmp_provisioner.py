import asyncio
import logging
from typing import Dict, Any, List
from netmiko import ConnectHandler
from datetime import datetime

logger = logging.getLogger(__name__)

class SnmpProvisioner:
    """
    SNMP 自动化配置下发器
    """
    
    @staticmethod
    def get_commands(device_type: str, community: str, access: str, trap_host: str = None) -> List[str]:
        """
        根据设备类型生成配置命令
        """
        commands = []
        dt = device_type.lower()
        
        # 权限转换
        # Cisco: ro / rw
        # Huawei: read / write
        is_ro = access.lower() in ['ro', 'read']
        
        if 'huawei' in dt:
            # Huawei 配置
            # snmp-agent community {read|write} cipher {community}
            perm = 'read' if is_ro else 'write'
            commands.append("system-view")
            commands.append("snmp-agent") # Enable SNMP
            commands.append("snmp-agent sys-info version v2c")
            commands.append(f"snmp-agent community {perm} cipher {community}")
            if trap_host:
                commands.append(f"snmp-agent target-host trap address udp-domain {trap_host} params securityname {community} v2c")
                commands.append("snmp-agent trap enable")
            # Huawei 保存配置
            # commands.append("return") # 通常 Netmiko 会处理退出 config 模式
            # save 需要交互，Netmiko send_command 支持 expect_string，或者用 save_config()
            
        elif 'cisco' in dt or 'ios' in dt:
            # Cisco IOS 配置
            # snmp-server community {community} {ro|rw}
            perm = 'ro' if is_ro else 'rw'
            commands.append(f"snmp-server community {community} {perm}")
            if trap_host:
                commands.append(f"snmp-server host {trap_host} version 2c {community}")
                commands.append("snmp-server enable traps")
                
        else:
            # 默认尝试 Cisco 风格
            perm = 'ro' if is_ro else 'rw'
            commands.append(f"snmp-server community {community} {perm}")

        return commands

    @staticmethod
    async def provision_device(device_info: Dict[str, Any], config: Dict[str, Any], log_callback=None) -> bool:
        """
        对单个设备执行配置下发
        
        Args:
            device_info: 数据库中的设备记录 (dict)
            config: 配置参数 {community, access, trap_host}
            log_callback: 异步回调函数，用于发送日志 await log_callback(msg)
        """
        ip = device_info.get('ipv4')
        username = device_info.get('user_name')
        password = device_info.get('password')
        device_type = device_info.get('device_type', 'cisco_ios')
        # 简单映射 device_type 到 netmiko device_type
        if 'huawei' in device_type.lower():
            netmiko_type = 'huawei'
        elif 'cisco' in device_type.lower():
            netmiko_type = 'cisco_ios'
        elif 'linux' in device_type.lower():
            # Linux 通常用 snmpd.conf，这里暂不支持或需特殊处理
            if log_callback:
                await log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {ip}: 暂不支持 Linux 自动配置 SNMP")
            return False
        else:
            netmiko_type = 'cisco_ios' # 默认

        port = device_info.get('ssh_port', 22)

        device_params = {
            'device_type': netmiko_type,
            'host': str(ip),
            'username': username,
            'password': password,
            'port': port,
            'timeout': 10,
            'banner_timeout': 30,
            'auth_timeout': 10
        }

        async def log(msg):
            if log_callback:
                await log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

        try:
            await log(f"正在连接 {device_info.get('device_name', ip)} ({ip})...")
            
            # 在线程池中运行阻塞的 Netmiko 操作
            loop = asyncio.get_event_loop()
            
            def _connect_and_config():
                with ConnectHandler(**device_params) as ssh:
                    # 生成命令
                    cmds = SnmpProvisioner.get_commands(
                        device_type=device_type, 
                        community=config['community'], 
                        access=config['access'],
                        trap_host=config.get('trap_host')
                    )
                    
                    output_log = []
                    output_log.append(f"连接成功，准备下发 {len(cmds)} 条命令...")
                    
                    # 发送配置
                    # Netmiko 的 send_config_set 自动进入 config 模式
                    output = ssh.send_config_set(cmds)
                    output_log.append(f"命令执行结果:\n{output}")
                    
                    # 保存配置
                    output_log.append("正在保存配置...")
                    save_out = ssh.save_config()
                    output_log.append(f"保存结果: {save_out}")
                    
                    return "\n".join(output_log)

            # 执行
            result = await loop.run_in_executor(None, _connect_and_config)
            
            await log(result)
            await log(f"{device_info.get('device_name')} 配置完成。")
            return True

        except Exception as e:
            logger.error(f"Config provision error for {ip}: {e}")
            await log(f"错误: {str(e)}")
            return False
