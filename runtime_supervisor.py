from runtime_status import build_runtime_status, write_runtime_status
from runtime_lock import acquire_lock, release_lock


def print_runtime_report(status):
    print("TITAN Runtime Supervisor Preview")
    print(f"timestamp_ist: {status['timestamp_ist']}")
    print(f"mode: {status['mode']}")
    print("live_allowed_engines:")
    for engine in status["live_allowed_engines"]:
        print(f"  - {engine}")
    print("research_allowed_engines:")
    for engine in status["research_allowed_engines"]:
        print(f"  - {engine}")
    print("blocked_engines:")
    for engine in status["blocked_engines"]:
        print(f"  - {engine}")
    print(f"reason: {status['reason']}")


def preview_runtime_supervision():
    status = build_runtime_status()
    write_runtime_status()
    print_runtime_report(status)
    return status


if __name__ == "__main__":
    lock_name = "supervisor_runtime"

    if not acquire_lock(lock_name):
        print("Supervisor already running. Skipping duplicate run.")
    else:
        try:
            preview_runtime_supervision()
        finally:
            release_lock(lock_name)
