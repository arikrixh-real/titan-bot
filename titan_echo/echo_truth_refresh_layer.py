"""Read-only TITAN truth refresh diagnostics.

This layer refreshes status artifacts from local files only. It does not call a
broker, place trades, run scanners, change strategy, or restart services.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo import echo_trade_diagnostics

RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
JOURNAL_DIR = REPO_ROOT / "data" / "journals"
AUTHORITATIVE_RUNTIME_TRUTH_PATH = RUNTIME_DIR / "authoritative_runtime_truth.json"
COMPONENT_FRESHNESS_SUMMARY_PATH = RUNTIME_DIR / "component_freshness_summary.json"
GIT_CLEANLINESS_PATH = RUNTIME_DIR / "git_cleanliness.json"
RUNTIME_ERROR_SUMMARY_PATH = RUNTIME_DIR / "runtime_error_summary.json"
DAEMON_ERRORS_LOG_PATH = RUNTIME_DIR / "daemon_errors.jsonl"
ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"
TRADE_OUTCOMES_CSV = JOURNAL_DIR / "trade_outcomes.csv"

IST = timezone(timedelta(hours=5, minutes=30))
STALE_AFTER_MINUTES = 30

COMPONENT_ARTIFACTS = {
    "runtime_status": RUNTIME_DIR / "runtime_status.json",
    "titan_runtime_status": RUNTIME_DIR / "titan_runtime_status.json",
    "scanner_status": RUNTIME_DIR / "scanner_status.json",
    "master_brain_status": RUNTIME_DIR / "master_brain_status.json",
    "outcome_tracker_status": RUNTIME_DIR / "outcome_tracker_status.json",
    "trade_journal_diagnostics": RUNTIME_DIR / "trade_journal_diagnostics.json",
    "outcome_tracker_diagnostics": RUNTIME_DIR / "outcome_tracker_diagnostics.json",
}


def refresh_truth_layer(*, now: datetime | None = None) -> dict[str, Any]:
    now = _as_aware(now or datetime.now(IST))
    trade_diagnostics = echo_trade_diagnostics.build_all_trade_diagnostics()
    component_freshness = build_component_freshness_summary(now=now)
    git_cleanliness = build_git_cleanliness()
    runtime_errors = build_runtime_error_summary(now=now)
    csv_truth = build_trade_csv_truth()

    payload = {
        "schema": "titan.echo.authoritative_runtime_truth.v1",
        "status": _overall_status(component_freshness, runtime_errors),
        "generated_at_ist": now.astimezone(IST).isoformat(),
        "component_freshness_status": component_freshness["overall_status"],
        "git_cleanliness_status": git_cleanliness["status"],
        "runtime_error_status": runtime_errors["status"],
        "active_trade_count": csv_truth["active_trade_count"],
        "trade_outcome_count": csv_truth["trade_outcome_count"],
        "csv_truth": csv_truth,
        "artifacts": {
            "component_freshness_summary": _relative(COMPONENT_FRESHNESS_SUMMARY_PATH),
            "git_cleanliness": _relative(GIT_CLEANLINESS_PATH),
            "runtime_error_summary": _relative(RUNTIME_ERROR_SUMMARY_PATH),
            "trade_journal_diagnostics": _relative(echo_trade_diagnostics.TRADE_JOURNAL_DIAGNOSTICS_PATH),
            "outcome_tracker_diagnostics": _relative(echo_trade_diagnostics.OUTCOME_TRACKER_DIAGNOSTICS_PATH),
        },
        "trade_diagnostics_status": {
            name: payload.get("status")
            for name, payload in trade_diagnostics.items()
            if isinstance(payload, dict)
        },
        "safety": _safety(),
    }
    _write_runtime_json(AUTHORITATIVE_RUNTIME_TRUTH_PATH, payload)
    return payload


def build_component_freshness_summary(
    *,
    now: datetime | None = None,
    artifacts: dict[str, Path] | None = None,
    stale_after_minutes: int = STALE_AFTER_MINUTES,
) -> dict[str, Any]:
    now = _as_aware(now or datetime.now(IST))
    artifacts = artifacts or COMPONENT_ARTIFACTS
    components = []
    for name, path in artifacts.items():
        components.append(_component_freshness(name, path, now=now, stale_after_minutes=stale_after_minutes))

    statuses = {item["freshness_status"] for item in components}
    overall = "UNKNOWN" if "UNKNOWN" in statuses else "STALE" if "STALE" in statuses else "FRESH"
    payload = {
        "schema": "titan.echo.component_freshness_summary.v1",
        "overall_status": overall,
        "generated_at_ist": now.astimezone(IST).isoformat(),
        "stale_after_minutes": stale_after_minutes,
        "components": components,
        "safety": _safety(),
    }
    _write_runtime_json(COMPONENT_FRESHNESS_SUMMARY_PATH, payload)
    return payload


def build_git_cleanliness(
    *,
    command_runner: Callable[..., Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    runner = command_runner or subprocess.run
    try:
        result = runner(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        lines = [line for line in str(result.stdout or "").splitlines() if line.strip()]
        status = "CLEAN" if result.returncode == 0 and not lines else "DIRTY" if result.returncode == 0 else "UNKNOWN"
        payload = {
            "schema": "titan.echo.git_cleanliness.v1",
            "status": status,
            "return_code": int(result.returncode),
            "dirty_file_count": len(lines),
            "dirty_files_sample": lines[:50],
            "stderr_tail": str(result.stderr or "")[-2000:],
            "safety": _safety(),
        }
    except Exception as exc:
        payload = {
            "schema": "titan.echo.git_cleanliness.v1",
            "status": "UNKNOWN",
            "error": type(exc).__name__,
            "detail": str(exc),
            "safety": _safety(),
        }
    _write_runtime_json(GIT_CLEANLINESS_PATH, payload)
    return payload


def build_runtime_error_summary(
    *,
    now: datetime | None = None,
    log_path: Path = DAEMON_ERRORS_LOG_PATH,
    lookback_hours: int = 24,
) -> dict[str, Any]:
    now = _as_aware(now or datetime.now(IST))
    if not log_path.exists():
        payload = {
            "schema": "titan.echo.runtime_error_summary.v1",
            "status": "UNKNOWN",
            "reason": "MISSING_ERROR_LOG",
            "log_path": _relative(log_path),
            "error_count": None,
            "recent_error_count": None,
            "latest_error": None,
            "safety": _safety(),
        }
        _write_runtime_json(RUNTIME_ERROR_SUMMARY_PATH, payload)
        return payload

    records = _read_jsonl(log_path)
    cutoff = now - timedelta(hours=lookback_hours)
    recent = [item for item in records if (_parse_time(_first_timestamp(item)) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]
    latest = max(records, key=lambda item: _parse_time(_first_timestamp(item)) or datetime.min.replace(tzinfo=timezone.utc), default=None)
    payload = {
        "schema": "titan.echo.runtime_error_summary.v1",
        "status": "ERRORS_PRESENT" if recent else "NO_RECENT_ERRORS",
        "reason": "ERROR_LOG_PARSED",
        "log_path": _relative(log_path),
        "lookback_hours": lookback_hours,
        "error_count": len(records),
        "recent_error_count": len(recent),
        "latest_error": latest,
        "safety": _safety(),
    }
    _write_runtime_json(RUNTIME_ERROR_SUMMARY_PATH, payload)
    return payload


def build_trade_csv_truth(
    *,
    active_trades_path: Path = ACTIVE_TRADES_CSV,
    outcomes_path: Path = TRADE_OUTCOMES_CSV,
) -> dict[str, Any]:
    active_rows = _read_csv(active_trades_path)
    outcome_rows = _read_csv(outcomes_path)
    active_ids = [_trade_id(row) for row in active_rows if _trade_id(row)]
    outcome_ids = [_trade_id(row) for row in outcome_rows if _trade_id(row)]
    return {
        "schema": "titan.echo.trade_csv_truth.v1",
        "active_trade_count": len(active_rows),
        "trade_outcome_count": len(outcome_rows),
        "active_trade_ids_sample": active_ids[:50],
        "outcome_trade_ids_sample": outcome_ids[:50],
        "source_files": {
            "active_trades": {"path": _relative(active_trades_path), "exists": active_trades_path.exists()},
            "trade_outcomes": {"path": _relative(outcomes_path), "exists": outcomes_path.exists()},
        },
        "safety": _safety(),
    }


def _component_freshness(name: str, path: Path, *, now: datetime, stale_after_minutes: int) -> dict[str, Any]:
    payload = _read_json(path)
    timestamp = _first_timestamp(payload)
    parsed = _parse_time(timestamp)
    source = "payload_timestamp" if parsed else ""
    if not parsed and path.exists():
        parsed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        source = "file_mtime"
    if not parsed:
        return {
            "component": name,
            "path": _relative(path),
            "exists": path.exists(),
            "freshness_status": "UNKNOWN",
            "reason": "MISSING_OR_UNREADABLE_ARTIFACT",
            "timestamp": "",
            "age_minutes": None,
        }

    age = max(0.0, (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60)
    status = "STALE" if age > stale_after_minutes else "FRESH"
    return {
        "component": name,
        "path": _relative(path),
        "exists": path.exists(),
        "freshness_status": status,
        "reason": "AGE_EXCEEDS_THRESHOLD" if status == "STALE" else "WITHIN_THRESHOLD",
        "timestamp": parsed.isoformat(),
        "timestamp_source": source,
        "age_minutes": round(age, 2),
    }


def _overall_status(component_freshness: dict[str, Any], runtime_errors: dict[str, Any]) -> str:
    if component_freshness.get("overall_status") == "UNKNOWN" or runtime_errors.get("status") == "UNKNOWN":
        return "UNKNOWN"
    if component_freshness.get("overall_status") == "STALE":
        return "STALE"
    if runtime_errors.get("status") == "ERRORS_PRESENT":
        return "DEGRADED"
    return "FRESH"


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _write_runtime_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_runtime = RUNTIME_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_runtime not in (resolved_path, *resolved_path.parents):
        raise ValueError("truth refresh writes only under data/runtime")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _first_timestamp(payload: dict[str, Any]) -> str:
    for key in (
        "timestamp_ist",
        "generated_at_ist",
        "updated_at_ist",
        "scan_finished_at_ist",
        "last_completed_at_ist",
        "timestamp",
        "generated_at",
        "updated_at",
    ):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed


def _as_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=IST) if value.tzinfo is None else value


def _trade_id(row: dict[str, Any]) -> str:
    return str(row.get("trade_id") or row.get("paper_trade_id") or "").strip()


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _safety() -> dict[str, bool]:
    return {
        "diagnostics_only": True,
        "broker_calls": False,
        "live_trades": False,
        "scanner_strategy_changes": False,
        "service_restart": False,
        "execution_mutation": False,
    }


if __name__ == "__main__":
    result = refresh_truth_layer()
    print(json.dumps({"status": result["status"], "active_trade_count": result["active_trade_count"]}, indent=2))
