"""
Refresh read-only infrastructure evidence for the TITAN dashboard.

This script measures local/system status and performs safe read-only checks.
It does not start workers, mutate trading state, place orders, or write to
Supabase.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
IST = timezone(timedelta(hours=5, minutes=30))

STORAGE_STATUS_PATH = RUNTIME_DIR / "storage_status.json"
NETWORK_STATUS_PATH = RUNTIME_DIR / "network_status.json"
SUPABASE_STATUS_PATH = RUNTIME_DIR / "supabase_status.json"
ECHO_ACTIVITY_PATH = RUNTIME_DIR / "echo_activity.json"
RELAY_STATUS_PATH = RUNTIME_DIR / "relay_status.json"

UPSTOX_HOST = "api.upstox.com"
UPSTOX_PORT = 443
ECHO_EVIDENCE_FILES = [
    ECHO_DIR / "codex_runner_request.json",
    ECHO_DIR / "approval_queue.json",
    ECHO_DIR / "auto_report.json",
    ECHO_DIR / "decision_trace_audit.json",
    ECHO_DIR / "recommendation_log.json",
    ECHO_DIR / "codex_runner_status.json",
    ECHO_DIR / "echo_api_status.json",
    ECHO_DIR / "relay_readiness.json",
]
RELAY_EVIDENCE_FILES = [
    ECHO_DIR / "relay_health.json",
    ECHO_DIR / "relay_runtime_status.json",
    ECHO_DIR / "relay_status.json",
    ECHO_DIR / "bridge_action_log.jsonl",
]


def now_ist() -> datetime:
    return datetime.now(IST)


def iso_now() -> str:
    return now_ist().isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists() or not path.is_file() or path.stat().st_size > 5_000_000:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def file_timestamp(path: Path) -> datetime | None:
    try:
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=IST)
    except Exception:
        return None


def payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in (
        "generated_at_ist",
        "generated_at",
        "timestamp_ist",
        "timestamp",
        "updated_at_ist",
        "updated_at",
        "last_updated_ist",
        "last_updated",
    ):
        value = payload.get(key)
        if not value:
            continue
        try:
            text = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=IST)
            return parsed.astimezone(IST)
        except Exception:
            continue
    return None


def bytes_gb(value: int | float) -> float:
    return round(float(value) / (1024 ** 3), 2)


def refresh_storage_status() -> dict[str, Any]:
    usage = shutil.disk_usage(ROOT)
    used_pct = round((usage.used / usage.total) * 100.0, 2) if usage.total else None
    if used_pct is None:
        status = "UNKNOWN"
        pressure = "UNKNOWN"
    elif used_pct >= 95:
        status = "CRITICAL"
        pressure = "CRITICAL"
    elif used_pct >= 85:
        status = "WARNING"
        pressure = "HIGH"
    else:
        status = "OK"
        pressure = "NORMAL"
    payload = {
        "schema": "titan.infrastructure.storage_status.v1",
        "generated_at_ist": iso_now(),
        "timestamp_ist": iso_now(),
        "status": status,
        "pressure": pressure,
        "root": str(ROOT),
        "total_gb": bytes_gb(usage.total),
        "used_gb": bytes_gb(usage.used),
        "free_gb": bytes_gb(usage.free),
        "used_percent": used_pct,
        "used": f"{used_pct:.2f}%" if used_pct is not None else "UNKNOWN",
        "source": "python.shutil.disk_usage",
        "read_only": True,
    }
    write_json(STORAGE_STATUS_PATH, payload)
    return payload


def refresh_network_status() -> dict[str, Any]:
    started = time.perf_counter()
    status = "UNKNOWN"
    error = None
    latency_ms = None
    resolved_ip = None
    try:
        resolved_ip = socket.gethostbyname(UPSTOX_HOST)
        with socket.create_connection((UPSTOX_HOST, UPSTOX_PORT), timeout=5):
            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            status = "OK"
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        status = "FAILED"
        error = str(exc)
    payload = {
        "schema": "titan.infrastructure.network_status.v1",
        "generated_at_ist": iso_now(),
        "timestamp_ist": iso_now(),
        "status": status,
        "broker": "UPSTOX_API",
        "host": UPSTOX_HOST,
        "port": UPSTOX_PORT,
        "resolved_ip": resolved_ip,
        "latency_ms": latency_ms,
        "age_seconds": 0,
        "error": error,
        "source": "socket.gethostbyname + socket.create_connection",
        "read_only": True,
    }
    write_json(NETWORK_STATUS_PATH, payload)
    return payload


def supabase_credentials() -> tuple[str | None, str | None]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    return url, key


def refresh_supabase_status() -> dict[str, Any]:
    generated_at = iso_now()
    url, key = supabase_credentials()
    base_payload = {
        "schema": "titan.infrastructure.supabase_status.v1",
        "generated_at_ist": generated_at,
        "timestamp_ist": generated_at,
        "status": "UNKNOWN",
        "latency_ms": None,
        "rows": "UNKNOWN",
        "storage": "UNKNOWN",
        "source": "supabase.table(...).select(count=exact).limit(1)",
        "read_only": True,
        "supabase_writes": False,
    }
    if not url or not key:
        payload = dict(base_payload)
        payload.update({"status": "UNKNOWN", "reason": "SUPABASE_CONFIG_MISSING"})
        write_json(SUPABASE_STATUS_PATH, payload)
        return payload
    try:
        from supabase import create_client  # type: ignore
    except Exception as exc:
        payload = dict(base_payload)
        payload.update({"status": "UNKNOWN", "reason": f"SUPABASE_CLIENT_IMPORT_FAILED:{exc}"})
        write_json(SUPABASE_STATUS_PATH, payload)
        return payload
    started = time.perf_counter()
    try:
        client = create_client(url, key)
        table_counts: dict[str, int | None] = {}
        for table in ("runtime_status", "scan_symbols", "trade_results"):
            try:
                result = client.table(table).select("*", count="exact").limit(1).execute()
                table_counts[table] = getattr(result, "count", None)
            except Exception:
                table_counts[table] = None
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        connected = any(value is not None for value in table_counts.values())
        payload = dict(base_payload)
        payload.update(
            {
                "status": "CONNECTED" if connected else "UNKNOWN",
                "latency_ms": latency_ms,
                "rows": sum(value for value in table_counts.values() if isinstance(value, int)) if connected else "UNKNOWN",
                "table_counts": table_counts,
                "reason": "READ_ONLY_QUERY_OK" if connected else "NO_READABLE_TABLE_COUNT",
            }
        )
    except Exception as exc:
        payload = dict(base_payload)
        payload.update({"status": "FAILED", "latency_ms": round((time.perf_counter() - started) * 1000.0, 2), "reason": str(exc)})
    write_json(SUPABASE_STATUS_PATH, payload)
    return payload


def approval_queue_depth(payload: dict[str, Any]) -> int | None:
    for key in ("approvals", "items", "queue", "pending", "requests"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    for key in ("pending_count", "queue_size", "queue_depth"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def refresh_echo_activity() -> dict[str, Any] | None:
    evidence = []
    latest_ts = None
    queue_depth = None
    mission = "UNKNOWN"
    for path in ECHO_EVIDENCE_FILES:
        if not path.exists():
            continue
        payload = read_json(path)
        ts = payload_timestamp(payload) or file_timestamp(path)
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
            mission = str(payload.get("mission_id") or payload.get("objective") or payload.get("status") or path.stem)
        if path.name == "approval_queue.json":
            queue_depth = approval_queue_depth(payload)
        evidence.append({"path": rel(path), "timestamp_ist": ts.isoformat() if ts else None, "status": payload.get("status")})
    if not evidence:
        return None
    age_seconds = max(0, (now_ist() - latest_ts).total_seconds()) if latest_ts else None
    status = "ACTIVE" if age_seconds is not None and age_seconds <= 900 else "STALE"
    payload = {
        "schema": "titan.infrastructure.echo_activity.v1",
        "generated_at_ist": iso_now(),
        "timestamp_ist": latest_ts.isoformat() if latest_ts else iso_now(),
        "status": status,
        "mission": mission,
        "queue_depth": queue_depth if queue_depth is not None else "UNKNOWN",
        "evidence_count": len(evidence),
        "latest_evidence_age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "evidence": evidence,
        "source": "data/runtime/echo evidence files",
        "read_only": True,
    }
    write_json(ECHO_ACTIVITY_PATH, payload)
    return payload


def refresh_relay_status_if_real() -> dict[str, Any] | None:
    candidates = [path for path in RELAY_EVIDENCE_FILES if path.exists()]
    if not candidates:
        return None
    payloads = [(path, read_json(path)) for path in candidates if path.suffix.lower() == ".json"]
    live_payloads = [
        (path, payload)
        for path, payload in payloads
        if str(payload.get("status") or "").upper() in {"RELAY_LIVE", "LIVE", "RUNNING", "CONNECTED", "OK"}
        or payload.get("relay_enabled") is True
    ]
    if not live_payloads:
        return None
    path, source_payload = live_payloads[0]
    ts = payload_timestamp(source_payload) or file_timestamp(path) or now_ist()
    payload = {
        "schema": "titan.infrastructure.relay_status.v1",
        "generated_at_ist": iso_now(),
        "timestamp_ist": ts.isoformat(),
        "status": str(source_payload.get("status") or "UNKNOWN").upper(),
        "sync_status": source_payload.get("sync_status") or source_payload.get("relay_sync_status") or "UNKNOWN",
        "writer": source_payload.get("writer") or source_payload.get("source") or rel(path),
        "source": rel(path),
        "read_only": True,
    }
    write_json(RELAY_STATUS_PATH, payload)
    return payload


def refresh_once() -> dict[str, Any]:
    results: dict[str, Any] = {
        "storage_status": refresh_storage_status(),
        "network_status": refresh_network_status(),
        "supabase_status": refresh_supabase_status(),
        "echo_activity": refresh_echo_activity(),
        "relay_status": refresh_relay_status_if_real(),
    }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh TITAN infrastructure status evidence.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval", type=float, default=5.0, help="Loop interval in seconds.")
    args = parser.parse_args()

    while True:
        results = refresh_once()
        print(
            json.dumps(
                {
                    "timestamp_ist": iso_now(),
                    "storage_status": (results.get("storage_status") or {}).get("status"),
                    "network_status": (results.get("network_status") or {}).get("status"),
                    "supabase_status": (results.get("supabase_status") or {}).get("status"),
                    "echo_activity": (results.get("echo_activity") or {}).get("status") if results.get("echo_activity") else "NOT_WRITTEN",
                    "relay_status": (results.get("relay_status") or {}).get("status") if results.get("relay_status") else "NOT_WRITTEN",
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not args.loop:
            return 0
        time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
