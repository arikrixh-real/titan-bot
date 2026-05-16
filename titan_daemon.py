import time

from runtime_lock import acquire_lock, release_lock
from runtime_dispatcher import preview_dispatch
from runtime_health import write_daemon_health
from runtime_error_log import log_runtime_error


LOCK_NAME = "titan_daemon"
PRINT_INTERVAL_SECONDS = 30
TICK_SECONDS = 1


def main():
    if not acquire_lock(LOCK_NAME):
        print("TITAN daemon already running. Exiting.")
        return

    last_printed_at = 0.0
    ticks_completed = 0
    last_dispatch_count = 0
    latest_mode = "UNKNOWN"

    try:
        while True:
            try:
                dispatch_result = preview_dispatch()
                ticks_completed += 1
                latest_mode = dispatch_result["mode"]
                last_dispatch_count = len(dispatch_result["dispatch_preview"])

                write_daemon_health(
                    mode=latest_mode,
                    ticks_completed=ticks_completed,
                    dispatch_count=last_dispatch_count,
                    status="RUNNING",
                )

                now = time.monotonic()
                if now - last_printed_at >= PRINT_INTERVAL_SECONDS:
                    print(
                        "TITAN daemon running "
                        f"mode={latest_mode} "
                        f"ticks_completed={ticks_completed} "
                        f"last_dispatch_count={last_dispatch_count}"
                    )
                    last_printed_at = now
            except Exception as exc:
                log_runtime_error(
                    source="titan_daemon_tick",
                    error=exc,
                    mode=latest_mode,
                )

            time.sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        print("TITAN daemon stopped.")
        write_daemon_health(
            mode=latest_mode,
            ticks_completed=ticks_completed,
            dispatch_count=last_dispatch_count,
            status="STOPPED",
        )
    finally:
        release_lock(LOCK_NAME)


if __name__ == "__main__":
    main()
