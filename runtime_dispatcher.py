import json
import time
from pathlib import Path

from runtime_engine_registry import get_registered_handler
from runtime_tick import get_due_tasks
from runtime_lock import acquire_lock, release_lock
from runtime_timeout import run_with_timeout


DISPATCH_LOG_PATH = Path("data/runtime/dispatch_log.jsonl")
DISPATCH_LOG_PREVIOUS_PATH = Path("data/runtime/dispatch_log_previous.jsonl")
SCANNER_DEBUG_LOG_PATH = Path("data/runtime/scanner_dispatch_debug.jsonl")
MAX_DISPATCH_LOG_BYTES = 5 * 1024 * 1024
CYCLE_DEADLINE_SECONDS = 285
DEFAULT_TASK_TIMEOUT_SECONDS = 60
TASK_TIMEOUT_SECONDS = {
    "ohlc_refresh": 120,
    "setup_engine": 240,
    "master_brain": 240,
    "scanner": 120,
    "mode_scanner_status": 120,
    "news_pulse": 45,
    "light_news_pulse": 45,
    "outcome_tracker": 45,
    "evolution_engine": 60,
}
SCANNER_DISPATCH_TASKS = {"scanner", "mode_scanner_status"}


def rotate_dispatch_log_if_needed():
    if DISPATCH_LOG_PATH.exists() and DISPATCH_LOG_PATH.stat().st_size > MAX_DISPATCH_LOG_BYTES:
        DISPATCH_LOG_PATH.replace(DISPATCH_LOG_PREVIOUS_PATH)


def append_dispatch_log(timestamp_ist, mode, dispatch_preview):
    try:
        DISPATCH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        rotate_dispatch_log_if_needed()
        with DISPATCH_LOG_PATH.open("a", encoding="utf-8") as log_file:
            for item in dispatch_preview:
                payload = {
                    "timestamp_ist": timestamp_ist,
                    "mode": mode,
                    "task": item["task"],
                    "action": item["action"],
                    "executed": item["executed"],
                }
                for key in ("legacy_classic_dispatcher_blocked", "dispatcher_scanner_handler"):
                    if key in item:
                        payload[key] = item[key]
                log_file.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def append_scanner_debug_log(timestamp_ist, mode, event, reason=None):
    payload = {
        "timestamp_ist": timestamp_ist,
        "mode": mode,
        "task": "scanner",
        "event": event,
    }
    if reason:
        payload["reason"] = reason

    print(json.dumps(payload, separators=(",", ":")), flush=True)

    try:
        SCANNER_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SCANNER_DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def scanner_dispatch_guard(result):
    guard = {
        "legacy_classic_dispatcher_blocked": None,
        "dispatcher_scanner_handler": "UNKNOWN",
    }
    if isinstance(result, dict):
        payload = result.get("result") if isinstance(result.get("result"), dict) else result
        if isinstance(payload, dict):
            guard["legacy_classic_dispatcher_blocked"] = payload.get("legacy_classic_dispatcher_blocked")
            guard["dispatcher_scanner_handler"] = payload.get("dispatcher_scanner_handler") or "UNKNOWN"
    return guard


def _task_timeout_seconds(task):
    return TASK_TIMEOUT_SECONDS.get(task, DEFAULT_TASK_TIMEOUT_SECONDS)


def _cycle_budget_remaining(started_at):
    return CYCLE_DEADLINE_SECONDS - (time.monotonic() - started_at)


def preview_dispatch(value=None):
    tick = get_due_tasks(value)
    due_tasks = tick["due_tasks"]
    print(f"DUE_TASKS={json.dumps(due_tasks, separators=(',', ':'))}", flush=True)
    dispatch_preview = []
    cycle_started_at = time.monotonic()

    for task in due_tasks:
        if task == "scanner":
            append_scanner_debug_log(
                tick["timestamp_ist"],
                tick["mode"],
                "SCANNER_TASK_DUE",
            )

        if _cycle_budget_remaining(cycle_started_at) <= 0:
            dispatch_preview.append(
                {
                    "task": task,
                    "action": "SKIPPED_CYCLE_DEADLINE",
                    "executed": False,
                }
            )
            if task == "scanner":
                append_scanner_debug_log(
                    tick["timestamp_ist"],
                    tick["mode"],
                    "SCANNER_TASK_SKIPPED",
                    "SKIPPED_CYCLE_DEADLINE",
                )
            continue

        handler = get_registered_handler(task)

        guard = {}
        if handler:
            lock_name = f"task_{task}"
            lock_acquired = acquire_lock(lock_name)

            if not lock_acquired:
                action = "SKIPPED_LOCKED"
                executed = False
            else:
                try:
                    timeout_seconds = min(
                        _task_timeout_seconds(task),
                        max(1, int(_cycle_budget_remaining(cycle_started_at))),
                    )
                    try:
                        result = run_with_timeout(handler, timeout_seconds)
                    except Exception:
                        result = {"status": "error"}

                    if result.get("status") == "ok":
                        action = "EXECUTED"
                        executed = True
                    elif result.get("status") == "timeout":
                        action = "TIMEOUT"
                        executed = False
                    else:
                        action = "ERROR"
                        executed = False
                    if task in SCANNER_DISPATCH_TASKS:
                        guard = scanner_dispatch_guard(result)
                finally:
                    release_lock(lock_name)
        else:
            action = "WOULD_DISPATCH"
            executed = False

        if task == "scanner":
            if executed:
                append_scanner_debug_log(
                    tick["timestamp_ist"],
                    tick["mode"],
                    "SCANNER_TASK_EXECUTED",
                )
            else:
                append_scanner_debug_log(
                    tick["timestamp_ist"],
                    tick["mode"],
                    "SCANNER_TASK_SKIPPED",
                    action,
                )

        item = {
            "task": task,
            "action": action,
            "executed": executed,
        }
        item.update(guard)
        dispatch_preview.append(item)

    append_dispatch_log(tick["timestamp_ist"], tick["mode"], dispatch_preview)

    return {
        "timestamp_ist": tick["timestamp_ist"],
        "mode": tick["mode"],
        "due_tasks": due_tasks,
        "dispatch_preview": dispatch_preview,
    }


if __name__ == "__main__":
    print(preview_dispatch())
