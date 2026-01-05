import asyncio
import logging
import subprocess
import sys
import os
import psutil
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from auth.security import verify_token, allow_admin, verify_token_ws
import aiofiles

router = APIRouter(prefix="/system/trap", tags=["System Trap Manager"])
logger = logging.getLogger(__name__)

# PID 文件路径 (Server 目录下)
# 当前文件在 Server/Routers/System/trap_manage.py
# dirname -> Server/Routers/System
# dirname -> Server/Routers
# dirname -> Server
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PID_FILE = os.path.join(BASE_DIR, 'trap_service.pid')
SCRIPT_PATH = os.path.join(BASE_DIR, 'trap_service_main.py')
LOG_FILE = os.path.join(BASE_DIR, 'logs', 'trap_service.log')

from Config.sys_config import SystemConfig

# ... (之前的变量定义)

def get_process_status():
    """获取 Trap 服务进程状态"""
    pid = None
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
        except:
            pass
            
    if pid:
        if psutil.pid_exists(pid):
            try:
                p = psutil.Process(pid)
                # 检查进程名是否匹配 (简单的检查)
                if 'python' in p.name().lower():
                    return {"status": "running", "pid": pid, "memory": p.memory_info().rss, "cpu": p.cpu_percent()}
            except psutil.NoSuchProcess:
                pass
    
    return {"status": "stopped", "pid": None}

def _start_service_internal():
    """内部启动逻辑，不依赖 API 上下文"""
    status = get_process_status()
    if status['status'] == 'running':
        return True, "服务已在运行中"
    
    try:
        python_exe = sys.executable
        env = os.environ.copy()
        
        # 打开日志文件用于追加
        # 注意：这里直接打开文件句柄传给子进程
        # Windows 下需要允许子进程继承句柄，但在 Popen 中通常默认继承 stdout/stderr
        
        # 确保日志目录存在
        log_dir = os.path.dirname(LOG_FILE)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        stdout_log = open(LOG_FILE, 'a', encoding='utf-8')
        
        if sys.platform == 'win32':
             process = subprocess.Popen(
                [python_exe, SCRIPT_PATH],
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=os.path.dirname(SCRIPT_PATH),
                env=env,
                stdout=stdout_log,
                stderr=subprocess.STDOUT # 将 stderr 重定向到 stdout
            )
        else:
            process = subprocess.Popen(
                [python_exe, SCRIPT_PATH],
                cwd=os.path.dirname(SCRIPT_PATH),
                env=env,
                stdout=stdout_log,
                stderr=subprocess.STDOUT
            )
            
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
            
        logger.info(f"Trap 服务已启动, PID: {process.pid}")
        return True, "服务启动成功"
        
    except Exception as e:
        logger.error(f"启动 Trap 服务失败: {e}")
        return False, f"启动失败: {str(e)}"

@router.websocket("/ws")
async def trap_manage_ws(websocket: WebSocket):
    await websocket.accept()
    
    try:
        token = websocket.query_params.get("token")
        user = await verify_token_ws(websocket, token)
        if not user:
            logger.warning("WebSocket authentication failed")
            await websocket.close(code=1008)
            return
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        await websocket.close(code=1008)
        return

    # 初始状态
    last_pos = 0
    # 如果日志文件存在，先读取最后 2KB (避免一次读太多)
    if os.path.exists(LOG_FILE):
        try:
            last_pos = os.path.getsize(LOG_FILE)
            # 初始推送最后一点日志
            async with aiofiles.open(LOG_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
                # 简单处理：如果文件不大，全部读；如果很大，seek 到末尾前 2000 字节
                if last_pos > 2000:
                    await f.seek(last_pos - 2000)
                    # 丢弃第一行可能不完整的
                    await f.readline()
                else:
                    await f.seek(0)
                
                content = await f.read()
                if content:
                    await websocket.send_json({
                        "type": "log",
                        "data": content.splitlines()
                    })
                
                # 更新位置到末尾
                last_pos = await f.tell()
        except Exception as e:
            logger.error(f"WS init log error: {e}")

    try:
        while True:
            # 检查连接状态
            if websocket.client_state.value == 3: # WebSocketState.DISCONNECTED
                break

            # 1. 推送状态
            try:
                status = get_process_status()
                await websocket.send_json({
                    "type": "status",
                    "data": status
                })
            except Exception as e:
                 # logger.error(f"WS send status error: {e}")
                 break # 发送失败通常意味着连接已断开
            
            # 2. 推送新增日志
            if os.path.exists(LOG_FILE):
                try:
                    current_size = os.path.getsize(LOG_FILE)
                    if current_size < last_pos:
                        # 文件可能被轮转或截断，重置
                        last_pos = 0
                    
                    if current_size > last_pos:
                        async with aiofiles.open(LOG_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
                            await f.seek(last_pos)
                            new_content = await f.read()
                            if new_content:
                                await websocket.send_json({
                                    "type": "log",
                                    "data": new_content.splitlines()
                                })
                            last_pos = await f.tell()
                except Exception as log_e:
                    logger.error(f"WS read log error: {log_e}")
                    # 日志读取错误不一定要断开 WS，但如果是发送错误则会在 send_json 时抛出
            
            # 等待 1 秒
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info("Trap Manage WS disconnected")
    except Exception as e:
        if "Cannot call" not in str(e): # 忽略重复的关闭错误
            logger.error(f"Trap WS main loop error: {e}")

@router.get("/config")
async def get_trap_config(user = Depends(verify_token)):
    """获取 Trap 服务配置"""
    autostart = SystemConfig.get("trap_autostart", "false") == "true"
    return {"code": 200, "data": {"autostart": autostart}}

@router.post("/config")
async def update_trap_config(data: dict, user = Depends(allow_admin)):
    """更新 Trap 服务配置"""
    autostart = str(data.get("autostart", False)).lower()
    
    # 保存到数据库 (通过 SystemConfig 间接保存，或者直接写 DB)
    # 这里直接用 DB 操作
    from DataBase import PostgreSQL
    sql = """
        INSERT INTO system_settings (key, value, description, group_name)
        VALUES ('trap_autostart', $1, 'Trap服务开机自启', 'system')
        ON CONFLICT (key) DO UPDATE 
        SET value = EXCLUDED.value
    """
    await PostgreSQL.execute(sql, autostart)
    await SystemConfig.refresh()
    
    return {"code": 200, "message": "配置已更新"}

@router.get("/status")
async def get_trap_status(user = Depends(verify_token)):
    """获取 Trap 服务状态"""
    return {"code": 200, "data": get_process_status()}

@router.post("/start")
async def start_trap_service(user = Depends(allow_admin)):
    """启动 Trap 服务"""
    success, msg = _start_service_internal()
    if success:
        return {"code": 200, "message": msg}
    else:
        return {"code": 500, "message": msg}

@router.post("/stop")
# ... (Stop 逻辑保持不变)

@router.post("/stop")
async def stop_trap_service(user = Depends(allow_admin)):
    """停止 Trap 服务"""
    status = get_process_status()
    if status['status'] != 'running':
        return {"code": 400, "message": "服务未运行"}
        
    pid = status['pid']
    try:
        p = psutil.Process(pid)
        p.terminate() # 尝试优雅关闭
        
        try:
            p.wait(timeout=3)
        except psutil.TimeoutExpired:
            p.kill() # 强制关闭
            
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            
        return {"code": 200, "message": "服务已停止"}
    except Exception as e:
        logger.error(f"停止 Trap 服务失败: {e}")
        return {"code": 500, "message": f"停止失败: {str(e)}"}

@router.get("/logs")
async def get_trap_logs(lines: int = 100, user = Depends(verify_token)):
    """获取 Trap 服务日志"""
    if not os.path.exists(LOG_FILE):
        return {"code": 200, "data": []}
        
    try:
        # 读取最后 N 行
        # 简单实现：读取整个文件取最后 N 行 (文件不大时)
        # 优化实现：seek 到末尾倒推
        
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            # 简单的全量读取 (生产环境需优化)
            content = f.readlines()
            return {"code": 200, "data": content[-lines:]}
    except Exception as e:
        return {"code": 500, "message": f"读取日志失败: {e}"}
