import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


GOVERNANCE_STATUS_PATH = Path("data") / "runtime" / "pyramid_governance_status.json"
DEFAULT_FRESH_SECONDS = 24 * 60 * 60
COMPONENT_PATHS = {
    "feeds": [
        Path("data") / "runtime" / "ohlc_refresh_status.json",
        Path("data") / "live_price_status.json",
        Path("data") / "live_price_cache.json",
    ],
    "report_vault": [Path("data") / "report_vault" / "latest_aggregated_packet.json"],
    "consciousness": [Path("data") / "consciousness_core" / "consciousness_context.json"],
    "experience_vault": [Path("data") / "experience_vault" / "reports" / "external_experience_packet.json"],
    "knowledge_vault": [Path("data") / "knowledge_vault" / "reports" / "knowledge_to_consciousness_packet.json"],
    "master_brain": [Path("data") / "runtime" / "master_brain_status.json"],
    "safety_council": [Path("data") / "execution_safety" / "latest_execution_safety_report.json"],
}
CRITICAL_COMPONENTS = {"feeds", "report_vault", "consciousness", "master_brain", "safety_council"}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path, payload):
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
            json.dump(payload, temp_file, indent=2, sort_keys=True, default=str)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def _read_json(path):
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {"status": "CORRUPT", "payload_type": type(payload).__name__}
    except Exception as exc:
        return {"status": "CORRUPT", "error": str(exc)}


def _age_seconds(path):
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - modified_at).total_seconds()), modified_at.isoformat()


def _payload_status(payload):
    if not isinstance(payload, dict):
        return "MISSING"
    for key in ("status", "last_status", "health", "state"):
        if payload.get(key):
            return str(payload.get(key)).upper()
    return "HEALTHY"


def _component_status(name, paths, fresh_seconds=DEFAULT_FRESH_SECONDS):
    probes = []
    available = []
    for path in paths:
        probe = {
            "path": str(path).replace("\\", "/"),
            "available": path.exists(),
            "status": "MISSING",
            "age_seconds": None,
            "modified_at_utc": None,
            "fresh_seconds": fresh_seconds,
            "warning": None,
        }
        if path.exists():
            age_seconds, modified_at = _age_seconds(path)
            payload = _read_json(path)
            source_status = _payload_status(payload)
            probe.update(
                {
                    "status": source_status,
                    "age_seconds": round(age_seconds, 3),
                    "modified_at_utc": modified_at,
                }
            )
            if age_seconds > fresh_seconds:
                probe["status"] = "STALE"
                probe["warning"] = f"stale:{probe['path']}"
            elif source_status in {"ERROR", "FAILED", "TIMEOUT", "DEGRADED", "CORRUPT", "BLOCKED"}:
                probe["warning"] = f"{source_status.lower()}:{probe['path']}"
            available.append(probe)
        else:
            probe["warning"] = f"missing:{probe['path']}"
        probes.append(probe)

    if not available:
        status = "BLOCKED" if name in CRITICAL_COMPONENTS else "SHADOW_ONLY"
    elif any(item["status"] in {"BLOCKED", "CORRUPT"} for item in available):
        status = "BLOCKED"
    elif any(item["status"] in {"STALE", "TIMEOUT"} for item in available):
        status = "STALE"
    elif any(item["status"] in {"DEGRADED", "ERROR", "FAILED", "WARNING"} for item in available):
        status = "DEGRADED"
    elif name in {"experience_vault", "knowledge_vault"}:
        status = "SHADOW_ONLY"
    else:
        status = "HEALTHY"

    return {
        "component": name,
        "status": status,
        "paths": probes,
        "critical": name in CRITICAL_COMPONENTS,
    }


def _duplicate_risk_active(duplicate_risk):
    if not isinstance(duplicate_risk, dict):
        return False
    positive_keys = (
        "duplicate",
        "duplicate_risk",
        "duplicate_detected",
        "duplicate_order",
        "duplicate_alert",
        "blocked",
        "risk_detected",
    )
    for key, value in duplicate_risk.items():
        normalized = str(key).lower()
        if any(token in normalized for token in positive_keys) and bool(value):
            return True
    return str(duplicate_risk.get("status") or "").upper() in {"DUPLICATE", "BLOCK", "BLOCKED", "REJECTED"}


def _broker_gate_failed(broker_safety):
    if not isinstance(broker_safety, dict):
        return False
    status_text = " ".join(
        str(broker_safety.get(key) or "").upper()
        for key in ("risk_status", "status", "decision", "safety_gate")
    )
    if any(token in status_text for token in ("FAIL", "FAILED", "REJECT", "BLOCK")):
        return True
    if broker_safety.get("live_trading_enabled") and broker_safety.get("execution_allowed") is not True:
        return True
    return False


def evaluate_safety_governance(advisory=None, safety_council=None, pyramid_status=None):
    advisory = advisory if isinstance(advisory, dict) else {}
    safety_council = safety_council if isinstance(safety_council, dict) else {}
    pyramid_status = pyramid_status if isinstance(pyramid_status, dict) else {}

    warnings = []
    stale_warnings = []
    degraded_warnings = []
    block_reasons = []
    caution_reasons = []

    sources = advisory.get("sources") if isinstance(advisory.get("sources"), dict) else {}
    for name, source in sources.items():
        status = str(source.get("status") or "UNKNOWN").upper() if isinstance(source, dict) else "UNKNOWN"
        warning = source.get("warning") if isinstance(source, dict) else None
        if status == "STALE":
            stale_warnings.append({"source": name, "status": status, "warning": warning})
        if status in {"DEGRADED", "WARNING", "MISSING", "CORRUPT", "ERROR"}:
            degraded_warnings.append({"source": name, "status": status, "warning": warning})
        if name in {"consciousness", "report_vault"} and status in {"STALE", "MISSING", "CORRUPT", "ERROR", "DEGRADED"}:
            block_reasons.append(f"critical_{name}_intelligence_{status.lower()}")

    components = pyramid_status.get("components") if isinstance(pyramid_status.get("components"), dict) else {}
    for name, component in components.items():
        status = str(component.get("status") or "UNKNOWN").upper() if isinstance(component, dict) else "UNKNOWN"
        if status in {"STALE", "DEGRADED", "BLOCKED"}:
            warning = {"component": name, "status": status}
            if status == "STALE":
                stale_warnings.append(warning)
            else:
                degraded_warnings.append(warning)
        if name in CRITICAL_COMPONENTS and status in {"STALE", "DEGRADED", "BLOCKED"}:
            block_reasons.append(f"critical_{name}_{status.lower()}")

    market_hour_status = safety_council.get("market_hour_status") if isinstance(safety_council.get("market_hour_status"), dict) else {}
    if market_hour_status.get("trade_window_open") is False:
        block_reasons.append("market_closed")

    if _duplicate_risk_active(safety_council.get("duplicate_risk")):
        block_reasons.append("duplicate_alert_or_order_risk")

    if _broker_gate_failed(safety_council.get("broker_safety")):
        block_reasons.append("broker_execution_safety_gate_failed")

    if safety_council.get("stale_data", {}).get("scanner_stale_data_warning"):
        block_reasons.append("scanner_stale_data_warning")

    no_trade_risk = safety_council.get("no_trade_risk") if isinstance(safety_council.get("no_trade_risk"), dict) else {}
    if no_trade_risk.get("warnings"):
        caution_reasons.append("no_trade_intelligence_warning")

    advisory_status = str(advisory.get("status") or "UNKNOWN").upper()
    if advisory_status in {"WARNING", "STALE", "DEGRADED"}:
        caution_reasons.append(f"advisory_confidence_{advisory_status.lower()}")

    warnings.extend(safety_council.get("warnings") or [])
    warnings.extend(block_reasons)
    warnings.extend(caution_reasons)

    if block_reasons:
        decision = "BLOCK"
    elif caution_reasons or stale_warnings or degraded_warnings:
        decision = "CAUTION"
    else:
        decision = "ALLOW"

    return {
        "decision": decision,
        "governance_decision": decision,
        "block_reasons": sorted(set(block_reasons)),
        "caution_reasons": sorted(set(caution_reasons)),
        "warnings": warnings[:50],
        "governance_warnings": warnings[:50],
        "stale_intelligence_warnings": stale_warnings[:50],
        "degraded_intelligence_warnings": degraded_warnings[:50],
        "advisory_only": True,
        "live_apply_allowed": False,
        "broker_orders": False,
        "telegram_changes": False,
        "strategy_weight_mutation": False,
        "scoring_mutation": False,
    }


def generate_pyramid_governance_status(advisory=None, safety_council=None, output_path=GOVERNANCE_STATUS_PATH):
    components = {
        name: _component_status(name, paths)
        for name, paths in COMPONENT_PATHS.items()
    }
    status = "HEALTHY"
    if any(item["status"] == "BLOCKED" for item in components.values()):
        status = "BLOCKED"
    elif any(item["status"] == "STALE" for item in components.values()):
        status = "STALE"
    elif any(item["status"] == "DEGRADED" for item in components.values()):
        status = "DEGRADED"

    payload = {
        "generated_at": utc_now_iso(),
        "status": status,
        "components": components,
        "safety_scope": "governance_status_only_no_live_execution_no_alert_or_strategy_mutation",
    }
    payload["governance"] = evaluate_safety_governance(advisory, safety_council, payload)
    _atomic_write_json(output_path, payload)
    return payload
