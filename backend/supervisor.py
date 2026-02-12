import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time


logger = logging.getLogger(__name__)


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

    log_mode = str(os.getenv("SUPERVISOR_LOG_MODE", "file")).strip().lower()
    stdio_mode = log_mode in {"stdout", "stdio", "console"}
    mixed_mode = log_mode in {"mixed", "api", "api_only", "fastapi_only"}

    fastapi_to_stdio = stdio_mode or mixed_mode
    monitor_to_stdio = stdio_mode
    config_push_to_stdio = stdio_mode

    stdio_prefix = str(os.getenv("SUPERVISOR_STDIO_PREFIX", "1")).strip().lower() not in {"0", "false", "no", "off"}

    fastapi_log_fp = None
    monitor_log_fp = None
    config_push_log_fp = None
    fastapi_log_path = ""
    monitor_log_path = ""
    config_push_log_path = ""

    if not (fastapi_to_stdio and monitor_to_stdio and config_push_to_stdio):
        log_dir = os.getenv("SUPERVISOR_LOG_DIR", "").strip() or os.getenv("LOG_DIR", "").strip() or "/tmp/bise-dev-logs"
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            log_dir = "/tmp"
            os.makedirs(log_dir, exist_ok=True)

        if not fastapi_to_stdio:
            fastapi_log_path = os.path.join(log_dir, "fastapi.log")
        if not monitor_to_stdio:
            monitor_log_path = os.path.join(log_dir, "monitor.log")
        if not config_push_to_stdio:
            config_push_log_path = os.path.join(log_dir, "config_push.log")

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
    config_push_cmd = [python_exe, os.path.join(project_root, "processes", "config_push_worker.py")]

    logger.info(f"Starting FastAPI: {' '.join(fastapi_cmd)}")
    logger.info(f"Starting Monitor daemon: {' '.join(monitor_cmd)}")
    logger.info(f"Starting ConfigPush worker: {' '.join(config_push_cmd)}")
    if fastapi_to_stdio and monitor_to_stdio and config_push_to_stdio:
        logger.info("Child logs: stdout/stderr")
    else:
        if fastapi_log_path:
            logger.info(f"FastAPI logs: {fastapi_log_path}")
            fastapi_log_fp = open(fastapi_log_path, "a", encoding="utf-8", buffering=1)
        if monitor_log_path:
            logger.info(f"Monitor logs: {monitor_log_path}")
            monitor_log_fp = open(monitor_log_path, "a", encoding="utf-8", buffering=1)
        if config_push_log_path:
            logger.info(f"ConfigPush logs: {config_push_log_path}")
            config_push_log_fp = open(config_push_log_path, "a", encoding="utf-8", buffering=1)

    try:
        fastapi_stdout = subprocess.PIPE if (fastapi_to_stdio and stdio_prefix) else (None if fastapi_to_stdio else fastapi_log_fp)
        fastapi_stderr = subprocess.PIPE if (fastapi_to_stdio and stdio_prefix) else (None if fastapi_to_stdio else fastapi_log_fp)
        monitor_stdout = subprocess.PIPE if (monitor_to_stdio and stdio_prefix) else (None if monitor_to_stdio else monitor_log_fp)
        monitor_stderr = subprocess.PIPE if (monitor_to_stdio and stdio_prefix) else (None if monitor_to_stdio else monitor_log_fp)
        config_push_stdout = subprocess.PIPE if (config_push_to_stdio and stdio_prefix) else (None if config_push_to_stdio else config_push_log_fp)
        config_push_stderr = subprocess.PIPE if (config_push_to_stdio and stdio_prefix) else (None if config_push_to_stdio else config_push_log_fp)

        base_env = os.environ.copy()

        fastapi_env = base_env.copy()
        fastapi_env["SERVICE_NAME"] = "fastapi"
        fastapi_env["LOG_BASENAME"] = "fastapi"

        monitor_env = base_env.copy()
        monitor_env["SERVICE_NAME"] = "monitor"
        monitor_env["LOG_BASENAME"] = "monitor"

        config_push_env = base_env.copy()
        config_push_env["SERVICE_NAME"] = "config_push"
        config_push_env["LOG_BASENAME"] = "config_push"

        io_lock = threading.Lock()

        def _forward_pipe(prefix: str, stream_name: str, pipe):
            try:
                while True:
                    line = pipe.readline()
                    if not line:
                        break
                    with io_lock:
                        sys.stdout.write(f"[{prefix} {stream_name}] {line}")
                        sys.stdout.flush()
            except Exception:
                return
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        fastapi_proc = subprocess.Popen(
            fastapi_cmd,
            cwd=project_root,
            env=fastapi_env,
            stdout=fastapi_stdout,
            stderr=fastapi_stderr,
            text=fastapi_stdout == subprocess.PIPE or fastapi_stderr == subprocess.PIPE,
            bufsize=1,
        )

        monitor_proc = subprocess.Popen(
            monitor_cmd,
            cwd=project_root,
            env=monitor_env,
            stdout=monitor_stdout,
            stderr=monitor_stderr,
            text=monitor_stdout == subprocess.PIPE or monitor_stderr == subprocess.PIPE,
            bufsize=1,
        )

        config_push_proc = subprocess.Popen(
            config_push_cmd,
            cwd=project_root,
            env=config_push_env,
            stdout=config_push_stdout,
            stderr=config_push_stderr,
            text=config_push_stdout == subprocess.PIPE or config_push_stderr == subprocess.PIPE,
            bufsize=1,
        )

        threads: list[threading.Thread] = []
        if stdio_prefix:
            if fastapi_proc.stdout is not None:
                threads.append(threading.Thread(target=_forward_pipe, args=("fastapi", "stdout", fastapi_proc.stdout), daemon=True))
            if fastapi_proc.stderr is not None:
                threads.append(threading.Thread(target=_forward_pipe, args=("fastapi", "stderr", fastapi_proc.stderr), daemon=True))
            if monitor_proc.stdout is not None:
                threads.append(threading.Thread(target=_forward_pipe, args=("monitor", "stdout", monitor_proc.stdout), daemon=True))
            if monitor_proc.stderr is not None:
                threads.append(threading.Thread(target=_forward_pipe, args=("monitor", "stderr", monitor_proc.stderr), daemon=True))
            if config_push_proc.stdout is not None:
                threads.append(threading.Thread(target=_forward_pipe, args=("config_push", "stdout", config_push_proc.stdout), daemon=True))
            if config_push_proc.stderr is not None:
                threads.append(threading.Thread(target=_forward_pipe, args=("config_push", "stderr", config_push_proc.stderr), daemon=True))

        for t in threads:
            t.start()
    except Exception:
        for fp in (fastapi_log_fp, monitor_log_fp, config_push_log_fp):
            if fp is None:
                continue
            try:
                fp.close()
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
        _terminate_process(config_push_proc)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    exit_code = 0
    while True:
        fcode = fastapi_proc.poll()
        mcode = monitor_proc.poll()
        ccode = config_push_proc.poll()
        if fcode is None and mcode is None and ccode is None:
            time.sleep(0.5)
            continue

        if not stopping:
            logger.error(f"Child exited (fastapi={fcode}, monitor={mcode}, config_push={ccode}); stopping the other one...")
            _terminate_process(fastapi_proc)
            _terminate_process(monitor_proc)
            _terminate_process(config_push_proc)

        if fcode is not None and fcode != 0:
            exit_code = int(fcode)
        elif mcode is not None and mcode != 0:
            exit_code = int(mcode)
        elif ccode is not None and ccode != 0:
            exit_code = int(ccode)
        break

    for fp in (fastapi_log_fp, monitor_log_fp, config_push_log_fp):
        if fp is None:
            continue
        try:
            fp.close()
        except Exception:
            pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
