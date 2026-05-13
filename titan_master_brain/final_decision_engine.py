"""
TITAN MASTER BRAIN - FINAL DECISION ENGINE
STEP 5

Purpose:
- Take evaluated setups from setup_reasoning_engine
- Select only the best candidates
- Reject weak/noisy setups
- Prepare final action list for Master Brain

This does NOT send Telegram alerts yet.
This does NOT execute trades yet.
It only makes final decision recommendations safely.
"""

import csv
import json
import os
from pathlib import Path
from typing import List, Dict, Any

try:
    from engines.probabilistic_world_model import (
        build_probability_report,
        rank_setups_by_probability,
    )
    print("PHASE 15 PROBABILITY MODEL ACTIVE")
except Exception:
    build_probability_report = None
    rank_setups_by_probability = None

try:
    from engines.causal_market_reasoning_engine import build_causal_reasoning_report
    print("PHASE 16 CAUSAL ENGINE ACTIVE")
except Exception:
    build_causal_reasoning_report = None

try:
    from engines.cross_asset_intelligence_engine import build_cross_asset_report
    print("PHASE 17 CROSS-ASSET ENGINE ACTIVE")
except Exception:
    build_cross_asset_report = None

try:
    from engines.portfolio_brain_engine import build_portfolio_brain_report
    print("PHASE 18 PORTFOLIO BRAIN ACTIVE")
except Exception:
    build_portfolio_brain_report = None

try:
    from engines.elite_trade_selection_filter import (
        build_elite_selection_report,
        filter_elite_setups,
    )
    print("PHASE 19 ELITE FILTER ACTIVE")
except Exception:
    build_elite_selection_report = None
    filter_elite_setups = None

try:
    from engines.order_book_microstructure_engine import build_microstructure_report
    print("PHASE 26 MICROSTRUCTURE ENGINE ACTIVE")
except Exception:
    build_microstructure_report = None

try:
    from engines.options_flow_intelligence_engine import build_options_flow_report
    print("PHASE 27 OPTIONS FLOW ENGINE ACTIVE")
except Exception:
    build_options_flow_report = None

try:
    from engines.news_intelligence_2_engine import build_news_intelligence_report
    print("PHASE 28 NEWS INTELLIGENCE 2 ACTIVE")
except Exception:
    build_news_intelligence_report = None

try:
    from engines.economic_calendar_intelligence_engine import build_economic_calendar_report
    print("PHASE 29 ECONOMIC CALENDAR INTELLIGENCE ACTIVE")
except Exception:
    build_economic_calendar_report = None

try:
    from engines.institutional_liquidity_map_engine import build_institutional_liquidity_report
    print("PHASE 30 INSTITUTIONAL LIQUIDITY MAP ACTIVE")
except Exception:
    build_institutional_liquidity_report = None

try:
    from engines.scenario_simulation_engine import build_scenario_simulation_report
    print("PHASE 31 SCENARIO SIMULATION ENGINE ACTIVE")
except Exception:
    build_scenario_simulation_report = None

try:
    from engines.multi_agent_debate_engine import build_multi_agent_debate_report
    print("PHASE 32 MULTI-AGENT DEBATE ENGINE ACTIVE")
except Exception:
    build_multi_agent_debate_report = None

try:
    from engines.self_reflection_meta_cognition_engine import build_self_reflection_report
    print("PHASE 33 SELF-REFLECTION META-COGNITION ACTIVE")
except Exception:
    build_self_reflection_report = None

try:
    from engines.confidence_calibration_engine import build_confidence_calibration_report
    print("PHASE 34 CONFIDENCE CALIBRATION ENGINE ACTIVE")
except Exception:
    build_confidence_calibration_report = None

try:
    from engines.no_trade_intelligence_engine import build_no_trade_intelligence_report
    print("PHASE 35 NO-TRADE INTELLIGENCE ACTIVE")
except Exception:
    build_no_trade_intelligence_report = None


MAX_FINAL_CANDIDATES = 3
CROSS_ASSET_WEIGHT = 0.10
PORTFOLIO_WEIGHT = 0.10
MICROSTRUCTURE_WEIGHT = 0.05
OPTIONS_FLOW_WEIGHT = 0.05
NEWS_INTELLIGENCE_WEIGHT = 0.05
CALENDAR_WEIGHT = 0.05
LIQUIDITY_WEIGHT = 0.05
SCENARIO_WEIGHT = 0.05
DEBATE_WEIGHT = 0.05
REFLECTION_WEIGHT = 0.05
CALIBRATION_WEIGHT = 0.05
NO_TRADE_WEIGHT = 0.05

OPEN_TRADE_PATHS = [
    Path("data/journals/active_trades.csv"),
    Path("active_trades.csv"),
    Path("data/journals/trade_journal.csv"),
    Path("data/journals/trade_journal.jsonl"),
    Path("journal/trade_journal.json"),
    Path("data/journals/trade_results.csv"),
    Path("data/journals/trade_outcomes.csv"),
    Path("data/journals/trade_outcomes.jsonl"),
]


def _decision_rank(decision: str) -> int:
    decision = str(decision or "").upper()

    if decision == "TRUST":
        return 3
    if decision == "DOWNGRADE":
        return 2
    if decision == "REJECT":
        return 1

    return 0


def _confidence_rank(confidence: str) -> int:
    confidence = str(confidence or "").upper()

    if confidence == "HIGH":
        return 3
    if confidence == "MEDIUM":
        return 2
    if confidence == "LOW":
        return 1

    return 0


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _bounded_meta_rank_points(setup: Dict[str, Any]) -> float:
    meta_quality = _safe_float(setup.get("meta_quality_score"), 50.0)
    return max(-0.2, min(0.2, (meta_quality - 50.0) * 0.008))


def _existing_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
        0.0,
    )


def _probability_setup_payload(setup: Dict[str, Any]) -> Dict[str, Any]:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    payload = dict(raw)
    payload.update({key: value for key, value in setup.items() if key != "raw"})
    return payload


def _attach_probability_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open probability annotation for final candidate ranking.
    """
    result = dict(setup)
    existing_score = _existing_score(result)

    if build_probability_report is None:
        result["blended_rank_score"] = existing_score
        return result

    try:
        report = build_probability_report(_probability_setup_payload(result), context or {})
        probability_score = _safe_float(report.get("final_probability_score"), existing_score)

        result["probability_score"] = probability_score
        result["probability_recommendation"] = report.get("recommendation")
        result["probability_expected_value"] = report.get("expected_value")
        result["probability_confidence"] = report.get("probability_confidence_score")
        result["probability_uncertainty"] = report.get("uncertainty_score")
        result["probability_explanations"] = report.get("explanations", [])
        result["blended_rank_score"] = round((0.70 * existing_score) + (0.30 * probability_score), 4)
    except Exception as e:
        result["blended_rank_score"] = existing_score
        result["probability_error"] = str(e)

    return result


def _attach_probability_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if rank_setups_by_probability is not None:
        try:
            rank_setups_by_probability(
                [_probability_setup_payload(candidate) for candidate in candidates],
                context or {},
            )
        except Exception:
            pass

    return [_attach_probability_fields(candidate, context) for candidate in candidates]


def _base_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "blended_rank_score",
            setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
        ),
        0.0,
    )


def _pre_cross_asset_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "new_blended_rank_score",
            setup.get(
                "blended_rank_score",
                setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
            ),
        ),
        0.0,
    )


def _pre_portfolio_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_cross_asset_rank",
            setup.get(
                "new_blended_rank_score",
                setup.get(
                    "blended_rank_score",
                    setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                ),
            ),
        ),
        0.0,
    )


def _pre_microstructure_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_portfolio_rank",
            setup.get(
                "final_cross_asset_rank",
                setup.get(
                    "new_blended_rank_score",
                    setup.get(
                        "blended_rank_score",
                        setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_options_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_microstructure_rank",
            setup.get(
                "final_portfolio_rank",
                setup.get(
                    "final_cross_asset_rank",
                    setup.get(
                        "new_blended_rank_score",
                        setup.get(
                            "blended_rank_score",
                            setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_news_intelligence_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_options_rank",
            setup.get(
                "final_microstructure_rank",
                setup.get(
                    "final_portfolio_rank",
                    setup.get(
                        "final_cross_asset_rank",
                        setup.get(
                            "new_blended_rank_score",
                            setup.get(
                                "blended_rank_score",
                                setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_calendar_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_news_intelligence_rank",
            setup.get(
                "final_options_rank",
                setup.get(
                    "final_microstructure_rank",
                    setup.get(
                        "final_portfolio_rank",
                        setup.get(
                            "final_cross_asset_rank",
                            setup.get(
                                "new_blended_rank_score",
                                setup.get(
                                    "blended_rank_score",
                                    setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_liquidity_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_calendar_rank",
            setup.get(
                "final_news_intelligence_rank",
                setup.get(
                    "final_options_rank",
                    setup.get(
                        "final_microstructure_rank",
                        setup.get(
                            "final_portfolio_rank",
                            setup.get(
                                "final_cross_asset_rank",
                                setup.get(
                                    "new_blended_rank_score",
                                    setup.get(
                                        "blended_rank_score",
                                        setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_scenario_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_liquidity_rank",
            setup.get(
                "final_calendar_rank",
                setup.get(
                    "final_news_intelligence_rank",
                    setup.get(
                        "final_options_rank",
                        setup.get(
                            "final_microstructure_rank",
                            setup.get(
                                "final_portfolio_rank",
                                setup.get(
                                    "final_cross_asset_rank",
                                    setup.get(
                                        "new_blended_rank_score",
                                        setup.get(
                                            "blended_rank_score",
                                            setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_debate_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_scenario_rank",
            setup.get(
                "final_liquidity_rank",
                setup.get(
                    "final_calendar_rank",
                    setup.get(
                        "final_news_intelligence_rank",
                        setup.get(
                            "final_options_rank",
                            setup.get(
                                "final_microstructure_rank",
                                setup.get(
                                    "final_portfolio_rank",
                                    setup.get(
                                        "final_cross_asset_rank",
                                        setup.get(
                                            "new_blended_rank_score",
                                            setup.get(
                                                "blended_rank_score",
                                                setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_reflection_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_debate_rank",
            setup.get(
                "final_scenario_rank",
                setup.get(
                    "final_liquidity_rank",
                    setup.get(
                        "final_calendar_rank",
                        setup.get(
                            "final_news_intelligence_rank",
                            setup.get(
                                "final_options_rank",
                                setup.get(
                                    "final_microstructure_rank",
                                    setup.get(
                                        "final_portfolio_rank",
                                        setup.get(
                                            "final_cross_asset_rank",
                                            setup.get(
                                                "new_blended_rank_score",
                                                setup.get(
                                                    "blended_rank_score",
                                                    setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_calibration_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_reflection_rank",
            setup.get(
                "final_debate_rank",
                setup.get(
                    "final_scenario_rank",
                    setup.get(
                        "final_liquidity_rank",
                        setup.get(
                            "final_calendar_rank",
                            setup.get(
                                "final_news_intelligence_rank",
                                setup.get(
                                    "final_options_rank",
                                    setup.get(
                                        "final_microstructure_rank",
                                        setup.get(
                                            "final_portfolio_rank",
                                            setup.get(
                                                "final_cross_asset_rank",
                                                setup.get(
                                                    "new_blended_rank_score",
                                                    setup.get(
                                                        "blended_rank_score",
                                                        setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _pre_no_trade_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    return _safe_float(
        setup.get(
            "final_calibration_rank",
            setup.get(
                "final_reflection_rank",
                setup.get(
                    "final_debate_rank",
                    setup.get(
                        "final_scenario_rank",
                        setup.get(
                            "final_liquidity_rank",
                            setup.get(
                                "final_calendar_rank",
                                setup.get(
                                    "final_news_intelligence_rank",
                                    setup.get(
                                        "final_options_rank",
                                        setup.get(
                                            "final_microstructure_rank",
                                            setup.get(
                                                "final_portfolio_rank",
                                                setup.get(
                                                    "final_cross_asset_rank",
                                                    setup.get(
                                                        "new_blended_rank_score",
                                                        setup.get(
                                                            "blended_rank_score",
                                                            setup.get("final_score", setup.get("score", raw.get("final_score", raw.get("score")))),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        0.0,
    )


def _final_master_rank_score(setup: Dict[str, Any]) -> float:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    for key in (
        "final_no_trade_rank",
        "final_calibration_rank",
        "final_reflection_rank",
        "final_debate_rank",
        "final_scenario_rank",
        "final_liquidity_rank",
        "final_calendar_rank",
        "final_news_intelligence_rank",
        "final_options_rank",
        "final_microstructure_rank",
        "final_portfolio_rank",
        "final_cross_asset_rank",
        "new_blended_rank_score",
        "blended_rank_score",
        "final_score",
        "score",
        "rank_score",
    ):
        if setup.get(key) is not None:
            return _safe_float(setup.get(key), 0.0)
        if raw.get(key) is not None:
            return _safe_float(raw.get(key), 0.0)
    return 0.0


def _attach_final_master_rank(setup: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(setup)
    result["final_master_rank"] = round(_final_master_rank_score(result), 4)
    return result


def _open_status(value: Any, default_open: bool = True) -> bool:
    if value is None or value == "":
        return default_open
    status = str(value).strip().upper()
    return status in {"OPEN", "ACTIVE", "LIVE", "PENDING", "TRIGGERED"}


def _trade_key(row: Dict[str, Any]) -> str:
    symbol = str(row.get("symbol") or row.get("stock") or row.get("ticker") or "").strip().upper()
    side = str(row.get("side") or row.get("direction") or "").strip().upper()
    entry = str(row.get("entry") or row.get("entry_price") or row.get("price") or "").strip()
    return f"{symbol}|{side}|{entry}"


def _dedupe_open_trades(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict) or not _open_status(row.get("status")):
            continue
        key = _trade_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _read_csv_open_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        default_open = "active_trades" in str(path).replace("\\", "/").lower()
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return [
                row
                for row in csv.DictReader(handle)
                if _open_status(row.get("status") or row.get("outcome") or row.get("result"), default_open=default_open)
            ]
    except Exception:
        return []


def _read_json_open_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []

        default_open = "active_trades" in str(path).replace("\\", "/").lower()

        if path.suffix == ".jsonl":
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict) and _open_status(
                    item.get("status") or item.get("outcome") or item.get("result"),
                    default_open=default_open,
                ):
                    rows.append(item)
            return rows

        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [
                item
                for item in data
                if isinstance(item, dict)
                and _open_status(item.get("status") or item.get("outcome") or item.get("result"), default_open=default_open)
            ]
        if isinstance(data, dict):
            for key in ("open_trades", "active_trades", "trade_results", "trades", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    return [
                        item
                        for item in value
                        if isinstance(item, dict)
                        and _open_status(item.get("status") or item.get("outcome") or item.get("result"), default_open=default_open)
                    ]
            if _open_status(data.get("status") or data.get("outcome") or data.get("result"), default_open=default_open):
                return [data]
    except Exception:
        return []
    return []


def _context_open_trades(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(context, dict):
        return []
    rows = []
    for key in ("open_trades", "active_trades", "trade_results", "journal_open_trades"):
        value = context.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            nested = value.get("data") or value.get("open_trades") or value.get("active_trades")
            if isinstance(nested, list):
                rows.extend(item for item in nested if isinstance(item, dict))
    return _dedupe_open_trades(rows)


def _local_open_trades() -> List[Dict[str, Any]]:
    rows = []
    for path in OPEN_TRADE_PATHS:
        if path.suffix == ".csv":
            rows.extend(_read_csv_open_rows(path))
        elif path.suffix in {".json", ".jsonl"}:
            rows.extend(_read_json_open_rows(path))
    return _dedupe_open_trades(rows)


def _supabase_open_trades() -> List[Dict[str, Any]]:
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return []
        from supabase import create_client

        client = create_client(url, key)
        result = client.table("trade_results").select("*").eq("status", "LIVE").limit(50).execute()
        return _dedupe_open_trades(result.data if isinstance(result.data, list) else [])
    except Exception:
        return []


def _collect_open_trades(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _context_open_trades(context)
    if rows:
        return rows
    rows = _local_open_trades()
    if rows:
        return rows
    return _supabase_open_trades()


def _causal_adjusted_confidence(report: Dict[str, Any]) -> float:
    confidence = _safe_float(report.get("cause_confidence_score"), 0.0)
    event = str(report.get("event_classification") or "").upper()
    news_chain = report.get("news_to_sector_stock_chain") if isinstance(report.get("news_to_sector_stock_chain"), dict) else {}
    index_chain = report.get("index_sector_stock_causality") if isinstance(report.get("index_sector_stock_causality"), dict) else {}
    leadership = report.get("sector_leadership_cause") if isinstance(report.get("sector_leadership_cause"), dict) else {}
    pressure = report.get("market_wide_pressure") if isinstance(report.get("market_wide_pressure"), dict) else {}
    false_news = report.get("false_news_caution") if isinstance(report.get("false_news_caution"), dict) else {}
    cascade = report.get("cascading_event_risk") if isinstance(report.get("cascading_event_risk"), dict) else {}
    graph = report.get("narrative_causality_graph") if isinstance(report.get("narrative_causality_graph"), dict) else {}

    if _safe_float(leadership.get("leadership_score"), 0.0) >= 65.0:
        confidence += 7.0
    if _safe_float(index_chain.get("causal_score"), 0.0) >= 55.0 or index_chain.get("causal_alignment") == "ALIGNED":
        confidence += 5.0
    if _safe_float(news_chain.get("chain_strength"), 0.0) >= 50.0:
        confidence += 6.0
    if len(graph.get("edges", []) or []) >= 4:
        confidence += 3.0
    if cascade.get("active") and _safe_float(cascade.get("risk_score"), 0.0) < 40.0:
        confidence += 2.0

    if false_news.get("active"):
        confidence -= 8.0
    if _safe_float(report.get("cause_confidence_score"), 0.0) < 35.0:
        confidence -= 6.0
    if _safe_float(cascade.get("risk_score"), 0.0) >= 55.0:
        confidence -= 8.0
    if pressure.get("active") and not index_chain.get("active"):
        confidence -= 4.0
    if event in {"NO_CLEAR_EVENT", "UNKNOWN", ""}:
        confidence -= 3.0

    return max(0.0, min(100.0, round(confidence, 2)))


def _attach_causal_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(setup)
    existing_rank = _base_rank_score(result)

    if build_causal_reasoning_report is None:
        result["new_blended_rank_score"] = existing_rank
        return result

    try:
        news_items = []
        if isinstance(context, dict):
            news_items = context.get("news_items") or context.get("news") or []

        report = build_causal_reasoning_report(
            _probability_setup_payload(result),
            context or {},
            news_items=news_items,
        )
        causal_confidence = _causal_adjusted_confidence(report)
        leadership = report.get("sector_leadership_cause") if isinstance(report.get("sector_leadership_cause"), dict) else {}
        pressure = report.get("market_wide_pressure") if isinstance(report.get("market_wide_pressure"), dict) else {}
        delayed = report.get("delayed_effect_tracking") if isinstance(report.get("delayed_effect_tracking"), dict) else {}
        cascade = report.get("cascading_event_risk") if isinstance(report.get("cascading_event_risk"), dict) else {}

        result["causal_primary_cause"] = report.get("primary_cause")
        result["causal_confidence_score"] = causal_confidence
        result["causal_event_classification"] = report.get("event_classification")
        result["causal_market_pressure"] = pressure
        result["causal_sector_leadership"] = leadership
        result["causal_delayed_effect"] = delayed
        result["causal_cascading_risk"] = cascade
        result["causal_explanations"] = report.get("explanations", [])
        result["new_blended_rank_score"] = round((existing_rank * 0.85) + (causal_confidence * 0.15), 4)
    except Exception as e:
        result["new_blended_rank_score"] = existing_rank
        result["causal_error"] = str(e)

    return result


def _attach_causal_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_causal_fields(candidate, context) for candidate in candidates or []]


def _attach_cross_asset_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open cross-asset annotation and bounded 10% ranking blend.
    Existing score fields remain intact; final_cross_asset_rank is additive metadata.
    """
    result = dict(setup)
    existing_rank = _pre_cross_asset_rank_score(result)

    if build_cross_asset_report is None:
        result["final_cross_asset_rank"] = existing_rank
        return result

    try:
        report = build_cross_asset_report(_probability_setup_payload(result), context or {})
        alignment_score = _safe_float(report.get("cross_asset_alignment_score"), existing_rank)
        result["cross_asset_alignment_score"] = alignment_score
        result["cross_asset_bias"] = report.get("cross_asset_bias")
        result["cross_asset_vix_pressure"] = report.get("india_vix_pressure", {})
        result["cross_asset_global_risk_mode"] = report.get("global_risk_mode")
        result["cross_asset_us_market_pressure"] = report.get("us_market_pressure", {})
        result["cross_asset_asian_market_influence"] = report.get("asian_market_influence", {})
        result["cross_asset_european_market_influence"] = report.get("european_market_influence", {})
        result["cross_asset_volatility_transmission"] = report.get("cross_asset_volatility_transmission", {})
        result["cross_asset_explanations"] = report.get("explanations", [])
        result["final_cross_asset_rank"] = round(
            (existing_rank * (1.0 - CROSS_ASSET_WEIGHT)) + (alignment_score * CROSS_ASSET_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_cross_asset_rank"] = existing_rank
        result["cross_asset_error"] = str(e)

    return result


def _attach_cross_asset_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_cross_asset_fields(candidate, context) for candidate in candidates or []]


def _attach_portfolio_fields(
    setup: Dict[str, Any],
    context: Dict[str, Any],
    open_trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Fail-open portfolio annotation and bounded 10% ranking blend.
    Existing ranking fields remain intact; final_portfolio_rank is additive metadata.
    """
    result = dict(setup)
    existing_rank = _pre_portfolio_rank_score(result)

    if build_portfolio_brain_report is None:
        result["final_portfolio_rank"] = existing_rank
        return result

    try:
        report = build_portfolio_brain_report(_probability_setup_payload(result), open_trades or [], context or {})
        safety_score = _safe_float(report.get("portfolio_safety_score"), existing_rank)
        result["portfolio_safety_score"] = safety_score
        result["portfolio_bias"] = report.get("portfolio_bias")
        result["portfolio_heat_score"] = report.get("portfolio_heat_score")
        result["portfolio_total_exposure"] = report.get("total_portfolio_exposure")
        result["portfolio_sector_exposure"] = report.get("sector_exposure", {})
        result["portfolio_crowding"] = report.get("same_direction_crowding", {})
        result["portfolio_drawdown_risk"] = report.get("drawdown_risk", {})
        result["portfolio_var"] = report.get("portfolio_var")
        result["portfolio_concentration_risk"] = report.get("concentration_risk", {})
        result["portfolio_capital_efficiency"] = report.get("capital_efficiency_score")
        result["portfolio_explanations"] = report.get("explanations", [])
        result["final_portfolio_rank"] = round(
            (existing_rank * (1.0 - PORTFOLIO_WEIGHT)) + (safety_score * PORTFOLIO_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_portfolio_rank"] = existing_rank
        result["portfolio_error"] = str(e)

    return result


def _attach_portfolio_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    open_trades = _collect_open_trades(context if isinstance(context, dict) else {})
    return [_attach_portfolio_fields(candidate, context, open_trades) for candidate in candidates or []]


def _attach_microstructure_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open microstructure annotation and bounded 5% ranking blend.
    If data is insufficient, score stays neutral and penalty is minimal.
    """
    result = dict(setup)
    existing_rank = _pre_microstructure_rank_score(result)

    if build_microstructure_report is None:
        result["final_microstructure_rank"] = existing_rank
        return result

    try:
        raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
        depth_data = (
            result.get("depth_data")
            or raw.get("depth_data")
            or context.get("depth_data")
            or context.get("market_depth")
        )
        tick_data = (
            result.get("tick_data")
            or raw.get("tick_data")
            or context.get("tick_data")
            or context.get("ticks")
        )
        market_context = dict(context or {})
        if isinstance(raw.get("market_context"), dict):
            market_context.update(raw.get("market_context"))
        report = build_microstructure_report(result, depth_data=depth_data, tick_data=tick_data, market_context=market_context)
        micro_score = _safe_float(report.get("microstructure_score"), 50.0)
        warning = str(report.get("execution_warning") or "NONE").upper()
        data_mode = str(report.get("data_mode") or "INSUFFICIENT").upper()
        adjusted_score = micro_score
        if warning == "SKIP":
            adjusted_score = max(0.0, micro_score - 25.0)
        elif warning == "REVIEW":
            adjusted_score = max(0.0, micro_score - 10.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["microstructure_score"] = micro_score
        result["microstructure_bias"] = report.get("microstructure_bias")
        result["microstructure_execution_warning"] = warning
        result["microstructure_data_mode"] = data_mode
        result["microstructure_explanations"] = report.get("explanations", [])
        result["final_microstructure_rank"] = round(
            (existing_rank * (1.0 - MICROSTRUCTURE_WEIGHT)) + (adjusted_score * MICROSTRUCTURE_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_microstructure_rank"] = existing_rank
        result["microstructure_error"] = str(e)

    return result


def _attach_microstructure_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_microstructure_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _option_chain_for_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Any:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    option_chain = setup.get("option_chain") or raw.get("option_chain")
    if option_chain is not None:
        return option_chain

    context = context if isinstance(context, dict) else {}
    symbol = str(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock") or "").strip()
    chains = context.get("option_chains")
    if isinstance(chains, dict) and symbol:
        return chains.get(symbol) or chains.get(symbol.upper()) or chains.get(symbol.lower())
    return context.get("option_chain")


def _attach_options_flow_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open options-flow annotation and bounded 5% ranking blend.
    Live execution remains fail-closed; live_order_allowed is never used to
    permit orders.
    """
    result = dict(setup)
    existing_rank = _pre_options_rank_score(result)

    if build_options_flow_report is None:
        result["final_options_rank"] = existing_rank
        return result

    try:
        option_chain = _option_chain_for_setup(result, context)
        report = build_options_flow_report(setup=result, option_chain=option_chain, context=context or {})
        options_score = _safe_float(report.get("options_flow_score"), 50.0)
        warning = str(report.get("options_warning") or "REVIEW").upper()

        result["options_flow_score"] = options_score
        result["options_flow_bias"] = report.get("options_flow_bias")
        result["options_warning"] = warning
        result["options_data_mode"] = report.get("data_mode")
        result["options_explanations"] = report.get("explanations", [])
        result["final_options_rank"] = round(
            (existing_rank * (1.0 - OPTIONS_FLOW_WEIGHT)) + (options_score * OPTIONS_FLOW_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_options_rank"] = existing_rank
        result["options_flow_error"] = str(e)

    return result


def _attach_options_flow_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_options_flow_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _news_items_for_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Any:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    news_items = setup.get("news_items") or raw.get("news_items")
    if news_items is not None:
        return news_items
    context = context if isinstance(context, dict) else {}
    symbol = str(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock") or "").strip()
    news_by_symbol = context.get("news_by_symbol")
    if isinstance(news_by_symbol, dict) and symbol:
        return news_by_symbol.get(symbol) or news_by_symbol.get(symbol.upper()) or news_by_symbol.get(symbol.lower())
    return context.get("news_items") or context.get("news")


def _attach_news_intelligence_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open news intelligence annotation and bounded 5% ranking blend.
    Warning penalties are local to final_news_intelligence_rank and never alter
    Telegram, dashboard, alert caps, or live execution.
    """
    result = dict(setup)
    existing_rank = _pre_news_intelligence_rank_score(result)

    if build_news_intelligence_report is None:
        result["final_news_intelligence_rank"] = existing_rank
        return result

    try:
        news_items = _news_items_for_setup(result, context)
        report = build_news_intelligence_report(setup=result, news_items=news_items, context=context or {})
        news_score = _safe_float(report.get("news_intelligence_score"), 50.0)
        warning = str(report.get("news_warning") or "REVIEW").upper()
        data_mode = str(report.get("news_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = news_score
        if warning == "SKIP":
            adjusted_score = max(0.0, news_score - 30.0)
        elif warning == "REVIEW":
            adjusted_score = max(0.0, news_score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["news_intelligence_score"] = news_score
        result["news_bias"] = report.get("news_bias")
        result["news_warning"] = warning
        result["news_data_mode"] = data_mode
        result["news_sentiment_score"] = report.get("overall_news_sentiment_score")
        result["news_credibility_score"] = report.get("credibility_score")
        result["news_narrative"] = report.get("market_narrative", {})
        result["news_explanations"] = report.get("explanations", [])
        result["final_news_intelligence_rank"] = round(
            (existing_rank * (1.0 - NEWS_INTELLIGENCE_WEIGHT)) + (adjusted_score * NEWS_INTELLIGENCE_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_news_intelligence_rank"] = existing_rank
        result["news_intelligence_error"] = str(e)

    return result


def _attach_news_intelligence_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_news_intelligence_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _calendar_events_for_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Any:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    events = setup.get("calendar_events") or raw.get("calendar_events")
    if events is not None:
        return events
    context = context if isinstance(context, dict) else {}
    symbol = str(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock") or "").strip()
    by_symbol = context.get("calendar_events_by_symbol")
    if isinstance(by_symbol, dict) and symbol:
        return by_symbol.get(symbol) or by_symbol.get(symbol.upper()) or by_symbol.get(symbol.lower())
    return context.get("calendar_events") or context.get("economic_calendar")


def _attach_calendar_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open economic-calendar annotation and bounded 5% ranking blend.
    Warning penalties are local to final_calendar_rank.
    """
    result = dict(setup)
    existing_rank = _pre_calendar_rank_score(result)

    if build_economic_calendar_report is None:
        result["final_calendar_rank"] = existing_rank
        return result

    try:
        events = _calendar_events_for_setup(result, context)
        report = build_economic_calendar_report(setup=result, calendar_events=events, context=context or {})
        score = _safe_float(report.get("calendar_intelligence_score"), 50.0)
        warning = str(report.get("calendar_warning") or "REVIEW").upper()
        data_mode = str(report.get("calendar_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = score
        if warning == "SKIP":
            adjusted_score = max(0.0, score - 30.0)
        elif warning in {"REVIEW", "WAIT"}:
            adjusted_score = max(0.0, score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["calendar_intelligence_score"] = score
        result["calendar_bias"] = report.get("calendar_bias")
        result["calendar_warning"] = warning
        result["calendar_data_mode"] = data_mode
        result["event_risk_score"] = report.get("event_risk_score")
        result["no_trade_caution"] = report.get("no_trade_caution", {})
        result["event_volatility_anticipation"] = report.get("event_volatility_anticipation", {})
        result["calendar_explanations"] = report.get("explanations", [])
        result["final_calendar_rank"] = round(
            (existing_rank * (1.0 - CALENDAR_WEIGHT)) + (adjusted_score * CALENDAR_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_calendar_rank"] = existing_rank
        result["calendar_error"] = str(e)

    return result


def _attach_calendar_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_calendar_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _liquidity_data_for_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Any:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    liquidity_data = setup.get("liquidity_data") or raw.get("liquidity_data") or setup.get("ohlcv") or raw.get("ohlcv")
    if liquidity_data is not None:
        return liquidity_data
    context = context if isinstance(context, dict) else {}
    symbol = str(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock") or "").strip()
    by_symbol = context.get("liquidity_by_symbol") or context.get("ohlcv_by_symbol")
    if isinstance(by_symbol, dict) and symbol:
        return by_symbol.get(symbol) or by_symbol.get(symbol.upper()) or by_symbol.get(symbol.lower())
    return context.get("liquidity_data") or context.get("ohlcv") or context.get("candles")


def _attach_liquidity_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open institutional liquidity-map annotation and bounded 5% ranking
    blend. Warning penalties are local to final_liquidity_rank.
    """
    result = dict(setup)
    existing_rank = _pre_liquidity_rank_score(result)

    if build_institutional_liquidity_report is None:
        result["final_liquidity_rank"] = existing_rank
        return result

    try:
        liquidity_data = _liquidity_data_for_setup(result, context)
        report = build_institutional_liquidity_report(setup=result, liquidity_data=liquidity_data, context=context or {})
        score = _safe_float(report.get("liquidity_map_score"), 50.0)
        warning = str(report.get("liquidity_warning") or "REVIEW").upper()
        data_mode = str(report.get("liquidity_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = score
        if warning == "SKIP":
            adjusted_score = max(0.0, score - 30.0)
        elif warning in {"REVIEW", "WAIT"}:
            adjusted_score = max(0.0, score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["liquidity_map_score"] = score
        result["liquidity_bias"] = report.get("liquidity_bias")
        result["liquidity_warning"] = warning
        result["liquidity_data_mode"] = data_mode
        result["liquidity_magnet_score"] = report.get("liquidity_magnet_score")
        result["liquidity_trap_zone"] = report.get("breakout_trap_zones", {})
        result["liquidity_smart_money_footprints"] = report.get("smart_money_footprints", {})
        result["liquidity_explanations"] = report.get("explanations", [])
        result["final_liquidity_rank"] = round(
            (existing_rank * (1.0 - LIQUIDITY_WEIGHT)) + (adjusted_score * LIQUIDITY_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_liquidity_rank"] = existing_rank
        result["liquidity_error"] = str(e)

    return result


def _attach_liquidity_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_liquidity_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _market_data_for_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Any:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    market_data = setup.get("market_data") or raw.get("market_data") or setup.get("ohlcv") or raw.get("ohlcv")
    if market_data is not None:
        return market_data
    context = context if isinstance(context, dict) else {}
    symbol = str(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock") or "").strip()
    by_symbol = context.get("market_data_by_symbol") or context.get("ohlcv_by_symbol")
    if isinstance(by_symbol, dict) and symbol:
        return by_symbol.get(symbol) or by_symbol.get(symbol.upper()) or by_symbol.get(symbol.lower())
    return context.get("market_data") or context.get("ohlcv") or context.get("candles")


def _attach_scenario_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open scenario-simulation annotation and bounded 5% ranking blend.
    Warning penalties are local to final_scenario_rank.
    """
    result = dict(setup)
    existing_rank = _pre_scenario_rank_score(result)

    if build_scenario_simulation_report is None:
        result["final_scenario_rank"] = existing_rank
        return result

    try:
        market_data = _market_data_for_setup(result, context)
        report = build_scenario_simulation_report(setup=result, context=context or {}, market_data=market_data)
        score = _safe_float(report.get("scenario_score"), 50.0)
        warning = str(report.get("scenario_warning") or "REVIEW").upper()
        data_mode = str(report.get("scenario_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = score
        if warning == "SKIP":
            adjusted_score = max(0.0, score - 30.0)
        elif warning in {"REVIEW", "WAIT"}:
            adjusted_score = max(0.0, score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["scenario_score"] = score
        result["scenario_bias"] = report.get("scenario_bias")
        result["scenario_warning"] = warning
        result["scenario_data_mode"] = data_mode
        result["scenario_expected_value"] = report.get("expected_value_projection", {})
        result["scenario_probability_tree"] = report.get("probability_tree", {})
        result["scenario_stress_risk"] = report.get("stress_case_simulation", {})
        result["scenario_explanations"] = report.get("explanations", [])
        result["final_scenario_rank"] = round(
            (existing_rank * (1.0 - SCENARIO_WEIGHT)) + (adjusted_score * SCENARIO_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_scenario_rank"] = existing_rank
        result["scenario_error"] = str(e)

    return result


def _attach_scenario_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_scenario_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _attach_debate_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open multi-agent debate annotation and bounded 5% ranking blend.
    Warning penalties are local to final_debate_rank.
    """
    result = dict(setup)
    existing_rank = _pre_debate_rank_score(result)

    if build_multi_agent_debate_report is None:
        result["final_debate_rank"] = existing_rank
        return result

    try:
        report = build_multi_agent_debate_report(setup=result, context=context or {})
        score = _safe_float(report.get("debate_score"), 50.0)
        warning = str(report.get("debate_warning") or "REVIEW").upper()
        data_mode = str(report.get("debate_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = score
        if warning == "SKIP":
            adjusted_score = max(0.0, score - 30.0)
        elif warning in {"REVIEW", "WAIT"}:
            adjusted_score = max(0.0, score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["debate_score"] = score
        result["debate_bias"] = report.get("debate_bias")
        result["debate_warning"] = warning
        result["debate_data_mode"] = data_mode
        result["confidence_after_debate"] = report.get("confidence_after_debate")
        result["debate_contradiction_resolution"] = report.get("contradiction_resolution", {})
        result["debate_final_judge"] = report.get("final_judge", {})
        result["debate_explanations"] = report.get("explanations", [])
        result["final_debate_rank"] = round(
            (existing_rank * (1.0 - DEBATE_WEIGHT)) + (adjusted_score * DEBATE_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_debate_rank"] = existing_rank
        result["debate_error"] = str(e)

    return result


def _attach_debate_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_debate_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _trade_history_for_reflection(context: Dict[str, Any]) -> Any:
    if not isinstance(context, dict):
        return []
    for key in ("trade_history", "trade_results", "closed_trades", "recent_trades"):
        value = context.get(key)
        if value:
            return value
    return []


def _trade_result_for_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Any:
    raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else {}
    trade_result = setup.get("trade_result") or raw.get("trade_result")
    if trade_result:
        return trade_result
    if not isinstance(context, dict):
        return {}
    symbol = str(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock") or "").strip().upper()
    for key in ("latest_trade_result", "trade_result"):
        value = context.get(key)
        if isinstance(value, dict):
            return value
    by_symbol = context.get("trade_results_by_symbol") or context.get("latest_trade_result_by_symbol")
    if isinstance(by_symbol, dict) and symbol:
        return by_symbol.get(symbol) or by_symbol.get(symbol.lower()) or by_symbol.get(symbol.upper()) or {}
    return {}


def _attach_reflection_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open self-reflection annotation and bounded 5% ranking blend.
    Warning penalties are local to final_reflection_rank.
    """
    result = dict(setup)
    existing_rank = _pre_reflection_rank_score(result)

    if build_self_reflection_report is None:
        result["final_reflection_rank"] = existing_rank
        return result

    try:
        report = build_self_reflection_report(
            setup=result,
            context=context or {},
            trade_result=_trade_result_for_setup(result, context or {}),
            trade_history=_trade_history_for_reflection(context or {}),
        )
        score = _safe_float(report.get("reflection_score"), 50.0)
        warning = str(report.get("reflection_warning") or "REVIEW").upper()
        data_mode = str(report.get("reflection_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = score
        if warning == "SKIP":
            adjusted_score = max(0.0, score - 30.0)
        elif warning in {"REVIEW", "WAIT"}:
            adjusted_score = max(0.0, score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["reflection_score"] = score
        result["reflection_bias"] = report.get("reflection_bias")
        result["reflection_warning"] = warning
        result["reflection_data_mode"] = data_mode
        result["thought_quality_score"] = report.get("thought_quality_score")
        result["confidence_calibration"] = report.get("confidence_calibration", {})
        result["mistake_patterns"] = report.get("mistake_patterns", {})
        result["self_improvement_suggestions"] = report.get("self_improvement_suggestions", [])
        result["reflection_explanations"] = report.get("explanations", [])
        result["final_reflection_rank"] = round(
            (existing_rank * (1.0 - REFLECTION_WEIGHT)) + (adjusted_score * REFLECTION_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_reflection_rank"] = existing_rank
        result["reflection_error"] = str(e)

    return result


def _attach_reflection_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_reflection_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _prediction_history_for_calibration(context: Dict[str, Any]) -> Any:
    if not isinstance(context, dict):
        return []
    for key in ("prediction_history", "predictions", "confidence_predictions", "calibration_predictions"):
        value = context.get(key)
        if value:
            return value
    return []


def _outcome_history_for_calibration(context: Dict[str, Any]) -> Any:
    if not isinstance(context, dict):
        return []
    for key in ("outcome_history", "trade_results", "closed_trades", "recent_trades"):
        value = context.get(key)
        if value:
            return value
    return []


def _attach_calibration_fields(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail-open confidence-calibration annotation and bounded 5% ranking blend.
    Warning penalties are local to final_calibration_rank.
    """
    result = dict(setup)
    existing_rank = _pre_calibration_rank_score(result)

    if build_confidence_calibration_report is None:
        result["final_calibration_rank"] = existing_rank
        return result

    try:
        report = build_confidence_calibration_report(
            setup=result,
            prediction_history=_prediction_history_for_calibration(context or {}),
            outcome_history=_outcome_history_for_calibration(context or {}),
            context=context or {},
        )
        score = _safe_float(report.get("calibrated_confidence_score"), 50.0)
        warning = str(report.get("calibration_warning") or "REVIEW").upper()
        data_mode = str(report.get("calibration_data_mode") or "INSUFFICIENT").upper()
        adjusted_score = score
        if warning == "SKIP":
            adjusted_score = max(0.0, score - 30.0)
        elif warning in {"REVIEW", "WAIT"}:
            adjusted_score = max(0.0, score - 8.0)
        elif data_mode == "INSUFFICIENT":
            adjusted_score = 50.0

        result["calibrated_confidence_score"] = score
        result["calibration_bias"] = report.get("calibration_bias")
        result["calibration_warning"] = warning
        result["calibration_data_mode"] = data_mode
        result["reliability_score"] = report.get("reliability_score")
        result["overconfidence_penalty"] = report.get("overconfidence_penalty", {})
        result["low_sample_shrinkage"] = report.get("low_sample_shrinkage", {})
        result["confidence_correction"] = report.get("confidence_correction", {})
        result["calibration_explanations"] = report.get("explanations", [])
        result["final_calibration_rank"] = round(
            (existing_rank * (1.0 - CALIBRATION_WEIGHT)) + (adjusted_score * CALIBRATION_WEIGHT),
            4,
        )
    except Exception as e:
        result["final_calibration_rank"] = existing_rank
        result["calibration_error"] = str(e)

    return result


def _attach_calibration_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [_attach_calibration_fields(candidate, context if isinstance(context, dict) else {}) for candidate in candidates or []]


def _recent_setups_for_no_trade(context: Dict[str, Any], candidates: List[Dict[str, Any]] = None) -> Any:
    if isinstance(context, dict):
        for key in ("recent_setups", "evaluated_setups", "setup_history"):
            value = context.get(key)
            if value:
                return value
    return candidates or []


def _attach_no_trade_fields(setup: Dict[str, Any], context: Dict[str, Any], recent_setups: Any = None) -> Dict[str, Any]:
    """
    Fail-open no-trade annotation and subtractive 5% danger adjustment.
    High no_trade_score means danger, so it reduces final_no_trade_rank.
    """
    result = dict(setup)
    existing_rank = _pre_no_trade_rank_score(result)

    if build_no_trade_intelligence_report is None:
        result["final_no_trade_rank"] = existing_rank
        return result

    try:
        report = build_no_trade_intelligence_report(
            setup=result,
            context=context or {},
            recent_setups=recent_setups or [],
        )
        score = _safe_float(report.get("no_trade_score"), 0.0)
        permission = str(report.get("trade_permission") or "REVIEW").upper()
        warning = str(report.get("no_trade_warning") or "REVIEW").upper()
        data_mode = str(report.get("no_trade_data_mode") or "INSUFFICIENT").upper()
        penalty = 0.0 if data_mode == "INSUFFICIENT" else score * NO_TRADE_WEIGHT
        if permission == "BLOCK":
            penalty += 25.0
        elif permission == "WAIT":
            penalty += 12.0
        elif permission == "REVIEW":
            penalty += 5.0
        if data_mode == "INSUFFICIENT":
            penalty = min(penalty, 2.0)

        result["no_trade_score"] = score
        result["trade_permission"] = permission
        result["no_trade_warning"] = warning
        result["no_trade_data_mode"] = data_mode
        result["low_edge_day"] = report.get("low_edge_day", {})
        result["choppy_market"] = report.get("choppy_market", {})
        result["market_toxicity"] = report.get("market_toxicity", {})
        result["wait_mode"] = report.get("wait_mode", {})
        result["no_trade_explanations"] = report.get("explanations", [])
        result["no_trade_block_alert"] = bool(
            permission == "BLOCK" or result["low_edge_day"].get("is_low_edge_day")
        )
        result["final_no_trade_rank"] = round(max(0.0, existing_rank - penalty), 4)
    except Exception as e:
        result["final_no_trade_rank"] = existing_rank
        result["no_trade_error"] = str(e)

    return result


def _attach_no_trade_to_candidates(
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    recent_setups = _recent_setups_for_no_trade(context if isinstance(context, dict) else {}, candidates)
    return [
        _attach_no_trade_fields(candidate, context if isinstance(context, dict) else {}, recent_setups)
        for candidate in candidates or []
    ]


def _elite_candidate_key(candidate: Dict[str, Any]) -> str:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
    symbol = str(candidate.get("symbol") or raw.get("symbol") or raw.get("stock") or "").strip().upper()
    side = str(candidate.get("side") or raw.get("side") or raw.get("direction") or "").strip().upper()
    return f"{symbol}|{side}"


def _attach_elite_state(
    candidate: Dict[str, Any],
    selected_keys: set,
    rejected_by_key: Dict[str, Dict[str, Any]],
    elite_report: Dict[str, Any],
) -> Dict[str, Any]:
    result = dict(candidate)
    key = _elite_candidate_key(result)
    rejected_item = rejected_by_key.get(key, {})
    selected = key in selected_keys
    reject_reason = rejected_item.get("elite_reject_reason") if rejected_item else None

    result["elite_quality_score"] = _safe_float(
        result.get("elite_quality_score", rejected_item.get("elite_quality_score")),
        0.0,
    )
    result["elite_uniqueness_score"] = _safe_float(
        result.get("elite_uniqueness_score", rejected_item.get("elite_uniqueness_score")),
        0.0,
    )
    result["elite_confluence_score"] = _safe_float(
        result.get("elite_confluence_score", rejected_item.get("elite_confluence_score")),
        0.0,
    )
    result["elite_duplicate_rejection"] = bool(reject_reason in {"same_symbol", "same_sector_strategy_side"})
    result["elite_selected"] = bool(selected)
    result["elite_rejection_reason"] = None if selected else reject_reason
    result["trade_scarcity_score"] = elite_report.get("trade_scarcity_score")
    result["low_quality_day"] = elite_report.get("low_quality_day")
    return result


def _apply_elite_filter_to_selected_pool(
    selected_pool: List[Dict[str, Any]],
    context: Dict[str, Any],
    max_candidates: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], bool]:
    """
    Returns selected, rejected, elite_report, applied.
    If the elite engine is unavailable or fails, applied is False and callers
    should preserve previous TITAN behavior.
    """
    if build_elite_selection_report is None or filter_elite_setups is None:
        return [], [], {}, False

    try:
        elite_report = build_elite_selection_report(selected_pool, context=context, max_alerts=max_candidates)
        elite_result = filter_elite_setups(selected_pool, context=context, max_alerts=max_candidates)
        selected = elite_result.get("selected", []) if isinstance(elite_result, dict) else []
        rejected = elite_result.get("rejected", []) if isinstance(elite_result, dict) else []
        low_quality_day = bool(elite_report.get("low_quality_day") or elite_result.get("low_quality_day"))

        selected_keys = {_elite_candidate_key(candidate) for candidate in selected}
        rejected_by_key = {_elite_candidate_key(candidate): candidate for candidate in rejected if isinstance(candidate, dict)}

        annotated_selected = [
            _attach_elite_state(candidate, selected_keys, rejected_by_key, elite_report)
            for candidate in selected
            if isinstance(candidate, dict)
        ]
        annotated_rejected = [
            _attach_elite_state(candidate, selected_keys, rejected_by_key, elite_report)
            for candidate in rejected
            if isinstance(candidate, dict)
        ]

        if low_quality_day:
            all_rejected = []
            seen = set()
            for candidate in annotated_rejected + selected_pool:
                if not isinstance(candidate, dict):
                    continue
                key = _elite_candidate_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                item = _attach_elite_state(candidate, set(), rejected_by_key, elite_report)
                item["elite_selected"] = False
                item["elite_rejection_reason"] = item.get("elite_rejection_reason") or "low_quality_day"
                all_rejected.append(item)
            return [], all_rejected, elite_report, True

        return annotated_selected[:max_candidates], annotated_rejected, elite_report, True
    except Exception:
        return [], [], {}, False


def make_final_decisions(
    evaluated_setups: List[Dict[str, Any]],
    context: Dict[str, Any],
    max_candidates: int = MAX_FINAL_CANDIDATES,
) -> Dict[str, Any]:
    """
    Produces final Master Brain decision.

    Returns:
    {
        "action_mode": "TRADE_CANDIDATES_FOUND" / "OBSERVE_ONLY",
        "selected": [...],
        "rejected": [...],
        "summary": [...]
    }
    """

    evaluated_setups = evaluated_setups or []
    context = context if isinstance(context, dict) else {}

    selected_pool = []
    rejected = []
    summary = []

    trading_mode = context.get("trading_mode", "OBSERVATION")
    risk_level = context.get("risk_level", "UNKNOWN")
    learning_env = context.get("learning_environment", "UNKNOWN")

    summary.append(f"Trading mode: {trading_mode}")
    summary.append(f"Risk level: {risk_level}")
    summary.append(f"Learning environment: {learning_env}")

    if not evaluated_setups:
        return {
            "action_mode": "OBSERVE_ONLY",
            "selected": [],
            "rejected": [],
            "elite_selection_report": {},
            "summary": summary + [
                "No evaluated setups available.",
                "Best action: observe and wait."
            ],
        }

    evaluated_setups = _attach_probability_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_causal_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_cross_asset_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_portfolio_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_microstructure_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_options_flow_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_news_intelligence_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_calendar_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_liquidity_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_scenario_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_debate_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_reflection_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_calibration_to_candidates(evaluated_setups, context)
    evaluated_setups = _attach_no_trade_to_candidates(evaluated_setups, context)
    evaluated_setups = [_attach_final_master_rank(setup) for setup in evaluated_setups]

    for setup in evaluated_setups:
        decision = str(setup.get("decision", "REJECT")).upper()
        confidence = str(setup.get("confidence", "LOW")).upper()

        if decision == "TRUST":
            selected_pool.append(setup)

        elif decision == "DOWNGRADE":
            # Downgraded setups are allowed only if market is selective/allowed.
            if trading_mode in ["SELECTIVE", "AGGRESSIVE"] and risk_level != "HIGH":
                selected_pool.append(setup)
            else:
                rejected.append(setup)

        else:
            rejected.append(setup)

    # Sort best first
    selected_pool.sort(
        key=lambda s: (
            _decision_rank(s.get("decision")),
            _confidence_rank(s.get("confidence")),
            _bounded_meta_rank_points(s),
            _safe_float(s.get("final_master_rank"), _final_master_rank_score(s)),
            _safe_float(s.get("final_no_trade_rank"), _pre_no_trade_rank_score(s)),
            _safe_float(s.get("final_calibration_rank"), _pre_calibration_rank_score(s)),
            _safe_float(s.get("final_reflection_rank"), _pre_reflection_rank_score(s)),
            _safe_float(s.get("final_debate_rank"), _pre_debate_rank_score(s)),
            _safe_float(s.get("final_scenario_rank"), _pre_scenario_rank_score(s)),
            _safe_float(s.get("final_liquidity_rank"), _pre_liquidity_rank_score(s)),
            _safe_float(s.get("final_calendar_rank"), _pre_calendar_rank_score(s)),
            _safe_float(s.get("final_news_intelligence_rank"), _pre_news_intelligence_rank_score(s)),
            _safe_float(s.get("final_options_rank"), _pre_options_rank_score(s)),
            _safe_float(s.get("final_microstructure_rank"), _pre_microstructure_rank_score(s)),
            _safe_float(s.get("final_portfolio_rank"), _pre_portfolio_rank_score(s)),
            _safe_float(s.get("final_cross_asset_rank"), _pre_cross_asset_rank_score(s)),
            _safe_float(s.get("new_blended_rank_score"), _base_rank_score(s)),
            _safe_float(s.get("blended_rank_score"), _existing_score(s)),
            _safe_float(s.get("score")),
            _safe_float(s.get("rr")),
        ),
        reverse=True
    )

    elite_selected, elite_rejected, elite_report, elite_applied = _apply_elite_filter_to_selected_pool(
        selected_pool,
        context,
        max_candidates,
    )

    if elite_applied:
        selected = elite_selected
        rejected.extend(elite_rejected)
        selected_keys = {_elite_candidate_key(candidate) for candidate in selected}
        rejected_keys = {_elite_candidate_key(candidate) for candidate in elite_rejected}
        for candidate in selected_pool:
            key = _elite_candidate_key(candidate)
            if key not in selected_keys and key not in rejected_keys:
                item = dict(candidate)
                item["elite_selected"] = False
                item["elite_rejection_reason"] = "not_elite_selected"
                item["trade_scarcity_score"] = elite_report.get("trade_scarcity_score")
                item["low_quality_day"] = elite_report.get("low_quality_day")
                rejected.append(item)
        if elite_report.get("low_quality_day"):
            summary.append("Elite filter marked this as a low-quality day; alerts suppressed safely.")
        else:
            summary.append(f"Elite filter selected {len(selected)} candidate(s).")
    else:
        selected = selected_pool[:max_candidates]
        overflow_rejected = selected_pool[max_candidates:]
        rejected.extend(overflow_rejected)

    if selected:
        summary.append(f"{len(selected)} final candidate(s) selected.")
        summary.append("Only the strongest setups should move forward.")
        action_mode = "TRADE_CANDIDATES_FOUND"
    else:
        summary.append("No final candidates passed the Master Brain decision layer.")
        summary.append("Best action: observe only.")
        action_mode = "OBSERVE_ONLY"

    return {
        "action_mode": action_mode,
        "selected": selected,
        "rejected": rejected,
        "elite_selection_report": elite_report if elite_applied else {},
        "summary": summary,
    }


def print_final_decisions(decisions: Dict[str, Any]) -> None:
    print("\n[MasterBrain] Final Decision Engine:\n")

    for line in decisions.get("summary", []):
        print(f"[FinalDecision] {line}")

    selected = decisions.get("selected", [])

    if selected:
        print("\n[FinalDecision] Selected candidates:")
        for idx, setup in enumerate(selected, start=1):
            symbol = setup.get("symbol", "UNKNOWN")
            decision = setup.get("decision", "UNKNOWN")
            confidence = setup.get("confidence", "UNKNOWN")
            score = setup.get("score", "NA")
            rr = setup.get("rr", "NA")
            print(f"{idx}. {symbol} → {decision} | {confidence} | Score: {score} | RR: {rr}")
    else:
        print("[FinalDecision] No selected candidates.")
