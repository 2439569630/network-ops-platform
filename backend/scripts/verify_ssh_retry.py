import os
import sys
import time

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.drivers.ssh_retry import classify_ssh_failure


def main() -> int:
    samples = [
        Exception("Error reading SSH protocol banner"),
        Exception("SSHException: Error reading SSH protocol banner"),
        EOFError(),
        Exception("Authentication failed."),
        Exception("Connection refused"),
        TimeoutError("timed out"),
        Exception("No existing session"),
        Exception(""),
    ]

    for e in samples:
        decision = classify_ssh_failure(e, default_base_delay_seconds=2.0, default_max_delay_seconds=30.0)
        print(f"{type(e).__name__}: {decision.category} | {decision.reason}")
        delays = [round(decision.next_delay_seconds(i), 2) for i in range(1, 6)]
        print("  delays:", delays)
        time.sleep(0.01)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
