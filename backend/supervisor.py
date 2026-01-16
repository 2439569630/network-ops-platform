import logging
import os
import signal
import socket
import subprocess
import sys
import time


logger = logging.getLogger(__name__)


def _env_with(overrides: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    for k, v in (overrides or {}).items():
        env[str(k)] = str(v)
    return env


def _terminate_process(proc: subprocess.Popen, timeout_seconds: float = 8.0) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        return
    deadline = time.time() + float(timeout_seconds)
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    try:
        proc.kill()
    except Exception:
        return


def _check_port_available(host: str, port: int) -> bool:
    try:
        p = int(port)
    except Exception:
        return False
    if p <= 0 or p > 65535:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((str(host), int(p)))
        finally:
            s.close()
        return True
    except OSError:
        return False


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    project_root = os.path.abspath(os.path.dirname(__file__))
    python_exe = sys.executable

    log_dir = os.getenv("SUPERVISOR_LOG_DIR", "").strip() or os.getenv("LOG_DIR", "").strip() or "/tmp/bise-dev-logs"
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = "/tmp"
        os.makedirs(log_dir, exist_ok=True)

    fastapi_log_path = os.path.join(log_dir, "fastapi.log")
    monitor_log_path = os.path.join(log_dir, "monitor.log")

    fastapi_host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    fastapi_port = os.getenv("FASTAPI_PORT", "8000")
    fastapi_reload = str(os.getenv("FASTAPI_RELOAD", "")).strip() in {"1", "true", "TRUE", "yes", "YES"}
    fastapi_workers = os.getenv("FASTAPI_WORKERS", "").strip()
    try:
        fastapi_port_int = int(str(fastapi_port))
    except Exception:
        logger.error(f"Invalid FASTAPI_PORT: {fastapi_port}")
        return 1
    try:
        fastapi_workers_int = int(fastapi_workers) if fastapi_workers else 1
        if fastapi_workers_int <= 0:
            fastapi_workers_int = 1
    except Exception:
        fastapi_workers_int = 1
    if fastapi_reload and fastapi_workers_int > 1:
        logger.warning("FASTAPI_RELOAD is enabled; forcing FASTAPI_WORKERS=1")
        fastapi_workers_int = 1

    if not _check_port_available(fastapi_host, fastapi_port_int):
        logger.error(f"FastAPI port is already in use: {fastapi_host}:{fastapi_port_int}")
        logger.error("Stop the existing process or set FASTAPI_PORT to another value.")
        return 1

    fastapi_cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "asgi:app",
        "--host",
        fastapi_host,
        "--port",
        str(fastapi_port_int),
    ]
    if fastapi_reload:
        fastapi_cmd.append("--reload")
    if fastapi_workers_int > 1:
        fastapi_cmd.extend(["--workers", str(fastapi_workers_int)])

    monitor_cmd = [python_exe, os.path.join(project_root, "processes", "monitor_daemon.py")]

    fastapi_env = _env_with({"DISABLE_INTERNAL_MONITOR": "1"})
    monitor_env = os.environ.copy()

    logger.info(f"Starting FastAPI: {' '.join(fastapi_cmd)}")
    logger.info(f"Starting Monitor daemon: {' '.join(monitor_cmd)}")
    logger.info(f"FastAPI logs: {fastapi_log_path}")
    logger.info(f"Monitor logs: {monitor_log_path}")

    fastapi_log_fp = open(fastapi_log_path, "a", encoding="utf-8", buffering=1)
    monitor_log_fp = open(monitor_log_path, "a", encoding="utf-8", buffering=1)

    try:
        fastapi_proc = subprocess.Popen(
            fastapi_cmd,
            cwd=project_root,
            env=fastapi_env,
            stdout=fastapi_log_fp,
            stderr=fastapi_log_fp,
        )

        monitor_proc = subprocess.Popen(
            monitor_cmd,
            cwd=project_root,
            env=monitor_env,
            stdout=monitor_log_fp,
            stderr=monitor_log_fp,
        )
    except Exception:
        try:
            fastapi_log_fp.close()
        except Exception:
            pass
        try:
            monitor_log_fp.close()
        except Exception:
            pass
        raise

    stopping = False

    def _handle_signal(signum, _frame=None):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        logger.info(f"Supervisor received signal {signum}, stopping children...")
        _terminate_process(fastapi_proc)
        _terminate_process(monitor_proc)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    exit_code = 0
    while True:
        fcode = fastapi_proc.poll()
        mcode = monitor_proc.poll()
        if fcode is None and mcode is None:
            time.sleep(0.5)
            continue

        if not stopping:
            logger.error(f"Child exited (fastapi={fcode}, monitor={mcode}); stopping the other one...")
            _terminate_process(fastapi_proc)
            _terminate_process(monitor_proc)

        if fcode is not None and fcode != 0:
            exit_code = int(fcode)
        elif mcode is not None and mcode != 0:
            exit_code = int(mcode)
        break

    try:
        fastapi_log_fp.close()
    except Exception:
        pass
    try:
        monitor_log_fp.close()
    except Exception:
        pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
