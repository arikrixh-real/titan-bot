import json
from pathlib import Path

from runtime_engine_registry import get_registered_handler
from runtime_tick import get_due_tasks
from runtime_lock import acquire_lock, release_lock


DISPATCH_LOG_PATH = Path("data/runtime/dispatch_log.jsonl")
DISPATCH_LOG_PREVIOUS_PATH = Path("data/runtime/dispatch_log_previous.jsonl")
MAX_DISPATCH_LOG_BYTES = 5 * 1024 * 1024


def rotate_dispatch_log_if_needed():
    if DISPATCH_LOG_PATH.exists() and DISPATCH_LOG_PATH.stat().st_size > MAX_DISPATCH_LOG_BYTES:
        DISPATCH_LOG_PATH.replace(DISPATCH_LOG_PREVIOUS_PATH)


def append_dispatch_log(timestamp_ist, mode, dispatch_preview):
    try:
        DISPATCH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        rotate_dispatch_log_if_needed()
        with DISPATCH_LOG_PATH.open("a", encoding="utf-8") as log_file:
            for item in dispatch_preview:
                log_file.write(
                    json.dumps(
                        {
                            "timestamp_ist": timestamp_ist,
                            "mode": mode,
                            "task": item["task"],
                            "action": item["action"],
                            "executed": item["executed"],
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
    except OSError:
        pass


def preview_dispatch(value=None):
    tick = get_due_tasks(value)
    due_tasks = tick["due_tasks"]
    dispatch_preview = []

    for task in due_tasks:
        handler = get_registered_handler(task)

        if handler:
            lock_name = f"task_{task}"
            lock_acquired = acquire_lock(lock_name)

            if not lock_acquired:
                action = "SKIPPED_LOCKED"
                executed = False
            else:
                try:
                    handler()
                    action = "EXECUTED"
                    executed = True
                finally:
                    release_lock(lock_name)
        else:
            action = "WOULD_DISPATCH"
            executed = False

        dispatch_preview.append(
            {
                "task": task,
                "action": action,
                "executed": executed,
            }
        )

    append_dispatch_log(tick["timestamp_ist"], tick["mode"], dispatch_preview)

    return {
        "timestamp_ist": tick["timestamp_ist"],
        "mode": tick["mode"],
        "due_tasks": due_tasks,
        "dispatch_preview": dispatch_preview,
    }


if __name__ == "__main__":
    print(preview_dispatch())
