# TITAN MASTER BRAIN - INPUT AGGREGATOR (STEP 3B)
# Now includes setup normalizer integration

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from titan_master_brain.memory_reasoning_engine import analyze_memory
from titan_master_brain.setup_normalizer import normalize_setups


ADVISORY_STATUS_PATH = Path("data") / "runtime" / "advisory_intelligence_status.json"
ADVISORY_FRESH_SECONDS = 24 * 60 * 60
ADVISORY_SOURCES = {
    "consciousness": Path("data") / "consciousness_core" / "consciousness_context.json",
    "report_vault": Path("data") / "report_vault" / "latest_aggregated_packet.json",
    "experience_vault": Path("data") / "experience_vault" / "reports" / "external_experience_packet.json",
    "knowledge_vault": Path("data") / "knowledge_vault" / "reports" / "knowledge_to_consciousness_packet.json",
}


def _safe_market():
    try:
        from engines.market_filter import market_regime_status
        return {
            "status": "OK",
            "data": market_regime_status(),
            "error": None
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "data": {"market_ok": False, "reason": "market_filter_error"},
            "error": str(e)
        }


def _safe_setups():
    try:
        from engines.setup_engine import scan_for_setups

        raw = scan_for_setups()

        # 🔥 NEW: normalize everything safely
        setups = normalize_setups(raw)

        return {
            "status": "OK",
            "data": setups,
            "count": len(setups),
            "error": None
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "data": [],
            "count": 0,
            "error": str(e)
        }


def _safe_memory():
    possible_paths = [
        "data/journals/trade_outcomes.jsonl",
        "data/journals/trade_outcomes.json",
        "journal/trade_journal.json",
        "data/journals/trade_journal.jsonl",
    ]

    for path in possible_paths:
        try:
            if not os.path.exists(path):
                continue

            recent = []

            if path.endswith(".jsonl"):
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-30:]
                    for line in lines:
                        try:
                            recent.append(json.loads(line.strip()))
                        except:
                            pass

            elif path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    recent = data[-30:]
                elif isinstance(data, dict):
                    for key in ["trades", "outcomes", "records", "data"]:
                        if isinstance(data.get(key), list):
                            recent = data.get(key)[-30:]
                            break

            return {
                "status": "OK",
                "source": path,
                "recent": recent,
                "analysis": analyze_memory({"recent": recent}),
                "error": None
            }

        except Exception as e:
            return {
                "status": "ERROR",
                "source": path,
                "recent": [],
                "analysis": analyze_memory({"recent": []}),
                "error": str(e)
            }

    return {
        "status": "EMPTY",
        "source": None,
        "recent": [],
        "analysis": analyze_memory({"recent": []}),
        "error": "No memory file found"
    }


def _utc_now():
    return datetime.now(timezone.utc)


def _safe_len(value):
    return len(value) if isinstance(value, (list, dict)) else 0


def _freshness_for_path(path):
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_seconds = max(0.0, (_utc_now() - modified_at).total_seconds())
    return {
        "modified_at_utc": modified_at.isoformat(),
        "age_seconds": round(age_seconds, 3),
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
        "is_stale": age_seconds > ADVISORY_FRESH_SECONDS,
    }


def _source_status(path, payload=None):
    status = str(payload.get("status") or "OK").upper() if isinstance(payload, dict) else "OK"
    freshness = _freshness_for_path(path)
    if freshness["is_stale"]:
        status = "STALE"
    return status, freshness


def _compact_consciousness(payload):
    if not isinstance(payload, dict):
        return {}
    report_vault = payload.get("report_vault_intelligence")
    report_vault = report_vault if isinstance(report_vault, dict) else {}
    phase_c = payload.get("phase_c_real_world_intelligence")
    phase_c = phase_c if isinstance(phase_c, dict) else {}
    return {
        "current_focus": payload.get("current_focus"),
        "top_weaknesses": (payload.get("top_weaknesses") or [])[:10],
        "active_regime_warnings": (payload.get("active_regime_warnings") or [])[:10],
        "no_trade_warnings": (payload.get("no_trade_warnings") or [])[:10],
        "confidence_warnings": (payload.get("confidence_warnings") or [])[:10],
        "approved_test_proposals_count": _safe_len(payload.get("approved_test_proposals")),
        "research_priorities_count": _safe_len(payload.get("research_priorities")),
        "report_vault_summary": report_vault.get("summary"),
        "report_vault_conflicts_count": _safe_len(report_vault.get("conflicts")),
        "promotion_allowed": phase_c.get("promotion_allowed"),
        "data_quality_score": phase_c.get("data_quality_score"),
        "validation_depth_score": phase_c.get("validation_depth_score"),
    }


def _compact_report_vault(payload):
    if not isinstance(payload, dict):
        return {}
    return {
        "summary": payload.get("summary"),
        "report_count": payload.get("report_count"),
        "source_workers": (payload.get("source_workers") or [])[:30],
        "conflicts": (payload.get("conflicts") or [])[:10],
        "missing_data": (payload.get("missing_data") or [])[:10],
        "merged_findings_count": _safe_len(payload.get("merged_findings")),
        "safety_scope": payload.get("safety_scope"),
        "trusted_summarized_input": payload.get("trusted_summarized_input"),
        "packet_hash": payload.get("packet_hash"),
    }


def _compact_experience_vault(payload):
    if not isinstance(payload, dict):
        return {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return {
        "source_type": payload.get("source_type"),
        "trust_level": payload.get("trust_level"),
        "lesson_count": _safe_len(payload.get("lessons")),
        "observation_count": _safe_len(payload.get("observations")),
        "warning_count": _safe_len(payload.get("extraction_warnings")),
        "run_stats": payload.get("run_stats") if isinstance(payload.get("run_stats"), dict) else {},
        "core_validation_required": safety.get("core_validation_required"),
        "live_mutation": safety.get("live_mutation"),
        "packet_hash": payload.get("packet_hash"),
    }


def _compact_knowledge_vault(payload):
    if not isinstance(payload, dict):
        return {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return {
        "knowledge_item_count": _safe_len(payload.get("top_knowledge_items")),
        "belief_count": _safe_len(payload.get("beliefs")),
        "research_idea_count": _safe_len(payload.get("research_ideas")),
        "observation_count": _safe_len(payload.get("observations")),
        "warning_count": _safe_len(payload.get("extraction_warnings")),
        "run_stats": payload.get("run_stats") if isinstance(payload.get("run_stats"), dict) else {},
        "live_mutation": safety.get("live_mutation"),
        "direct_strategy_changes": safety.get("direct_strategy_changes"),
        "packet_hash": payload.get("packet_hash"),
    }


def _compact_payload(name, payload):
    if name == "consciousness":
        return _compact_consciousness(payload)
    if name == "report_vault":
        return _compact_report_vault(payload)
    if name == "experience_vault":
        return _compact_experience_vault(payload)
    if name == "knowledge_vault":
        return _compact_knowledge_vault(payload)
    return {}


def _write_advisory_status(advisory):
    try:
        ADVISORY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ADVISORY_STATUS_PATH.write_text(
            json.dumps(advisory, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


def _safe_advisory_intelligence():
    generated_at = datetime.now().isoformat()
    advisory = {
        "status": "OK",
        "generated_at": generated_at,
        "mode": "READ_ONLY_ADVISORY",
        "safety": {
            "direct_score_changes": False,
            "alert_changes": False,
            "execution_changes": False,
            "journal_writes": False,
            "broker_orders": False,
            "supabase_trade_writes": False,
        },
        "freshness_policy": {
            "fresh_seconds": ADVISORY_FRESH_SECONDS,
            "staleness_source": "file_modified_time",
        },
        "warnings": [],
        "sources": {},
    }

    for name, path in ADVISORY_SOURCES.items():
        source = {
            "path": str(path).replace("\\", "/"),
            "status": "UNKNOWN",
            "available": False,
            "freshness": None,
            "warning": None,
            "summary": {},
        }

        try:
            if not path.exists():
                source["status"] = "MISSING"
                source["warning"] = f"{name} advisory file missing: {source['path']}"
                advisory["warnings"].append(source["warning"])
                advisory["sources"][name] = source
                continue

            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)

            if not isinstance(payload, dict):
                source["status"] = "CORRUPT"
                source["warning"] = f"{name} advisory file is not a JSON object: {source['path']}"
                advisory["warnings"].append(source["warning"])
                advisory["sources"][name] = source
                continue

            status, freshness = _source_status(path, payload)
            source.update(
                {
                    "status": status,
                    "available": True,
                    "freshness": freshness,
                    "summary": _compact_payload(name, payload),
                }
            )
            if freshness["is_stale"]:
                source["warning"] = f"{name} advisory file is stale: {source['path']}"
                advisory["warnings"].append(source["warning"])

        except Exception as e:
            source["status"] = "CORRUPT"
            source["warning"] = f"{name} advisory file could not be read: {source['path']} ({e})"
            advisory["warnings"].append(source["warning"])

        advisory["sources"][name] = source

    if any(source.get("status") in {"MISSING", "CORRUPT"} for source in advisory["sources"].values()):
        advisory["status"] = "WARNING"
    elif any(source.get("status") == "STALE" for source in advisory["sources"].values()):
        advisory["status"] = "STALE"

    _write_advisory_status(advisory)
    return advisory


def build_master_input():
    market = _safe_market()
    setups = _safe_setups()
    memory = _safe_memory()
    advisory_intelligence = _safe_advisory_intelligence()

    print("[MasterBrain] Market:", market.get("data"))
    print("[MasterBrain] Setups:", setups.get("count"))
    print("[MasterBrain] Memory records:", memory.get("analysis", {}).get("total_records"))
    print("[MasterBrain] Advisory intelligence:", advisory_intelligence.get("status"))

    return {
        "timestamp": datetime.now().isoformat(),
        "market": market,
        "setups": setups,
        "memory": memory,
        "advisory_intelligence": advisory_intelligence,
        "system_health": {
            "market_connection": market.get("status"),
            "setup_connection": setups.get("status"),
            "memory_connection": memory.get("status"),
            "advisory_intelligence": advisory_intelligence.get("status"),
            "normalizer_active": True
        }
    }
