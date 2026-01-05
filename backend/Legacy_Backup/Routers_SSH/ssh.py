import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
import paramiko
from DataBase import PostgreSQL
from auth.jwtTools import verify_token
from fastapi.exceptions import HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_token_from_query(token: str = Query(...)):
    try:
        # 验证 token
        user_data = verify_token(token)
        return user_data
    except Exception as e:
        logger.error(f"WebSocket 鉴权失败: {e}")
        return None

class SSHSession:
    def __init__(self, host: str, port: int = 22, username: str = "root", password: str = "123456"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.shell = None

    def connect(self):
        try:
            # 增加一些配置以提高兼容性
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,  # 增加超时时间
                allow_agent=False, # 禁用 ssh-agent
                look_for_keys=False, # 禁用寻找本地私钥
                banner_timeout=30,
                disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']} # 尝试禁用某些可能导致问题的算法
            )
            
            # 使用 invoke_shell 之前，可以先尝试 open_session
            # self.shell = self.client.invoke_shell(term='xterm', width=80, height=24) # 指定终端类型和大小
            # 为了更好的兼容性，特别是对某些网络设备，可能需要特定的参数
            transport = self.client.get_transport()
            transport.set_keepalive(30) # 发送 keepalive 包防止连接断开
            
            self.shell = self.client.invoke_shell()
            self.shell.settimeout(0.0) # Non-blocking
            return True, "连接成功"
        except paramiko.AuthenticationException:
            msg = f"认证失败：用户 {self.username}@{self.host}"
            logger.error(msg)
            return False, msg
        except paramiko.SSHException as e:
            msg = f"SSH 连接失败: {e}"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"连接错误: {e}"
            logger.error(msg)
            return False, msg

    def disconnect(self):
        if self.client:
            self.client.close()

    def send_command(self, command: str):
        if self.shell:
            try:
                self.shell.send(command)
            except Exception as e:
                logger.error(f"Send command error: {e}")

    def receive_output(self) -> bytes:
        if self.shell:
            try:
                if self.shell.recv_ready():
                    return self.shell.recv(4096)
            except Exception as e:
                logger.error(f"Receive output error: {e}")
                pass
        return None

@router.websocket("/ws/ssh/{ip}")
async def ssh_websocket(websocket: WebSocket, ip: str, token: str = Query(None)):
    # 手动鉴权
    user = None
    if token:
        try:
            user = verify_token(token)
        except:
            pass
            
    if not user:
        await websocket.close(code=1008)
        logger.warning(f"WebSocket connection rejected: unauthorized access to {ip}")
        return

    await websocket.accept()
    logger.info(f"User {user.get('sub', 'unknown')} connected to SSH for {ip}")
    
    # 发送初始日志到前端
    await websocket.send_text(f"系统: 已认证为用户 {user.get('sub', 'unknown')}.\r\n")
    await websocket.send_text(f"系统: 正在解析 {ip} 的凭据...\r\n")

    # 从数据库获取设备的 SSH 凭据
    sql = "SELECT user_name, password FROM network_devices WHERE ipv4 = $1 LIMIT 1"
    device_info = await PostgreSQL.execute(sql, ip, fetch_row=True)
    
    username = "root"
    password = "password"
    
    if device_info:
        if device_info.get('user_name'):
            username = device_info['user_name']
        if device_info.get('password'):
            password = device_info['password']
        await websocket.send_text(f"系统: 找到用户 '{username}' 的凭据。\r\n")
    else:
        logger.warning(f"No device found in DB for IP {ip}, using default credentials")
        await websocket.send_text(f"系统: 数据库中未找到凭据，使用默认值。\r\n")

    await websocket.send_text(f"系统: 正在连接到 {ip}...\r\n")
    
    ssh = SSHSession(host=ip, username=username, password=password)
    
    loop = asyncio.get_event_loop()
    
    try:
        # 在线程池中运行阻塞的连接操作
        connected, msg = await loop.run_in_executor(None, ssh.connect)
        
        if not connected:
            await websocket.send_text(f"错误: {msg}\r\n")
            await websocket.close()
            return

        await websocket.send_text(f"系统: {msg}\r\n")
        # 发送清屏指令 (ANSI escape code for clear screen)
        # \033[2J 清除屏幕, \033[H 将光标移动到左上角
        await websocket.send_text("\033[2J\033[H")

        async def read_from_ssh():
            while True:
                try:
                    output = await loop.run_in_executor(None, ssh.receive_output)
                    if output:
                        text = output.decode('utf-8', errors='ignore')
                        await websocket.send_text(text)
                    else:
                        await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Read error: {e}")
                    break

        read_task = asyncio.create_task(read_from_ssh())

        try:
            while True:
                data = await websocket.receive_text()
                # 确保发送的是换行符
                if not data.endswith('\r') and not data.endswith('\n'):
                    data += '\n'
                await loop.run_in_executor(None, ssh.send_command, data)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        finally:
            read_task.cancel()
            
    except Exception as e:
        error_msg = f"Error in SSH WebSocket: {e}"
        logger.error(error_msg)
        try:
            await websocket.send_text(f"System Error: {error_msg}\r\n")
        except:
            pass
    finally:
        ssh.disconnect()
