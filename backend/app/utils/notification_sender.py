import aiosmtplib
from email.mime.text import MIMEText
from email.header import Header
import httpx
import logging
import json

logger = logging.getLogger(__name__)

async def send_email(host, port, username, password, to_email, subject, content):
    """发送邮件"""
    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = username
        message['To'] = to_email
        message['Subject'] = Header(subject, 'utf-8')

        # 尝试连接 SMTP (支持 SSL 和 TLS)
        # 注意：这里简化处理，假设 465 是 SSL，其他尝试 STARTTLS 或普通
        use_tls = False
        if str(port) == '465':
             use_tls = True
        
        # aiosmtplib 用法
        await aiosmtplib.send(
            message,
            hostname=host,
            port=int(port),
            username=username,
            password=password,
            use_tls=use_tls,
            # start_tls=not use_tls # 如果不是 SSL 端口，通常尝试 STARTTLS
        )
        return True, "发送成功"
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False, str(e)

async def send_pushplus(token, content, title="系统通知"):
    """发送 PushPlus 通知"""
    try:
        url = "http://www.pushplus.plus/send"
        data = {
            "token": token,
            "title": title,
            "content": content,
            "template": "html"
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data)
            result = resp.json()
            if result.get('code') == 200:
                return True, "发送成功"
            else:
                return False, result.get('msg', '未知错误')
    except Exception as e:
        logger.error(f"PushPlus 发送失败: {e}")
        return False, str(e)

async def send_http(url, content, title="系统通知"):
    """发送 HTTP 回调"""
    try:
        data = {
            "title": title,
            "message": content,
            "timestamp": "now" # 实际应为时间戳
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data)
            if 200 <= resp.status_code < 300:
                return True, "发送成功"
            else:
                return False, f"HTTP 状态码: {resp.status_code}"
    except Exception as e:
        logger.error(f"HTTP 回调失败: {e}")
        return False, str(e)
