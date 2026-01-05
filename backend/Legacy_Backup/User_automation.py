import asyncio
import logging
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Body
from DataBase import PostgreSQL
from auth.security import verify_token_ws, verify_token, allow_admin
from DeviceLayer.snmp_provisioner import SnmpProvisioner
from typing import List, Dict
from Config.sys_config import SystemConfig

router = APIRouter(prefix="/user/automation", tags=["Automation"])
logger = logging.getLogger(__name__)

@router.get("/snmp/config")
async def get_snmp_config(user = Depends(verify_token)):
    """获取 SNMP 默认配置"""
    config = {
        "community": SystemConfig.get("snmp_default_community", "public"),
        "access": SystemConfig.get("snmp_default_access", "ro"),
        "trap_host": SystemConfig.get("snmp_default_trap_host", "")
    }
    return {"code": 200, "data": config}

@router.post("/snmp/config")
async def save_snmp_config(config: Dict[str, str] = Body(...), user = Depends(verify_token)):
    """保存 SNMP 默认配置"""
    try:
        # 更新或插入配置
        # 这里为了简单，直接遍历更新，假设 SystemConfig 能够处理
        # 但 SystemConfig 主要用于读取。我们需要直接操作数据库。
        
        settings = [
            ("snmp_default_community", config.get("community", "public"), "SNMP 默认团体名", "snmp"),
            ("snmp_default_access", config.get("access", "ro"), "SNMP 默认权限", "snmp"),
            ("snmp_default_trap_host", config.get("trap_host", ""), "SNMP 默认 Trap 主机", "snmp")
        ]
        
        for key, value, desc, group in settings:
            # Upsert logic
            # PostgreSQL 9.5+ supports ON CONFLICT
            sql = """
                INSERT INTO system_settings (key, value, description, group_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (key) DO UPDATE 
                SET value = EXCLUDED.value
            """
            await PostgreSQL.execute(sql, key, value, desc, group)
            
        # 刷新内存缓存
        await SystemConfig.refresh()
        
        return {"code": 200, "message": "配置保存成功"}
    except Exception as e:
        logger.error(f"保存 SNMP 配置失败: {e}")
        return {"code": 500, "message": "保存失败"}

@router.get("/candidates")
async def get_snmp_candidates(user = Depends(verify_token)):
    """获取可以配置 SNMP 的设备列表 (在线且未配置/或需重新配置)"""
    # 仅允许网络设备配置 SNMP，允许覆盖下发
    sql = """
        SELECT id, device_name, ipv4, device_type, online_status 
        FROM network_devices 
        WHERE device_type IN ('router', 'switch', 'firewall', 'huawei', '路由器', '交换机', '防火墙')
    """
    rows = await PostgreSQL.execute(sql, fetch=True)
    
    # 转换为 dict 列表
    result = []
    if rows:
        for r in rows:
            result.append({
                'id': r['id'],
                'label': f"{r['device_name']} ({r['ipv4']})",
                'ipv4': str(r['ipv4']),
                'type': r['device_type'],
                'disabled': not r['online_status'] # 离线设备不可配置
            })
            
    return {"code": 200, "data": result}

@router.websocket("/ws/snmp")
async def websocket_snmp_provision(websocket: WebSocket):
    await websocket.accept()
    
    token = websocket.query_params.get("token")
    user = await verify_token_ws(websocket, token)
    if not user:
        return

    try:
        # 等待前端发送配置指令
        data = await websocket.receive_json()
        # 格式: { community: 'public', access: 'ro', trap_host: '...', device_ids: [1, 2] }
        
        community = data.get('community', 'public')
        access = data.get('access', 'ro')
        trap_host = data.get('trap_host')
        device_ids = data.get('device_ids', [])
        
        if not device_ids:
            await websocket.send_text("未选择任何设备。")
            await websocket.close()
            return

        await websocket.send_text(f"开始任务: 配置 {len(device_ids)} 台设备...")
        
        # 异步回调，用于推送日志
        async def log_callback(msg):
            try:
                await websocket.send_text(msg)
            except:
                pass

        # 逐个执行 (也可以用 asyncio.gather 并发，但为了日志清晰，这里用顺序执行或小批量并发)
        # 这里演示顺序执行
        for dev_id in device_ids:
            # 获取设备详情
            sql = "SELECT * FROM network_devices WHERE id = $1"
            device_info = await PostgreSQL.execute(sql, dev_id, fetch_row=True)
            
            if not device_info:
                await log_callback(f"设备 ID {dev_id} 未找到，跳过。")
                continue
                
            config = {
                'community': community,
                'access': access,
                'trap_host': trap_host
            }
            
            success = await SnmpProvisioner.provision_device(device_info, config, log_callback)
            
            if success:
                # 更新数据库中的 snmp_community 字段，以便后续监控模块使用
                try:
                    update_sql = "UPDATE network_devices SET snmp_community = $1 WHERE id = $2"
                    await PostgreSQL.execute(update_sql, community, dev_id)
                    await log_callback(f"数据库记录已更新。")
                except Exception as db_e:
                    logger.error(f"Failed to update snmp_community in DB: {db_e}")
            
        await websocket.send_text("所有任务执行完毕。")
        # 保持连接一会儿，让前端有机会看到最后一条消息，或者由前端主动断开
        await websocket.receive_text() # 等待关闭

    except WebSocketDisconnect:
        logger.info("Automation WS disconnected")
    except Exception as e:
        logger.error(f"Automation WS Error: {e}")
        try:
            await websocket.send_text(f"系统错误: {str(e)}")
        except:
            pass
