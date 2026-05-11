"""
TITAN Phase 21 Step 1 - Autonomous Research Brain
-------------------------------------------------

Standalone research-only engine. It generates, scores, rejects, and organizes
trading research ideas without changing live rules, strategy weights, alerts,
dashboard, broker/execution, or daily alert caps.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List


WIN_OUTCOMES = {"TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}
LOSS_OUTCOMES = {"SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "STOP_LOSS_HIT", "SL_HIT", "FAILED"}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def clamp(value: Any, min_value: float = 0.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, low)))


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [item for item in safe_list(value) if isinstance(item, dict)]


def _upper(value: Any, default: str = "UNKNOWN") -> str:
    return safe_text(value, default).upper()


def _outcome(row: Dict[str, Any]) -> str:
    value = (
        row.get("outcome")
        or row.get("result")
        or row.get("status")
        or row.get("trade_result")
        or row.get("exit_reason")
    )
    text = _upper(value, "UNKNOWN").replace(" ", "_")
    if text in WIN_OUTCOMES:
        return "WIN"
    if text in LOSS_OUTCOMES:
        return "LOSS"
    if text in {"OPEN", "ACTIVE", "LIVE", "RUNNING"}:
        return "OPEN"
    return text


def _symbol(row: Dict[str, Any]) -> str:
    return _upper(row.get("symbol") or row.get("stock") or row.get("ticker"), "UNKNOWN").replace(".NS", "")


def _sector(row: Dict[str, Any]) -> str:
    return _upper(row.get("sector") or row.get("industry") or row.get("sector_name"), "UNKNOWN")


def _side(row: Dict[str, Any]) -> str:
    side = _upper(row.get("side") or row.get("direction") or row.get("bias"), "UNKNOWN")
    if side in {"BUY", "BULLISH"}:
        return "LONG"
    if side in {"SELL", "BEARISH"}:
        return "SHORT"
    return side


def _strategy(row: Dict[str, Any]) -> str:
    return _upper(row.get("strategy_family") or row.get("setup_type") or row.get("strategy") or row.get("pattern"), "UNKNOWN")


def _score(row: Dict[str, Any]) -> float:
    for key in ("final_portfolio_rank", "final_cross_asset_rank", "elite_quality_score", "blended_rank_score", "final_score", "score", "rank_score"):
        if row.get(key) is not None:
            return clamp(row.get(key))
    return 50.0


def _rr(row: Dict[str, Any]) -> float:
    return safe_float(row.get("rr") or row.get("risk_reward"), 0.0)


def _bucket_stats(rows: Iterable[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row) or "UNKNOWN"
        bucket = buckets.setdefault(key, {"trades": 0, "wins": 0, "losses": 0, "scores": [], "rr": []})
        outcome = _outcome(row)
        bucket["trades"] += 1
        bucket["wins"] += 1 if outcome == "WIN" else 0
        bucket["losses"] += 1 if outcome == "LOSS" else 0
        bucket["scores"].append(_score(row))
        bucket["rr"].append(_rr(row))

    for bucket in buckets.values():
        closed = bucket["wins"] + bucket["losses"]
        bucket["win_rate"] = round((bucket["wins"] / closed * 100.0) if closed else 0.0, 2)
        bucket["avg_score"] = round(sum(bucket["scores"]) / max(1, len(bucket["scores"])), 2)
        bucket["avg_rr"] = round(sum(bucket["rr"]) / max(1, len(bucket["rr"])), 2)
        bucket.pop("scores", None)
        bucket.pop("rr", None)
    return buckets


def _hypothesis(title: str, evidence: str, score: float, hypothesis_type: str = "RESEARCH") -> Dict[str, Any]:
    return {
        "title": title,
        "type": hypothesis_type,
        "evidence": evidence,
        "research_score": round(clamp(score), 2),
        "status": "RESEARCH_ONLY",
        "live_change_allowed": False,
    }


def generate_hypotheses(trade_history: Any = None, scan_history: Any = None, context: Any = None) -> List[Dict[str, Any]]:
    trades = _rows(trade_history)
    scans = _rows(scan_history)
    hypotheses = []

    if not trades and not scans:
        return [
            _hypothesis("Validate high-confluence setups before alerting", "No history available; start with conservative confluence validation.", 55.0, "STARTER"),
            _hypothesis("Compare sector leadership versus isolated stock strength", "No history available; sector context is a safe starter research axis.", 52.0, "STARTER"),
            _hypothesis("Study VIX and portfolio heat impact on setup outcomes", "No history available; risk-state sensitivity should be measured before promotion.", 50.0, "STARTER"),
        ]

    sector_stats = _bucket_stats(trades, _sector)
    strategy_stats = _bucket_stats(trades, _strategy)
    side_stats = _bucket_stats(trades, _side)

    for sector, stats in sector_stats.items():
        if stats["trades"] >= 2 and stats["win_rate"] >= 60:
            hypotheses.append(_hypothesis(f"{sector} sector may contain repeatable edge", f"{stats['wins']} wins from {stats['trades']} trades; win rate {stats['win_rate']}%.", 60 + stats["win_rate"] * 0.25, "SECTOR_EDGE"))
        if stats["trades"] >= 2 and stats["win_rate"] <= 35 and stats["losses"] > stats["wins"]:
            hypotheses.append(_hypothesis(f"{sector} sector may need stricter filters", f"{stats['losses']} losses from {stats['trades']} trades; win rate {stats['win_rate']}%.", 58 + (35 - stats["win_rate"]) * 0.5, "FAILURE_FILTER"))

    for strategy, stats in strategy_stats.items():
        if stats["trades"] >= 2 and stats["win_rate"] >= 60 and stats["avg_rr"] >= 1.8:
            hypotheses.append(_hypothesis(f"{strategy} with RR >= 1.8 may be promising", f"Average RR {stats['avg_rr']} with {stats['win_rate']}% win rate.", 65 + min(20, stats["avg_rr"] * 4), "STRATEGY_EDGE"))

    for side, stats in side_stats.items():
        if side in {"LONG", "SHORT"} and stats["trades"] >= 2:
            hypotheses.append(_hypothesis(f"{side} setup quality should be tested separately", f"{side} win rate is {stats['win_rate']}% across {stats['trades']} trades.", 45 + abs(stats["win_rate"] - 50) * 0.45, "SIDE_SENSITIVITY"))

    if scans:
        pass_rate = sum(1 for row in scans if str(row.get("passed") or row.get("status")).upper() in {"TRUE", "PASSED", "PASS"}) / max(1, len(scans)) * 100
        hypotheses.append(_hypothesis("Scan pass-rate may explain setup scarcity", f"Observed scan pass rate is {round(pass_rate, 2)}%.", 50 + abs(pass_rate - 20) * 0.25, "SCAN_BEHAVIOR"))

    hypotheses.sort(key=lambda item: item["research_score"], reverse=True)
    return hypotheses[:12]


def research_failures(trade_history: Any = None, context: Any = None) -> List[Dict[str, Any]]:
    trades = _rows(trade_history)
    failures = [row for row in trades if _outcome(row) == "LOSS"]
    if not failures:
        return []

    results = []
    for label, key_fn in (("sector", _sector), ("strategy", _strategy), ("side", _side)):
        stats = _bucket_stats(failures, key_fn)
        for key, item in stats.items():
            if item["trades"] >= 1:
                results.append({
                    "focus": f"{label}:{key}",
                    "loss_count": item["trades"],
                    "avg_score": item["avg_score"],
                    "avg_rr": item["avg_rr"],
                    "research_question": f"Why did {key} produce losing outcomes despite selection?",
                    "priority_score": round(clamp(item["trades"] * 18 + item["avg_score"] * 0.25), 2),
                })
    results.sort(key=lambda item: item["priority_score"], reverse=True)
    return results[:10]


def discover_strongest_confluences(trade_history: Any = None, scan_history: Any = None) -> List[Dict[str, Any]]:
    trades = _rows(trade_history)
    winners = [row for row in trades if _outcome(row) == "WIN"]
    confluences = []
    for row in winners:
        features = []
        if _rr(row) >= 2.0:
            features.append("RR>=2")
        if _score(row) >= 70:
            features.append("HIGH_RANK")
        if safe_float(row.get("portfolio_safety_score"), 0) >= 70:
            features.append("PORTFOLIO_SAFE")
        if safe_float(row.get("cross_asset_alignment_score"), 0) >= 65:
            features.append("CROSS_ASSET_ALIGNED")
        if safe_float(row.get("elite_confluence_score"), 0) >= 70:
            features.append("ELITE_CONFLUENCE")
        if features:
            confluences.append({
                "symbol": _symbol(row),
                "sector": _sector(row),
                "strategy": _strategy(row),
                "features": features,
                "confluence_score": round(clamp(len(features) * 18 + _score(row) * 0.25), 2),
            })
    confluences.sort(key=lambda item: item["confluence_score"], reverse=True)
    return confluences[:10]


def generate_strategy_ideas(research_findings: Any = None, context: Any = None) -> List[Dict[str, Any]]:
    findings = _rows(research_findings)
    ideas = []
    if not findings:
        return [
            {"name": "High confluence validation basket", "source": "starter", "idea_score": 55.0, "live_change_allowed": False},
            {"name": "Sector leadership plus cross-asset alignment study", "source": "starter", "idea_score": 53.0, "live_change_allowed": False},
        ]

    for finding in findings:
        title = safe_text(finding.get("title") or finding.get("focus") or finding.get("research_question"), "Research finding")
        score = calculate_research_score(finding, context)
        ideas.append({
            "name": f"Test: {title}",
            "source": finding.get("type") or finding.get("focus") or "research",
            "idea_score": score,
            "validation_required": True,
            "live_change_allowed": False,
        })
    ideas.sort(key=lambda item: item["idea_score"], reverse=True)
    return ideas[:10]


def build_backtest_queue(strategy_ideas: Any = None, hypotheses: Any = None) -> List[Dict[str, Any]]:
    ideas = _rows(strategy_ideas)
    hyps = _rows(hypotheses)
    queue = []
    for idx, item in enumerate(ideas + hyps, start=1):
        score = calculate_research_score(item)
        if score < 45:
            continue
        queue.append({
            "queue_id": f"BT-{idx:03d}",
            "research_item": safe_text(item.get("name") or item.get("title"), "Untitled research"),
            "priority_score": score,
            "minimum_sample_size": 30 if score >= 70 else 50,
            "validation_status": "QUEUED",
            "live_change_allowed": False,
        })
    queue.sort(key=lambda item: item["priority_score"], reverse=True)
    return queue[:12]


def calculate_research_score(item: Any, context: Any = None) -> float:
    item = _as_dict(item)
    context = _as_dict(context)
    base = safe_float(item.get("research_score") or item.get("idea_score") or item.get("priority_score"), 50.0)
    evidence_bonus = 0.0
    evidence_text = " ".join(str(value) for value in item.values()).lower()
    if any(term in evidence_text for term in ("win rate", "loss", "rr", "confluence", "sector", "strategy")):
        evidence_bonus += 8.0
    if context.get("research_focus") and safe_text(context.get("research_focus")).lower() in evidence_text:
        evidence_bonus += 6.0
    if item.get("live_change_allowed") is True:
        evidence_bonus -= 20.0
    return round(clamp(base + evidence_bonus), 2)


def reject_weak_hypotheses(hypotheses: Any = None, min_score: float = 50) -> List[Dict[str, Any]]:
    rejected = []
    for item in _rows(hypotheses):
        score = calculate_research_score(item)
        if score < safe_float(min_score, 50.0):
            rejected.append({**item, "rejection_reason": "below_research_score_threshold", "research_score": score})
    return rejected


def promote_validated_hypotheses(hypotheses: Any = None, validation_results: Any = None) -> List[Dict[str, Any]]:
    hyps = _rows(hypotheses)
    validations = _rows(validation_results)
    validation_by_title = {safe_text(item.get("title") or item.get("research_item") or item.get("name")).lower(): item for item in validations}
    promoted = []
    for item in hyps:
        title = safe_text(item.get("title") or item.get("name"))
        validation = validation_by_title.get(title.lower(), {})
        validated = bool(validation.get("validated")) or safe_float(validation.get("validation_score"), 0.0) >= 70.0
        if validated and calculate_research_score(item) >= 65:
            promoted.append({
                **item,
                "promotion_status": "VALIDATED_FOR_REVIEW_ONLY",
                "live_change_allowed": False,
                "validation_score": safe_float(validation.get("validation_score"), 70.0),
            })
    return promoted


def detect_anomalies(trade_history: Any = None, scan_history: Any = None, context: Any = None) -> List[Dict[str, Any]]:
    trades = _rows(trade_history)
    scans = _rows(scan_history)
    anomalies = []
    high_score_losses = [row for row in trades if _outcome(row) == "LOSS" and _score(row) >= 75]
    low_score_wins = [row for row in trades if _outcome(row) == "WIN" and _score(row) <= 45]
    if high_score_losses:
        anomalies.append({"type": "HIGH_SCORE_LOSSES", "count": len(high_score_losses), "severity_score": round(clamp(len(high_score_losses) * 22), 2)})
    if low_score_wins:
        anomalies.append({"type": "LOW_SCORE_WINS", "count": len(low_score_wins), "severity_score": round(clamp(len(low_score_wins) * 18), 2)})
    if scans:
        passed = sum(1 for row in scans if str(row.get("passed") or row.get("status")).upper() in {"TRUE", "PASSED", "PASS"})
        pass_rate = passed / max(1, len(scans)) * 100
        if pass_rate <= 3 or pass_rate >= 65:
            anomalies.append({"type": "SCAN_PASS_RATE_EXTREME", "pass_rate": round(pass_rate, 2), "severity_score": round(clamp(abs(pass_rate - 20) * 1.5), 2)})
    anomalies.sort(key=lambda item: item.get("severity_score", 0), reverse=True)
    return anomalies[:10]


def discover_edges(trade_history: Any = None, scan_history: Any = None, context: Any = None) -> List[Dict[str, Any]]:
    trades = _rows(trade_history)
    edges = []
    for label, key_fn in (("sector", _sector), ("strategy", _strategy), ("side", _side)):
        stats = _bucket_stats(trades, key_fn)
        for key, item in stats.items():
            closed = item["wins"] + item["losses"]
            if closed >= 2 and item["win_rate"] >= 60:
                edges.append({
                    "edge": f"{label}:{key}",
                    "win_rate": item["win_rate"],
                    "sample_size": closed,
                    "avg_rr": item["avg_rr"],
                    "edge_score": round(clamp(item["win_rate"] * 0.65 + min(25, closed * 4) + item["avg_rr"] * 3), 2),
                    "live_change_allowed": False,
                })
    edges.sort(key=lambda item: item["edge_score"], reverse=True)
    return edges[:10]


def build_experiment_plan(hypothesis: Any, context: Any = None) -> Dict[str, Any]:
    item = _as_dict(hypothesis)
    title = safe_text(item.get("title") or item.get("name") or item.get("research_item"), "Untitled hypothesis")
    score = calculate_research_score(item, context)
    return {
        "hypothesis": title,
        "research_score": score,
        "steps": [
            "Collect at least 30 historical or shadow samples.",
            "Compare win rate, average RR, drawdown, and false-confidence losses.",
            "Segment results by regime, sector, side, and strategy family.",
            "Keep result in research review; do not auto-deploy.",
        ],
        "success_criteria": {
            "minimum_samples": 30 if score >= 70 else 50,
            "minimum_win_rate": 55,
            "minimum_avg_rr": 1.8,
            "max_drawdown_flag": "no elevated drawdown cluster",
        },
        "live_change_allowed": False,
    }


def build_autonomous_research_report(trade_history: Any = None, scan_history: Any = None, context: Any = None) -> Dict[str, Any]:
    trades = _rows(trade_history)
    scans = _rows(scan_history)
    context = _as_dict(context)

    hypotheses = generate_hypotheses(trades, scans, context)
    failure_research = research_failures(trades, context)
    confluences = discover_strongest_confluences(trades, scans)
    findings = hypotheses + failure_research + confluences
    strategy_ideas = generate_strategy_ideas(findings, context)
    backtest_queue = build_backtest_queue(strategy_ideas, hypotheses)
    rejected = reject_weak_hypotheses(hypotheses, min_score=50)
    promoted = promote_validated_hypotheses(hypotheses, context.get("validation_results"))
    anomalies = detect_anomalies(trades, scans, context)
    edges = discover_edges(trades, scans, context)
    experiment_plans = [build_experiment_plan(item, context) for item in (hypotheses[:3] + edges[:2])]

    score_items = hypotheses + strategy_ideas + edges + anomalies
    priority = round(sum(calculate_research_score(item, context) for item in score_items) / max(1, len(score_items)), 2)
    priority = clamp(priority)
    if priority >= 70 or anomalies:
        mode = "INVESTIGATE"
    elif promoted or edges:
        mode = "VALIDATE"
    else:
        mode = "OBSERVE"

    explanations = []
    if not trades and not scans:
        explanations.append("No history available; generated safe starter research ideas only.")
    if hypotheses:
        explanations.append(f"Generated {len(hypotheses)} research hypotheses from available evidence.")
    if failure_research:
        explanations.append("Failure clusters found for investigation.")
    if edges:
        explanations.append("Potential edges found, but they remain research-only until validated.")
    if anomalies:
        explanations.append("Anomalies detected and prioritized for investigation.")
    explanations.append("No live trading rules or strategy weights were changed.")

    return {
        "generated_hypotheses": hypotheses,
        "failure_research": failure_research,
        "strongest_confluences": confluences,
        "strategy_ideas": strategy_ideas,
        "backtest_queue": backtest_queue,
        "rejected_hypotheses": rejected,
        "promoted_hypotheses": promoted,
        "anomalies": anomalies,
        "discovered_edges": edges,
        "experiment_plans": experiment_plans,
        "research_priority_score": round(priority, 2),
        "research_mode": mode,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_trade_history = [
        {
            "symbol": "TCS",
            "sector": "IT",
            "side": "LONG",
            "strategy_family": "Breakout",
            "outcome": "TP",
            "rr": 2.4,
            "final_portfolio_rank": 84,
            "portfolio_safety_score": 80,
            "cross_asset_alignment_score": 76,
            "elite_confluence_score": 82,
        },
        {
            "symbol": "INFY",
            "sector": "IT",
            "side": "LONG",
            "strategy_family": "Breakout",
            "outcome": "TP",
            "rr": 2.1,
            "final_portfolio_rank": 78,
            "cross_asset_alignment_score": 72,
        },
        {
            "symbol": "ICICIBANK",
            "sector": "Banking",
            "side": "LONG",
            "strategy_family": "Momentum",
            "outcome": "SL",
            "rr": 1.5,
            "final_portfolio_rank": 82,
        },
        {
            "symbol": "HDFCBANK",
            "sector": "Banking",
            "side": "LONG",
            "strategy_family": "Momentum",
            "outcome": "SL",
            "rr": 1.7,
            "final_portfolio_rank": 79,
        },
    ]
    sample_scan_history = [
        {"symbol": "TCS", "passed": True, "final_score": 78},
        {"symbol": "INFY", "passed": True, "final_score": 74},
        {"symbol": "SBIN", "passed": False, "final_score": 45},
        {"symbol": "RELIANCE", "passed": False, "final_score": 42},
    ]
    sample_context = {
        "research_focus": "sector",
        "validation_results": [
            {"title": "IT sector may contain repeatable edge", "validated": True, "validation_score": 74}
        ],
    }
    print(json.dumps(build_autonomous_research_report(sample_trade_history, sample_scan_history, sample_context), indent=2, sort_keys=True))
