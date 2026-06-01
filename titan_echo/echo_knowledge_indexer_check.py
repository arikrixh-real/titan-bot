"""Validate the TITAN ECHO read-only knowledge indexer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEXER_PATH = REPO_ROOT / "titan_echo" / "echo_knowledge_indexer.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "titan_file_index.json"


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_indexer() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(INDEXER_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def load_index() -> tuple[dict[str, object] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing output file: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"

    if not isinstance(data, dict):
        return None, "Index root must be a JSON object."
    return data, None


def validate_index(data: dict[str, object]) -> list[str]:
    errors: list[str] = []
    files = data.get("files")

    if not isinstance(files, list):
        return ["Index field 'files' must be a list."]

    if len(files) <= 0:
        errors.append("Index must contain at least one file.")

    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"File entry {index} must be an object.")
            continue
        if "criticality" not in item:
            errors.append(f"File entry {index} is missing criticality.")

    return errors


def main() -> int:
    errors: list[str] = []

    if not INDEXER_PATH.is_file():
        errors.append(f"Missing indexer: {relative(INDEXER_PATH)}")
    else:
        returncode, stdout, stderr = run_indexer()
        if returncode != 0:
            errors.append(f"Indexer failed with exit code {returncode}.")
        if stderr:
            errors.append("Indexer wrote to stderr.")
        if stdout:
            allowed_prefixes = (
                "TITAN ECHO knowledge indexer:",
                "Indexed files:",
                "Criticality counts:",
                "Output:",
            )
            for line in stdout.splitlines():
                if not line.startswith(allowed_prefixes):
                    errors.append("Indexer printed unexpected output.")
                    break

    data, load_error = load_index()
    if load_error:
        errors.append(load_error)
    elif data is not None:
        errors.extend(validate_index(data))

    if errors:
        print("TITAN ECHO knowledge indexer check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    files = data.get("files", []) if data else []
    print("TITAN ECHO knowledge indexer check: PASSED")
    print(f"Indexed files: {len(files)}")
    print(f"Output present: {relative(OUTPUT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
