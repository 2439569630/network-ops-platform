from __future__ import annotations

from dataclasses import dataclass
import logging
import random
from typing import Optional


@dataclass(frozen=True)
class SSHFailureDecision:
    category: str
    reason: str
    base_delay_seconds: float
    max_delay_seconds: float
    log_level: int = logging.WARNING

    def next_delay_seconds(self, failure_count: int) -> float:
        n = max(1, int(failure_count or 1))
        base = float(self.base_delay_seconds or 0.0)
        cap = float(self.max_delay_seconds or 0.0)
        if base <= 0:
            base = 1.0
        if cap <= 0:
            cap = base
        exp = min(cap, base * (2 ** max(0, n - 1)))
        jitter = exp * random.uniform(-0.2, 0.2)
        return max(0.0, min(cap, exp + jitter))


def compact_exception_message(e: BaseException) -> str:
    try:
        s = str(e) if e is not None else ""
    except Exception:
        s = ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    first = s.split("\n", 1)[0].strip()
    name = type(e).__name__ if e is not None else ""
    if first:
        return f"{name}: {first}" if name and not first.startswith(name) else first
    return name or ""


def classify_ssh_failure(
    e: Optional[BaseException],
    *,
    default_base_delay_seconds: float = 30.0,
    default_max_delay_seconds: float = 300.0,
) -> SSHFailureDecision:
    msg = compact_exception_message(e) if e is not None else ""
    raw = msg.lower()

    if any(k in raw for k in ["authentication failed", "bad authentication type", "not allowed"]):
        return SSHFailureDecision(
            category="auth",
            reason=msg or "认证失败",
            base_delay_seconds=300.0,
            max_delay_seconds=3600.0,
            log_level=logging.ERROR,
        )

    if any(k in raw for k in ["error reading ssh protocol banner", "protocol banner", "not a valid ssh transport"]):
        return SSHFailureDecision(
            category="not_ssh",
            reason=msg or "SSH 协议横幅读取失败",
            base_delay_seconds=300.0,
            max_delay_seconds=1800.0,
            log_level=logging.ERROR,
        )

    if any(k in raw for k in ["connection refused", "no route to host", "name or service not known", "nodename nor servname"]):
        return SSHFailureDecision(
            category="unreachable",
            reason=msg or "网络不可达或端口拒绝",
            base_delay_seconds=120.0,
            max_delay_seconds=1800.0,
            log_level=logging.ERROR,
        )

    if any(k in raw for k in ["eoferror", "connection reset by peer", "broken pipe", "socket is closed", "bad file descriptor"]):
        return SSHFailureDecision(
            category="dropped",
            reason=msg or "连接被对端中断",
            base_delay_seconds=max(5.0, float(default_base_delay_seconds or 0.0)),
            max_delay_seconds=max(60.0, float(default_max_delay_seconds or 0.0)),
            log_level=logging.WARNING,
        )

    if any(k in raw for k in ["timed out", "timeout", "read timeout"]):
        return SSHFailureDecision(
            category="timeout",
            reason=msg or "连接超时",
            base_delay_seconds=max(10.0, float(default_base_delay_seconds or 0.0)),
            max_delay_seconds=max(120.0, float(default_max_delay_seconds or 0.0)),
            log_level=logging.WARNING,
        )

    if msg:
        return SSHFailureDecision(
            category="unknown",
            reason=msg,
            base_delay_seconds=float(default_base_delay_seconds or 30.0),
            max_delay_seconds=float(default_max_delay_seconds or 300.0),
            log_level=logging.WARNING,
        )

    return SSHFailureDecision(
        category="unknown",
        reason="连接失败",
        base_delay_seconds=float(default_base_delay_seconds or 30.0),
        max_delay_seconds=float(default_max_delay_seconds or 300.0),
        log_level=logging.WARNING,
    )
