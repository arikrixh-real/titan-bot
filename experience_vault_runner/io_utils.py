import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True, ensure_ascii=True)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as source_file:
            payload = json.load(source_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default

