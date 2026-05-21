# TITAN MASTER BRAIN - INPUT AGGREGATOR (STEP 3B)
# Now includes setup normalizer integration

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from titan_master_brain.memory_reasoning_engine import analyze_memory
from titan_master_brain.neural_schema import neural_packet, utc_now_iso
from titan_master_brain.setup_normalizer import normalize_setups


ADVISORY_STATUS_PATH = Path("data") / "runtime" / "advisory_intelligence_status.json"
PYRAMID_CHAIN_STATUS_PATH = Path("data") / "runtime" / "pyramid_chain_status.json"
SHADOW_RECOMMENDATIONS_PATH = Path("data") / "consciousness_core" / "master_brain_shadow_recommendations.json"
ADVISORY_FRESH_SECONDS = 24 * 60 * 60
ADVISORY_SOURCES = {
    "consciousness": Path("data") / "consciousness_core" / "consciousness_context.json",
    "report_vault": Path("data") / "report_vault" / "latest_aggregated_packet.json",
    "experience_vault": Path("data") / "experience_vault" / "reports" / "external_experience_packet.json",
    "knowledge_vault": Path("data") / "knowledge_vault" / "reports" / "knowledge_to_consciousness_packet.json",
}
PYRAMID_STATUS_PATHS = {
    "feeds_cache": Path("data") / "runtime" / "ohlc_refresh_status.json",
    "scanner": Path("data") / "runtime" / "scanner_status.json",
    "report_vault": Path("data") / "report_vault" / "latest_aggregated_packet.json",
    "experience_vault": Path("data") / "experience_vault" / "reports" / "external_experience_packet.json",
    "knowledge_vault": Path("data") / "knowledge_vault" / "reports" / "knowledge_to_consciousness_packet.json",
    "consciousness_core": Path("data") / "consciousness_core" / "consciousness_context.json",
    "master_brain": Path("data") / "runtime" / "master_brain_status.json",
    "safety_gates": Path("data") / "execution_safety" / "latest_execution_safety_report.json",
    "advisory_bridge": ADVISORY_STATUS_PATH,
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


def _read_json_file(path):
    try:
        display_path = str(path).replace("\\", "/")
        if not path.exists():
            return None, f"missing:{display_path}"
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload, None
    except Exception as exc:
        display_path = str(path).replace("\\", "/")
        return None, f"read_error:{display_path}:{exc}"


def _path_probe(path, fresh_seconds=ADVISORY_FRESH_SECONDS):
    item = {
        "path": str(path).replace("\\", "/"),
        "available": False,
        "status": "MISSING",
        "freshness": None,
        "warning": None,
    }
    try:
        if not path.exists():
            item["warning"] = f"missing:{item['path']}"
            return item
        freshness = _freshness_for_path(path)
        freshness["fresh_seconds"] = fresh_seconds
        item["available"] = True
        item["freshness"] = freshness
        item["status"] = "STALE" if freshness["is_stale"] else "OK"
        if freshness["is_stale"]:
            item["warning"] = f"stale:{item['path']}"
        return item
    except Exception as exc:
        item["status"] = "ERROR"
        item["warning"] = f"probe_error:{item['path']}:{exc}"
        return item


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
        "sample_lessons": (payload.get("lessons") or [])[:5],
        "sample_observations": (payload.get("observations") or [])[:5],
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
        "sample_observations": (payload.get("observations") or [])[:5],
        "sample_beliefs": (payload.get("beliefs") or [])[:5],
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


def _write_json_safely(path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return True
    except Exception:
        return False


def _safe_safety_council_status(advisory=None):
    safety_report, safety_error = _read_json_file(Path("data") / "execution_safety" / "latest_execution_safety_report.json")
    safety_state, state_error = _read_json_file(Path("data") / "execution_safety" / "execution_safety_state.json")
    promotion_memory, promotion_error = _read_json_file(Path("data") / "memory" / "promotion_gate_memory.json")
    scanner_status, scanner_error = _read_json_file(Path("data") / "runtime" / "scanner_status.json")
    no_trade_report, no_trade_error = _read_json_file(Path("data") / "no_trade" / "latest_no_trade_intelligence_report.json")

    warnings = []
    for error in [safety_error, state_error, promotion_error, scanner_error, no_trade_error]:
        if error:
            warnings.append(error)

    market_hour_status = {"status": "UNKNOWN", "trade_window_open": False, "warning": None}
    try:
        from utils.market_hours import is_trade_window, trade_window_text

        market_hour_status = {
            "status": "OPEN" if is_trade_window() else "CLOSED",
            "trade_window_open": bool(is_trade_window()),
            "trade_window": trade_window_text(),
        }
    except Exception as exc:
        market_hour_status["warning"] = f"market_hours_unavailable:{exc}"
        warnings.append(market_hour_status["warning"])

    stale_packets = []
    if isinstance(advisory, dict):
        for name, source in (advisory.get("sources") or {}).items():
            if isinstance(source, dict) and str(source.get("status") or "").upper() == "STALE":
                stale_packets.append(name)

    promotion_summary = promotion_memory.get("promotion_summary") if isinstance(promotion_memory, dict) else {}
    duplicate_check = safety_report.get("duplicate_order_check") if isinstance(safety_report, dict) else {}
    broker_check = safety_report.get("broker_connection_check") if isinstance(safety_report, dict) else {}

    return {
        "mode": "READ_ONLY_STATUS",
        "broker_safety": {
            "broker_execution_mode": (safety_report or safety_state or {}).get("broker_execution_mode"),
            "live_trading_enabled": bool((safety_report or safety_state or {}).get("live_trading_enabled", False)),
            "execution_allowed": bool((safety_report or {}).get("execution_allowed", False)),
            "risk_status": (safety_report or {}).get("risk_status"),
            "broker_connection": broker_check,
        },
        "promotion_gate": {
            "status": (promotion_memory or {}).get("status"),
            "any_live_influence": bool(promotion_summary.get("any_live_influence", False)) if isinstance(promotion_summary, dict) else False,
            "recommended_live_weight": promotion_summary.get("recommended_live_weight", 0.0) if isinstance(promotion_summary, dict) else 0.0,
            "max_promotion_score": promotion_summary.get("max_promotion_score", 0.0) if isinstance(promotion_summary, dict) else 0.0,
        },
        "stale_data": {
            "scanner_stale_data_warning": bool((scanner_status or {}).get("stale_data_warning", False)) if isinstance(scanner_status, dict) else False,
            "stale_symbol_ratio": (scanner_status or {}).get("stale_symbol_ratio") if isinstance(scanner_status, dict) else None,
            "stale_advisory_packets": stale_packets,
        },
        "no_trade_risk": {
            "status": (no_trade_report or {}).get("status") if isinstance(no_trade_report, dict) else None,
            "warnings": (no_trade_report or {}).get("warnings", [])[:10] if isinstance(no_trade_report, dict) else [],
        },
        "market_hour_status": market_hour_status,
        "duplicate_risk": duplicate_check,
        "warnings": warnings[:20],
        "live_apply_allowed": False,
    }


def _build_shadow_improvement_workflow(advisory):
    sources = advisory.get("sources") if isinstance(advisory, dict) else {}
    report_summary = {}
    if isinstance(sources, dict):
        report_summary = (sources.get("report_vault") or {}).get("summary") or {}
        consciousness_summary = (sources.get("consciousness") or {}).get("summary") or {}
        experience_summary = (sources.get("experience_vault") or {}).get("summary") or {}
        knowledge_summary = (sources.get("knowledge_vault") or {}).get("summary") or {}
    else:
        consciousness_summary = {}
        experience_summary = {}
        knowledge_summary = {}

    recommendations = []
    if report_summary.get("conflicts"):
        recommendations.append({
            "title": "Resolve report-vault conflicts before strategy promotion",
            "reason": "aggregated report conflicts present",
            "target_engine": "report_vault",
            "suggested_action": "review conflicting worker outputs and keep downstream influence advisory",
            "status": "SHADOW_RECOMMENDATION",
        })
    if consciousness_summary.get("no_trade_warnings"):
        recommendations.append({
            "title": "Keep no-trade warnings advisory until gate review",
            "reason": "consciousness no-trade warnings present",
            "target_engine": "no_trade",
            "suggested_action": "route to paper/backtest validation before any live filter change",
            "status": "SHADOW_RECOMMENDATION",
        })
    if experience_summary.get("lesson_count", 0):
        recommendations.append({
            "title": "Validate external experience lessons in sandbox",
            "reason": "external imported experience is unvalidated",
            "target_engine": "experience_vault",
            "suggested_action": "use only as sandbox evidence; do not merge with native trade memory",
            "status": "SHADOW_RECOMMENDATION",
        })
    if knowledge_summary.get("observation_count", 0) or knowledge_summary.get("belief_count", 0):
        recommendations.append({
            "title": "Convert knowledge observations to testable hypotheses",
            "reason": "knowledge-vault observations available",
            "target_engine": "knowledge_vault",
            "suggested_action": "route to research/paper validation before strategy changes",
            "status": "SHADOW_RECOMMENDATION",
        })

    if not recommendations:
        recommendations.append({
            "title": "Continue observation only",
            "reason": "no actionable advisory packet evidence found",
            "target_engine": "master_brain",
            "suggested_action": "do not mutate scoring, weights, or strategies",
            "status": "SHADOW_RECOMMENDATION",
        })

    payload = {
        "generated_at": utc_now_iso(),
        "mode": "SHADOW_PROPOSAL_ONLY",
        "proposal_queue_path": "data/consciousness_core/improvement_queue.json",
        "shadow_recommendation_path": str(SHADOW_RECOMMENDATIONS_PATH).replace("\\", "/"),
        "direct_live_mutation": False,
        "direct_scoring_change": False,
        "direct_strategy_replacement": False,
        "recommendations": recommendations[:20],
    }
    _write_json_safely(SHADOW_RECOMMENDATIONS_PATH, payload)
    return payload


def _build_pyramid_chain_status(advisory, safety_council):
    chain = {
        name: _path_probe(path)
        for name, path in PYRAMID_STATUS_PATHS.items()
    }
    warnings = []
    for name, item in chain.items():
        if item.get("warning"):
            warnings.append(f"{name}:{item['warning']}")
    payload = {
        "generated_at": utc_now_iso(),
        "required_chain": [
            "Raw Feeds",
            "Workers",
            "Report Vault",
            "Aggregator",
            "Labs/Vaults",
            "Consciousness Core",
            "Master Brain",
            "Safety Council",
            "Alerts/Journal/Dashboard",
        ],
        "status": "WARNING" if warnings else "OK",
        "components": chain,
        "safety_council": safety_council,
        "advisory_bridge_status": advisory.get("status") if isinstance(advisory, dict) else "UNKNOWN",
        "warnings": warnings[:50],
        "live_apply_allowed": False,
    }
    _write_json_safely(PYRAMID_CHAIN_STATUS_PATH, payload)
    return payload


def _safe_advisory_intelligence():
    generated_at = utc_now_iso()
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
                source["neural_schema"] = neural_packet(
                    source=name,
                    timestamp=generated_at,
                    warnings=source["warning"],
                    risk="MEDIUM",
                    trust_level="MISSING",
                    validation_status="MISSING",
                    action_permission="READ_ONLY",
                    live_apply_allowed=False,
                )
                advisory["warnings"].append(source["warning"])
                advisory["sources"][name] = source
                continue

            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)

            if not isinstance(payload, dict):
                source["status"] = "CORRUPT"
                source["warning"] = f"{name} advisory file is not a JSON object: {source['path']}"
                source["neural_schema"] = neural_packet(
                    source=name,
                    timestamp=generated_at,
                    warnings=source["warning"],
                    risk="HIGH",
                    trust_level="CORRUPT",
                    validation_status="CORRUPT",
                    action_permission="READ_ONLY",
                    live_apply_allowed=False,
                )
                advisory["warnings"].append(source["warning"])
                advisory["sources"][name] = source
                continue

            status, freshness = _source_status(path, payload)
            summary = _compact_payload(name, payload)
            trust_level = summary.get("trust_level") or payload.get("trust_level") or "LOCAL_ADVISORY"
            source.update(
                {
                    "status": status,
                    "available": True,
                    "freshness": freshness,
                    "summary": summary,
                    "neural_schema": neural_packet(
                        source=name,
                        timestamp=generated_at,
                        freshness=freshness,
                        confidence=None,
                        risk="MEDIUM" if status == "STALE" else "LOW",
                        warnings=[],
                        memory_type="EXTERNAL_EXPERIENCE" if name == "experience_vault" else "ADVISORY",
                        trust_level=trust_level,
                        validation_status="STALE" if status == "STALE" else "READ_OK",
                        action_permission="READ_ONLY",
                        live_apply_allowed=False,
                    ),
                }
            )
            if freshness["is_stale"]:
                source["warning"] = f"{name} advisory file is stale: {source['path']}"
                advisory["warnings"].append(source["warning"])

        except Exception as e:
            source["status"] = "CORRUPT"
            source["warning"] = f"{name} advisory file could not be read: {source['path']} ({e})"
            source["neural_schema"] = neural_packet(
                source=name,
                timestamp=generated_at,
                warnings=source["warning"],
                risk="HIGH",
                trust_level="CORRUPT",
                validation_status="READ_ERROR",
                action_permission="READ_ONLY",
                live_apply_allowed=False,
            )
            advisory["warnings"].append(source["warning"])

        advisory["sources"][name] = source

    if any(source.get("status") in {"MISSING", "CORRUPT"} for source in advisory["sources"].values()):
        advisory["status"] = "WARNING"
    elif any(source.get("status") == "STALE" for source in advisory["sources"].values()):
        advisory["status"] = "STALE"

    advisory["strategy_improvement_workflow"] = _build_shadow_improvement_workflow(advisory)
    advisory["safety_council"] = _safe_safety_council_status(advisory)
    _write_advisory_status(advisory)
    _build_pyramid_chain_status(advisory, advisory["safety_council"])
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
