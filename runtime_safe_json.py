import json
import os
import time
import uuid
from pathlib import Path


def cleanup_stale_temp_files(path, max_age_seconds=3600):
    path = Path(path)
    parent = path.parent
    if not parent.exists():
        return
    now = time.time()
    for temp_path in parent.glob(f".{path.name}.*.tmp"):
        try:
            if now - temp_path.stat().st_mtime >= max_age_seconds:
                temp_path.unlink()
        except OSError:
            pass


def safe_atomic_write_json(path, payload, *, retries=5, retry_delay_seconds=0.05, ensure_ascii=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_temp_files(path)
    last_error = None

    for attempt in range(retries):
        temp_path = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8") as temp_file:
                json.dump(payload, temp_file, indent=2, sort_keys=True, default=str, ensure_ascii=ensure_ascii)
                temp_file.write("\n")
            os.replace(temp_path, path)
            return True
        except PermissionError as exc:
            last_error = exc
            time.sleep(retry_delay_seconds * (attempt + 1))
        except OSError as exc:
            last_error = exc
            time.sleep(retry_delay_seconds * (attempt + 1))
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

    try:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str, ensure_ascii=ensure_ascii) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError as exc:
        last_error = exc

    if last_error is not None:
        raise last_error
    return False
