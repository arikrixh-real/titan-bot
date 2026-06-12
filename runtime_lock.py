import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


IST = timezone(timedelta(hours=5, minutes=30))
LOCK_DIR = Path("data") / "runtime" / "locks"


def _lock_path(name):
    return LOCK_DIR / f"{name}.lock"


def _now_ist():
    return datetime.now(IST)


def _lock_payload(name):
    return {
        "name": name,
        "acquired_at_ist": _now_ist().isoformat(),
        "pid": os.getpid(),
    }


def _read_lock(path):
    with path.open("r", encoding="utf-8") as lock_file:
        return json.load(lock_file)


def pid_exists(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_info(name, stale_after_seconds=300):
    path = _lock_path(name)
    if not path.exists():
        return {
            "name": name,
            "path": str(path).replace("\\", "/"),
            "locked": False,
            "stale": False,
            "reason": "lock_missing",
        }
    try:
        payload = _read_lock(path)
        acquired_at = datetime.fromisoformat(payload["acquired_at_ist"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {
            "name": name,
            "path": str(path).replace("\\", "/"),
            "locked": True,
            "stale": True,
            "reason": "lock_unreadable",
        }

    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=IST)

    age_seconds = (_now_ist() - acquired_at.astimezone(IST)).total_seconds()
    pid = payload.get("pid")
    pid_alive = pid_exists(pid)
    stale_by_age = age_seconds >= stale_after_seconds
    stale = stale_by_age or not pid_alive
    if not pid_alive:
        reason = "worker_pid_not_found"
    elif stale_by_age:
        reason = "lock_age_exceeded"
    else:
        reason = "lock_active"
    return {
        "name": name,
        "path": str(path).replace("\\", "/"),
        "locked": True,
        "stale": stale,
        "reason": reason,
        "pid": pid,
        "pid_alive": pid_alive,
        "age_seconds": max(0.0, age_seconds),
        "stale_after_seconds": stale_after_seconds,
        "acquired_at_ist": payload.get("acquired_at_ist"),
    }


def _is_stale(path, stale_after_seconds):
    try:
        payload = _read_lock(path)
        acquired_at = datetime.fromisoformat(payload["acquired_at_ist"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return True

    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=IST)

    age = _now_ist() - acquired_at.astimezone(IST)
    return age.total_seconds() >= stale_after_seconds or not pid_exists(payload.get("pid"))


def _write_lock(path, name):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    payload = _lock_payload(name)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=LOCK_DIR,
            delete=False,
            prefix=f".{name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)

        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def _current_process_owns_lock(path):
    try:
        payload = _read_lock(path)
        return int(payload.get("pid")) == os.getpid()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def acquire_lock(name, stale_after_seconds=300):
    path = _lock_path(name)
    LOCK_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with path.open("x", encoding="utf-8") as lock_file:
            json.dump(_lock_payload(name), lock_file, indent=2)
            lock_file.write("\n")
        return True
    except FileExistsError:
        if not _is_stale(path, stale_after_seconds):
            return False

        _write_lock(path, name)
        return True


def refresh_lock(name):
    path = _lock_path(name)
    last_error = None
    for _ in range(3):
        try:
            _write_lock(path, name)
            return True
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    if _current_process_owns_lock(path):
        return False
    raise last_error


def release_lock(name):
    path = _lock_path(name)

    try:
        path.unlink()
    except FileNotFoundError:
        pass


def is_locked(name, stale_after_seconds=300):
    path = _lock_path(name)

    if not path.exists():
        return False

    return not _is_stale(path, stale_after_seconds)


if __name__ == "__main__":
    test_lock = "supervisor_preview"
    acquired = acquire_lock(test_lock)
    print(f"acquire_lock({test_lock!r}) -> {acquired}")
    print(f"is_locked({test_lock!r}) -> {is_locked(test_lock)}")
    release_lock(test_lock)
    print(f"released {test_lock!r}")
