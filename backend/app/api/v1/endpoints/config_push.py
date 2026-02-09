import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query

from app.core.redis import redis_manager
from app.core.security import PermissionChecker, user_has_permission, user_is_super, verify_token_ws, UnicornException, get_or_init_user_auth_version
from app.schemas.config_push import ConfigPushJobCreateRequest
from app.services.config_push_service import ConfigPushService, normalize_command_list


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/jobs")
async def create_config_push_job(
    req: ConfigPushJobCreateRequest,
    user_data: dict = Depends(PermissionChecker(["sys:config:push"])),
):
    commands = normalize_command_list(req.commands, req.commands_text)
    job_id = await ConfigPushService.create_job(
        creator_id=int(user_data.get("id")),
        title=req.title,
        device_ids=req.device_ids,
        commands=commands,
    )
    return {"code": 200, "data": {"job_id": int(job_id), "status": "pending"}}


@router.get("/jobs/{job_id}")
async def get_config_push_job(
    job_id: int,
    user_data: dict = Depends(PermissionChecker(["sys:config:push"])),
):
    payload = await ConfigPushService.get_job(int(job_id))
    job = payload.get("job") or {}
    if not user_is_super(user_data):
        if int(job.get("creator_id") or 0) != int(user_data.get("id") or 0):
            raise UnicornException(403, "权限不足")
    return {"code": 200, "data": payload}


@router.post("/jobs/{job_id}/cancel")
async def cancel_config_push_job(
    job_id: int,
    user_data: dict = Depends(PermissionChecker(["sys:config:push"])),
):
    payload = await ConfigPushService.get_job(int(job_id))
    job = payload.get("job") or {}
    if not user_is_super(user_data):
        if int(job.get("creator_id") or 0) != int(user_data.get("id") or 0):
            raise UnicornException(403, "权限不足")
    await ConfigPushService.cancel_job(int(job_id), actor_id=int(user_data.get("id") or 0))
    return {"code": 200}


@router.websocket("/ws/{job_id}")
async def config_push_ws(websocket: WebSocket, job_id: int, token: str | None = Query(None)):
    await websocket.accept()
    user = await verify_token_ws(websocket, token)
    if not user:
        return
    if not user_is_super(user):
        if not await user_has_permission(user, "sys:config:push"):
            try:
                await websocket.send_text("系统: 权限不足\r\n")
            except Exception:
                pass
            await websocket.close(code=4003, reason="权限不足")
            return

    try:
        job_payload = await ConfigPushService.get_job(int(job_id))
        job = job_payload.get("job") or {}
        if not user_is_super(user):
            if int(job.get("creator_id") or 0) != int(user.get("id") or 0):
                await websocket.close(code=4003, reason="权限不足")
                return
    except Exception:
        try:
            await websocket.close(code=4004, reason="任务不存在")
        except Exception:
            pass
        return

    last_id = str(websocket.query_params.get("last_id") or "0-0").strip() or "0-0"
    stream = ConfigPushService.events_stream(int(job_id))
    redis = redis_manager.get_client()

    try:
        token_auth_ver = user.get("auth_ver")
        try:
            token_auth_ver = int(token_auth_ver) if token_auth_ver is not None else None
        except Exception:
            token_auth_ver = None
        last_auth_check = 0.0
        while True:
            now = asyncio.get_running_loop().time()
            if token_auth_ver is not None and now - last_auth_check >= 2.0:
                last_auth_check = now
                current_ver = await get_or_init_user_auth_version(int(user.get("id") or 0))
                if int(current_ver) != int(token_auth_ver):
                    try:
                        await websocket.close(code=4001, reason="会话已失效")
                    except Exception:
                        pass
                    return
            try:
                res = await redis.xread({stream: last_id}, count=100, block=1000)
            except Exception:
                res = None
            if not res:
                await asyncio.sleep(0.05)
                continue
            for _stream_name, entries in res:
                for entry_id, fields in (entries or []):
                    last_id = str(entry_id)
                    payload: Dict[str, Any] = {"id": str(entry_id)}
                    if isinstance(fields, dict):
                        payload.update({str(k): v for k, v in fields.items()})
                    await websocket.send_json(payload)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.error(f"config-push ws error: {e}")
        try:
            await websocket.close(code=1011, reason="服务器错误")
        except Exception:
            pass
