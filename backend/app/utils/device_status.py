from __future__ import annotations

from typing import Any, Dict

from app.drivers.models.status import DeviceStatus


ONLINE_FSM_STATES = {
    "online",
    "recovering",
    "degraded",
    "checking",
    "collecting",
    "reloading",
}


def normalize_fsm_state(value: Any) -> str:
    s = str(value or "").strip()
    return s or "init"


def is_online_fsm_state(fsm_state: Any) -> bool:
    return normalize_fsm_state(fsm_state) in ONLINE_FSM_STATES


def compute_display_status(fsm_state: Any) -> str:
    state = normalize_fsm_state(fsm_state)
    return DeviceStatus(fsm_state=state).label()


def status_fields_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    fsm_state = normalize_fsm_state(snapshot.get("fsm_state"))
    fsm_reason = str(snapshot.get("fsm_reason") or "")
    fsm_updated = str(snapshot.get("fsm_updated") or "")
    online_status = bool(snapshot.get("online_status")) or is_online_fsm_state(fsm_state)
    connectivity = "online" if online_status else "offline"
    display_status = str(snapshot.get("display_status") or snapshot.get("status") or "").strip()
    if not display_status:
        display_status = compute_display_status(fsm_state)
    return {
        "fsm_state": fsm_state,
        "fsm_reason": fsm_reason,
        "fsm_updated": fsm_updated,
        "online_status": online_status,
        "connectivity": connectivity,
        "display_status": display_status,
        "fsmState": fsm_state,
        "fsmReason": fsm_reason,
        "fsmUpdated": fsm_updated,
        "displayStatus": display_status,
    }
