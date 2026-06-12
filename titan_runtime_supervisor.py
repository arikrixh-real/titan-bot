import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime_safe_json import safe_atomic_write_json


IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
LOG_DIR = ROOT / "logs"
LOCK_PATH = RUNTIME_DIR / "titan_runtime_supervisor.lock"
STATUS_PATH = RUNTIME_DIR / "titan_runtime_supervisor_status.json"
LOG_PATH = LOG_DIR / "titan_runtime_supervisor.log"
TASK_TIMEOUT_SECONDS = 120
LOCK_STALE_SECONDS = 300


@dataclass
class Task:
    name: str
    script: str
    interval_seconds: int
    timeout_seconds: int = TASK_TIMEOUT_SECONDS
    enabled: bool = True
    next_run_monotonic: float = 0.0
    running: bool = False
    last_result: dict[str, Any] = field(default_factory=dict)


TASKS = [
    Task("runtime_continuous_core", "runtime_continuous_core.py", 30),
    Task("runtime_paper_engine", "runtime_paper_engine.py", 60),
    Task("runtime_dashboard_sync", "runtime_dashboard_sync.py", 60),
    Task("runtime_truth", "runtime_truth.py", 60),
    Task("runtime_snapshot_logger", "runtime_snapshot_logger.py", 120),
]


def now_ist() -> datetime:
    return datetime.now(IST)


def now_ist_text() -> str:
    return now_ist().isoformat()


def write_log(event: str, **fields: Any) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp_ist": now_ist_text(),
        "event": event,
        "supervisor_pid": os.getpid(),
        **fields,
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return str(pid) in result.stdout
            except Exception:
                return True
        return False


def lock_is_stale(payload: dict[str, Any]) -> bool:
    pid = int(payload.get("pid") or 0)
    if pid and process_exists(pid):
        return False

    status = read_json(STATUS_PATH)
    heartbeat = status.get("heartbeat_ist") or status.get("timestamp_ist")
    if isinstance(heartbeat, str):
        try:
            heartbeat_dt = datetime.fromisoformat(heartbeat)
            if heartbeat_dt.tzinfo is None:
                heartbeat_dt = heartbeat_dt.replace(tzinfo=IST)
            return (now_ist() - heartbeat_dt.astimezone(IST)).total_seconds() > LOCK_STALE_SECONDS
        except ValueError:
            pass
    return True


def acquire_lock() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        payload = {
            "pid": os.getpid(),
            "created_at_ist": now_ist_text(),
            "owner": "titan_runtime_supervisor",
        }
        try:
            fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
            os.close(fd)
            write_log("lock_acquired", lock_path=str(LOCK_PATH))
            return os.getpid()
        except FileExistsError:
            existing = read_json(LOCK_PATH)
            if lock_is_stale(existing):
                try:
                    LOCK_PATH.unlink()
                    write_log("stale_lock_removed", existing_lock=existing)
                    continue
                except OSError as exc:
                    write_log("lock_remove_failed", error=str(exc), existing_lock=existing)
            write_log("duplicate_supervisor_blocked", existing_lock=existing)
            raise SystemExit(f"TITAN runtime supervisor already running: {LOCK_PATH}")


def release_lock() -> None:
    payload = read_json(LOCK_PATH)
    if int(payload.get("pid") or 0) == os.getpid():
        try:
            LOCK_PATH.unlink()
            write_log("lock_released", lock_path=str(LOCK_PATH))
        except OSError as exc:
            write_log("lock_release_failed", error=str(exc))


def task_result(
    task: Task,
    status: str,
    started_monotonic: float,
    returncode: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    result = {
        "task": task.name,
        "script": task.script,
        "status": status,
        "returncode": returncode,
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        "last_run_ist": now_ist_text(),
        "interval_seconds": task.interval_seconds,
        "timeout_seconds": task.timeout_seconds,
    }
    if error:
        result["error"] = error
    return result


def write_status(tasks: list[Task], supervisor_status: str = "RUNNING") -> None:
    payload = {
        "timestamp_ist": now_ist_text(),
        "heartbeat_ist": now_ist_text(),
        "status": supervisor_status,
        "pid": os.getpid(),
        "lock_path": str(LOCK_PATH),
        "log_path": str(LOG_PATH),
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
        "task_timeout_seconds": TASK_TIMEOUT_SECONDS,
        "tasks": {task.name: task.last_result for task in tasks},
    }
    safe_atomic_write_json(STATUS_PATH, payload)


def run_task(task: Task) -> dict[str, Any]:
    script_path = ROOT / task.script
    started = time.monotonic()
    if not script_path.exists():
        return task_result(task, "SKIPPED", started, error="script_not_found")

    task.running = True
    write_log("task_started", task=task.name, script=task.script)
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=task.timeout_seconds,
        )
        error = None
        status = "OK" if completed.returncode == 0 else "ERROR"
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "").strip()[-2000:] or "nonzero_returncode"
        result = task_result(task, status, started, completed.returncode, error)
        write_log("task_finished", **result)
        return result
    except subprocess.TimeoutExpired as exc:
        result = task_result(task, "TIMEOUT", started, error=f"timeout_after_{task.timeout_seconds}s")
        write_log("task_timeout", task=task.name, timeout_seconds=task.timeout_seconds, output=(exc.stdout or "")[-1000:])
        return result
    except Exception as exc:
        result = task_result(task, "ERROR", started, error=f"{type(exc).__name__}: {exc}")
        write_log("task_exception", **result)
        return result
    finally:
        task.running = False


def stop_requested(signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt(f"signal_{signum}")


def supervise() -> None:
    acquire_lock()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop_requested)

    tasks = [task for task in TASKS if task.enabled]
    write_status(tasks, "STARTING")
    write_log("supervisor_started", tasks=[task.name for task in tasks])

    try:
        while True:
            now_monotonic = time.monotonic()
            ran_any = False
            for task in tasks:
                if task.running or now_monotonic < task.next_run_monotonic:
                    continue
                task.last_result = run_task(task)
                task.next_run_monotonic = time.monotonic() + task.interval_seconds
                write_status(tasks)
                ran_any = True

            if not ran_any:
                write_status(tasks)
                next_due = min((task.next_run_monotonic for task in tasks), default=time.monotonic() + 5)
                sleep_seconds = max(1.0, min(5.0, next_due - time.monotonic()))
                time.sleep(sleep_seconds)
    except KeyboardInterrupt as exc:
        write_log("supervisor_stopping", reason=str(exc))
        write_status(tasks, "STOPPING")
    finally:
        write_status(tasks, "STOPPED")
        release_lock()
        write_log("supervisor_stopped")


if __name__ == "__main__":
    supervise()
