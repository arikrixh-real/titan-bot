import json
import os
import tempfile
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


def _is_stale(path, stale_after_seconds):
    try:
        payload = _read_lock(path)
        acquired_at = datetime.fromisoformat(payload["acquired_at_ist"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return True

    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=IST)

    age = _now_ist() - acquired_at.astimezone(IST)
    return age.total_seconds() >= stale_after_seconds


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
