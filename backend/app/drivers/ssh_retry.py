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


def _split_exception_compact_message(msg: str) -> tuple[str, str]:
    s = str(msg or "").strip()
    if not s:
        return "", ""
    if ": " in s:
        head, tail = s.split(": ", 1)
        head = head.strip()
        tail = tail.strip()
        if head and head.replace("_", "").isalnum():
            return head, tail
    return "", s


def _extract_cn_detail_from_raw(raw: str) -> str:
    r = str(raw or "").strip().lower()
    if not r:
        return ""

    if "tcp connection to device failed" in r or ("tcp connection" in r and "failed" in r):
        return "TCP 连接失败"
    if "connection refused" in r:
        return "端口拒绝"
    if "no route to host" in r:
        return "无到主机路由"
    if "name or service not known" in r or "nodename nor servname" in r:
        return "域名解析失败"
    if "connection reset by peer" in r:
        return "连接被对端重置"
    if "broken pipe" in r:
        return "连接管道破裂"
    if "socket is closed" in r or "bad file descriptor" in r:
        return "连接已关闭"
    if "error reading ssh protocol banner" in r or "protocol banner" in r:
        return "SSH 横幅读取失败"
    if "authentication failed" in r or "bad authentication type" in r or "not allowed" in r:
        return "认证失败"
    if "read timeout" in r:
        return "读取超时"
    if "timed out" in r or "timeout" in r:
        return "连接超时"

    return ""


def _format_cn_reason(*, base: str, raw: str) -> str:
    detail = _extract_cn_detail_from_raw(raw)
    base = str(base or "").strip() or "连接失败"
    if not detail or detail == base:
        return base
    return f"{base}: {detail}"


def classify_ssh_failure(
    e: Optional[BaseException],
    *,
    default_base_delay_seconds: float = 30.0,
    default_max_delay_seconds: float = 300.0,
) -> SSHFailureDecision:
    msg = compact_exception_message(e) if e is not None else ""
    _, tail = _split_exception_compact_message(msg)
    raw = msg.lower()

    if any(k in raw for k in ["authentication failed", "bad authentication type", "not allowed"]):
        return SSHFailureDecision(
            category="auth",
            reason=_format_cn_reason(base="认证失败", raw=tail),
            base_delay_seconds=300.0,
            max_delay_seconds=3600.0,
            log_level=logging.ERROR,
        )

    if any(k in raw for k in ["error reading ssh protocol banner", "protocol banner", "not a valid ssh transport"]):
        return SSHFailureDecision(
            category="not_ssh",
            reason=_format_cn_reason(base="SSH 协议异常", raw=tail),
            base_delay_seconds=300.0,
            max_delay_seconds=1800.0,
            log_level=logging.ERROR,
        )

    if any(k in raw for k in ["connection refused", "no route to host", "name or service not known", "nodename nor servname"]):
        return SSHFailureDecision(
            category="unreachable",
            reason=_format_cn_reason(base="网络不可达", raw=tail),
            base_delay_seconds=120.0,
            max_delay_seconds=1800.0,
            log_level=logging.ERROR,
        )

    if any(k in raw for k in ["eoferror", "connection reset by peer", "broken pipe", "socket is closed", "bad file descriptor"]):
        return SSHFailureDecision(
            category="dropped",
            reason=_format_cn_reason(base="连接被中断", raw=tail),
            base_delay_seconds=max(5.0, float(default_base_delay_seconds or 0.0)),
            max_delay_seconds=max(60.0, float(default_max_delay_seconds or 0.0)),
            log_level=logging.WARNING,
        )

    if any(k in raw for k in ["timed out", "timeout", "read timeout"]):
        return SSHFailureDecision(
            category="timeout",
            reason=_format_cn_reason(base="连接超时", raw=tail),
            base_delay_seconds=max(10.0, float(default_base_delay_seconds or 0.0)),
            max_delay_seconds=max(120.0, float(default_max_delay_seconds or 0.0)),
            log_level=logging.WARNING,
        )

    if msg:
        base = "连接失败"
        detail = _extract_cn_detail_from_raw(tail or msg)
        reason = f"{base}: {detail}" if detail else base
        return SSHFailureDecision(
            category="unknown",
            reason=reason,
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
