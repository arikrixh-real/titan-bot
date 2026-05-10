"""
TITAN Phase 9 - Cross-Setup Relational Intelligence.

Shadow-only observer for relationships between already-produced setups. This
module writes compact advisory artifacts and never feeds ranking, decisions,
alerts, execution, broker behavior, or market data collection.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "reports" / "cross_setup_report.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "cross_setup_memory.json"
MARKET_NARRATIVE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json"
LIFECYCLE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"
SETUP_FAMILY_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "strategy_family_memory.json"

STATE_VERSION = "9.0"
PHASE9_SHADOW_MODE = True
MAX_SETUPS_TO_ANALYZE = 30
MAX_PAIRWISE_COMPARISONS = 435
MAX_REPORT_ITEMS = 10
MAX_HISTORY = 50
REPORT_REFRESH_SECONDS = 3600
RUNTIME_BUDGET_SECONDS = 0.25


def _now_text() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size > 1_000_000:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _raw_setup(setup: Dict[str, Any]) -> Dict[str, Any]:
    raw = setup.get("raw")
    return raw if isinstance(raw, dict) else setup


def _first_text(*values: Any, default: str = "UNKNOWN") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text[:80]
    return default


def _setup_sector(setup: Dict[str, Any]) -> str:
    raw = _raw_setup(setup)
    return _first_text(
        setup.get("sector"),
        raw.get("sector"),
        raw.get("stock_sector"),
        raw.get("sector_name"),
        default="UNKNOWN",
    )


def _setup_family(setup: Dict[str, Any]) -> str:
    raw = _raw_setup(setup)
    return _first_text(
        setup.get("strategy_family"),
        setup.get("strategy"),
        raw.get("strategy_family"),
        raw.get("strategy"),
        raw.get("setup_type"),
        default="UNKNOWN",
    )


def _symbol(setup: Dict[str, Any]) -> str:
    raw = _raw_setup(setup)
    return _safe_upper(setup.get("symbol") or raw.get("symbol") or raw.get("stock") or "UNKNOWN")


def _side(setup: Dict[str, Any]) -> str:
    raw = _raw_setup(setup)
    side = _safe_upper(setup.get("side") or raw.get("side") or raw.get("direction"))
    return side if side in {"LONG", "SHORT"} else "UNKNOWN"


def _memory_signal() -> Dict[str, Any]:
    narrative = _read_json(MARKET_NARRATIVE_MEMORY_PATH)
    lifecycle = _read_json(LIFECYCLE_MEMORY_PATH)
    family = _read_json(SETUP_FAMILY_MEMORY_PATH)

    current = narrative.get("current_narrative") if isinstance(narrative.get("current_narrative"), dict) else {}
    weak_patterns = []

    for source in (lifecycle, family):
        for key in ("correlated_weakness", "weak_families", "failure_clusters", "top_failure_modes"):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, list):
                weak_patterns.extend(str(item)[:80] for item in value[:MAX_REPORT_ITEMS])

    return {
        "narrative_type": current.get("narrative_type") or narrative.get("narrative_type") or "UNKNOWN",
        "risk_state": current.get("risk_on_risk_off_state") or narrative.get("risk_on_risk_off_state") or "UNKNOWN",
        "memory_available": bool(narrative or lifecycle or family),
        "weak_patterns": weak_patterns[:MAX_REPORT_ITEMS],
    }


def _cluster_items(setups: List[Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
    clusters: Dict[str, List[str]] = defaultdict(list)
    for setup in setups:
        if key_name == "sector":
            key = _setup_sector(setup)
        elif key_name == "family":
            key = _setup_family(setup)
        else:
            key = "UNKNOWN"
        clusters[key].append(_symbol(setup))

    rows = [
        {"name": key, "count": len(symbols), "symbols": symbols[:MAX_REPORT_ITEMS]}
        for key, symbols in clusters.items()
        if key != "UNKNOWN" and len(symbols) >= 2
    ]
    rows.sort(key=lambda item: item["count"], reverse=True)
    return rows[:MAX_REPORT_ITEMS]


def _pairwise_pressure(setups: List[Dict[str, Any]], started_at: float) -> Dict[str, Any]:
    overlap = []
    conflicts = []
    comparisons = 0

    for i, left in enumerate(setups):
        if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
            break
        for right in setups[i + 1:]:
            comparisons += 1
            if comparisons > MAX_PAIRWISE_COMPARISONS:
                break

            left_symbol = _symbol(left)
            right_symbol = _symbol(right)
            same_sector = _setup_sector(left) == _setup_sector(right) != "UNKNOWN"
            same_family = _setup_family(left) == _setup_family(right) != "UNKNOWN"
            left_side = _side(left)
            right_side = _side(right)

            if same_sector or same_family:
                item = {
                    "symbols": [left_symbol, right_symbol],
                    "sector_overlap": same_sector,
                    "family_overlap": same_family,
                }
                if left_side != "UNKNOWN" and right_side != "UNKNOWN" and left_side != right_side:
                    conflicts.append(item)
                else:
                    overlap.append(item)

        if comparisons > MAX_PAIRWISE_COMPARISONS:
            break

    return {
        "comparisons": min(comparisons, MAX_PAIRWISE_COMPARISONS),
        "overlap_pairs": overlap[:MAX_REPORT_ITEMS],
        "conflict_pairs": conflicts[:MAX_REPORT_ITEMS],
    }


def _dominance_score(counter: Counter, total: int) -> float:
    if total <= 0 or not counter:
        return 0.0
    dominant = counter.most_common(1)[0][1]
    return round((dominant / total) * 100.0, 2)


def _top_counter(counter: Counter) -> List[Dict[str, Any]]:
    return [
        {"name": str(name), "count": int(count)}
        for name, count in counter.most_common(MAX_REPORT_ITEMS)
        if name and name != "UNKNOWN"
    ]


def _neutral_result(error: str | None = None) -> Dict[str, Any]:
    result = {
        "version": STATE_VERSION,
        "phase9_shadow_mode": PHASE9_SHADOW_MODE,
        "phase9_applied": False,
        "generated_at": _now_text(),
        "observed_setup_count": 0,
        "relational_state": "NEUTRAL",
        "portfolio_heat_score": 0.0,
        "phase9_rank_adjustment": 0.0,
        "warnings": ["phase9_failed_open"] if error else [],
        "systemic_contradiction_flags": [],
    }
    if error:
        result["error"] = str(error)
    return result


def build_cross_setup_intelligence_shadow(
    evaluated_setups: List[Dict[str, Any]],
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    market_narrative: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build a bounded advisory snapshot from already-produced metadata only.
    Inputs are copied and never mutated.
    """

    started_at = time.monotonic()

    try:
        setup_snapshot = deepcopy(evaluated_setups if isinstance(evaluated_setups, list) else [])
        context_snapshot = deepcopy(context if isinstance(context, dict) else {})
        decision_snapshot = deepcopy(final_decisions if isinstance(final_decisions, dict) else {})
        narrative_snapshot = deepcopy(market_narrative if isinstance(market_narrative, dict) else {})

        setups = [item for item in setup_snapshot[:MAX_SETUPS_TO_ANALYZE] if isinstance(item, dict)]
        if not setups:
            result = _neutral_result()
            result["phase9_applied"] = True
            result["warnings"] = ["no_setups_to_observe"]
            return result

        memory = _memory_signal()
        sectors = Counter(_setup_sector(item) for item in setups)
        sides = Counter(_side(item) for item in setups)
        families = Counter(_setup_family(item) for item in setups)
        pairwise = _pairwise_pressure(setups, started_at)

        total = len(setups)
        sector_concentration = _dominance_score(sectors, total)
        directional_crowding = _dominance_score(sides, total)
        family_concentration = _dominance_score(families, total)
        conflict_count = len(pairwise["conflict_pairs"])
        overlap_count = len(pairwise["overlap_pairs"])

        correlation_pressure = _clamp((overlap_count * 8.0) + (conflict_count * 10.0))
        portfolio_heat = _clamp(
            (sector_concentration * 0.30)
            + (directional_crowding * 0.25)
            + (family_concentration * 0.20)
            + (correlation_pressure * 0.25)
        )

        if portfolio_heat >= 70:
            relational_state = "HIGH_CONCENTRATION"
        elif portfolio_heat >= 45:
            relational_state = "MODERATE_CONCENTRATION"
        else:
            relational_state = "DIVERSIFIED_OR_NEUTRAL"

        risk_state = _safe_upper(
            narrative_snapshot.get("risk_on_risk_off_state")
            or narrative_snapshot.get("risk_state")
            or memory.get("risk_state")
        )

        contradiction_flags = []
        if risk_state == "RISK_ON" and sides.get("SHORT", 0) > sides.get("LONG", 0):
            contradiction_flags.append("short crowding conflicts with risk-on narrative")
        if risk_state == "RISK_OFF" and sides.get("LONG", 0) > sides.get("SHORT", 0):
            contradiction_flags.append("long crowding conflicts with risk-off narrative")
        if conflict_count:
            contradiction_flags.append("same cluster contains opposing trade directions")
        if sector_concentration >= 60:
            contradiction_flags.append("dominant sector concentration detected")

        selected = decision_snapshot.get("selected") if isinstance(decision_snapshot.get("selected"), list) else []
        selected_symbols = {_safe_upper(item.get("symbol")) for item in selected if isinstance(item, dict)}
        isolated = []
        for setup in setups:
            symbol = _symbol(setup)
            if symbol not in selected_symbols:
                continue
            if sectors[_setup_sector(setup)] == 1 and families[_setup_family(setup)] == 1:
                isolated.append(symbol)

        advisory = []
        if portfolio_heat >= 70:
            advisory.append("High setup heat: treat clustered exposure as one risk bucket.")
        elif portfolio_heat >= 45:
            advisory.append("Moderate setup heat: prefer diversified confirmation.")
        else:
            advisory.append("Setup relationships appear diversified or neutral.")
        if contradiction_flags:
            advisory.append("Review systemic contradiction flags before increasing exposure.")

        elapsed_ms = round((time.monotonic() - started_at) * 1000.0, 3)

        return {
            "version": STATE_VERSION,
            "phase9_shadow_mode": PHASE9_SHADOW_MODE,
            "phase9_applied": True,
            "generated_at": _now_text(),
            "observed_setup_count": total,
            "analyzed_setup_limit": MAX_SETUPS_TO_ANALYZE,
            "pairwise_comparisons": pairwise["comparisons"],
            "runtime_ms": elapsed_ms,
            "runtime_bounded": elapsed_ms <= (RUNTIME_BUDGET_SECONDS * 1000.0) + 50.0,
            "relational_state": relational_state,
            "setup_clustering": {
                "sector_clusters": _cluster_items(setups, "sector"),
                "family_clusters": _cluster_items(setups, "family"),
            },
            "sector_concentration": {
                "score": sector_concentration,
                "top": _top_counter(sectors),
            },
            "directional_crowding": {
                "score": directional_crowding,
                "counts": dict(sides),
            },
            "correlation_pressure": {
                "score": round(correlation_pressure, 2),
                "overlap_pairs": pairwise["overlap_pairs"],
            },
            "overlap_conflict_detection": {
                "conflict_pairs": pairwise["conflict_pairs"],
                "conflict_count": conflict_count,
            },
            "portfolio_heat_score": round(portfolio_heat, 2),
            "narrative_dependency_groups": {
                "narrative_type": (
                    narrative_snapshot.get("narrative_type")
                    or memory.get("narrative_type")
                    or "UNKNOWN"
                ),
                "risk_state": risk_state or "UNKNOWN",
                "dominant_families": _top_counter(families),
            },
            "correlated_weakness_memory": {
                "memory_available": memory.get("memory_available"),
                "weak_patterns": memory.get("weak_patterns", []),
            },
            "diversification_advisory": advisory[:MAX_REPORT_ITEMS],
            "systemic_contradiction_flags": contradiction_flags[:MAX_REPORT_ITEMS],
            "isolated_best_setups": isolated[:MAX_REPORT_ITEMS],
            "context_snapshot": {
                "trading_mode": context_snapshot.get("trading_mode"),
                "risk_level": context_snapshot.get("risk_level"),
                "setup_environment": context_snapshot.get("setup_environment"),
            },
            "phase9_rank_adjustment": 0.0,
            "warnings": [],
        }

    except Exception as exc:
        return _neutral_result(str(exc))


def _load_memory() -> Dict[str, Any]:
    data = _read_json(MEMORY_PATH)
    if data:
        return data
    return {
        "version": STATE_VERSION,
        "last_updated": None,
        "current_snapshot": {},
        "history": [],
    }


def _write_memory(snapshot: Dict[str, Any]) -> None:
    memory = _load_memory()
    history = memory.get("history") if isinstance(memory.get("history"), list) else []
    history.append(
        {
            "generated_at": snapshot.get("generated_at"),
            "observed_setup_count": snapshot.get("observed_setup_count"),
            "relational_state": snapshot.get("relational_state"),
            "portfolio_heat_score": snapshot.get("portfolio_heat_score"),
            "contradiction_count": len(snapshot.get("systemic_contradiction_flags") or []),
        }
    )
    history = history[-MAX_HISTORY:]

    payload = {
        "version": STATE_VERSION,
        "last_updated": _now_text(),
        "current_snapshot": snapshot,
        "history": history,
    }
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _top_names(items: Iterable[Dict[str, Any]]) -> List[str]:
    names = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        label = item.get("name") or item.get("symbols") or item
        names.append(str(label)[:120])
    return names[:MAX_REPORT_ITEMS]


def render_cross_setup_report(snapshot: Dict[str, Any]) -> str:
    sector = snapshot.get("sector_concentration") if isinstance(snapshot.get("sector_concentration"), dict) else {}
    crowding = snapshot.get("directional_crowding") if isinstance(snapshot.get("directional_crowding"), dict) else {}
    clustering = snapshot.get("setup_clustering") if isinstance(snapshot.get("setup_clustering"), dict) else {}
    correlation = snapshot.get("correlation_pressure") if isinstance(snapshot.get("correlation_pressure"), dict) else {}

    lines = [
        "TITAN Phase 9 Cross-Setup Relational Shadow Report",
        "===================================================",
        "",
        "Safety",
        "- Shadow advisory only.",
        "- No ranking, decision, alert, execution, broker, market data, or daily-cap integration.",
        "- Uses already-produced setup/context/memory metadata only.",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Observed Setups: {snapshot.get('observed_setup_count', 0)}",
        f"Relational State: {snapshot.get('relational_state')}",
        f"Portfolio Heat Score: {snapshot.get('portfolio_heat_score', 0.0)}",
        f"Runtime Ms: {snapshot.get('runtime_ms', 0.0)}",
        "",
        f"Sector Concentration Score: {sector.get('score', 0.0)}",
        f"Directional Crowding Score: {crowding.get('score', 0.0)}",
        f"Correlation Pressure Score: {correlation.get('score', 0.0)}",
        "",
        "Sector Clusters:",
    ]

    lines.extend([f"- {item}" for item in _top_names(clustering.get("sector_clusters") or [])] or ["- None observed"])
    lines.append("")
    lines.append("Family Clusters:")
    lines.extend([f"- {item}" for item in _top_names(clustering.get("family_clusters") or [])] or ["- None observed"])
    lines.append("")
    lines.append("Diversification Advisory:")
    lines.extend([f"- {item}" for item in (snapshot.get("diversification_advisory") or [])[:MAX_REPORT_ITEMS]] or ["- None"])
    lines.append("")
    lines.append("Systemic Contradiction Flags:")
    lines.extend([f"- {item}" for item in (snapshot.get("systemic_contradiction_flags") or [])[:MAX_REPORT_ITEMS]] or ["- None observed"])

    return "\n".join(lines) + "\n"


def _report_throttled() -> bool:
    try:
        if not REPORT_PATH.exists():
            return False
        age_seconds = datetime.now().timestamp() - REPORT_PATH.stat().st_mtime
        return age_seconds < REPORT_REFRESH_SECONDS
    except Exception:
        return False


def refresh_cross_setup_report(
    evaluated_setups: List[Dict[str, Any]],
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    market_narrative: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Throttled artifact refresh. Fails open and never raises to caller.
    """

    try:
        if _report_throttled():
            memory = _load_memory()
            snapshot = memory.get("current_snapshot") if isinstance(memory.get("current_snapshot"), dict) else {}
            return {"skipped": "CACHE_FRESH", "snapshot": snapshot}

        snapshot = build_cross_setup_intelligence_shadow(
            evaluated_setups=evaluated_setups,
            context=context,
            final_decisions=final_decisions,
            market_narrative=market_narrative,
        )
        report = render_cross_setup_report(snapshot)

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report, encoding="utf-8")
        _write_memory(snapshot)

        return snapshot

    except Exception as exc:
        return _neutral_result(str(exc))
