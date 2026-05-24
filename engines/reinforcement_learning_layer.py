"""
TITAN Phase 20 Step 1 - Reinforcement Learning Layer
----------------------------------------------------

Standalone shadow-learning engine. It computes explainable reward and penalty
signals from trade outcomes but does not update live strategy weights, change
policy, send alerts, touch execution, or modify daily alert caps.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = PROJECT_ROOT / "data" / "memory"
REPORTS_DIR = PROJECT_ROOT / "reports"
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
REINFORCEMENT_MEMORY_PATH = MEMORY_DIR / "reinforcement_learning_memory.json"
REINFORCEMENT_REPORT_PATH = REPORTS_DIR / "phase20_reinforcement_learning_report.txt"
REINFORCEMENT_STATUS_PATH = RUNTIME_DIR / "reinforcement_learning_status.json"
MAX_REPLAY_RECORDS = 500

WIN_OUTCOMES = {
    "TP",
    "WIN",
    "WON",
    "TARGET",
    "TARGET_HIT",
    "PROFIT",
    "SUCCESS",
    "CLOSED_PROFIT",
}

LOSS_OUTCOMES = {
    "SL",
    "LOSS",
    "LOST",
    "STOPLOSS",
    "STOP_LOSS",
    "STOP_LOSS_HIT",
    "SL_HIT",
    "FAILED",
    "CLOSED_LOSS",
}


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


def clamp(value: Any, min_value: float = -100.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, -100.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, 0.0)))


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _raw(trade: Dict[str, Any]) -> Dict[str, Any]:
    raw = trade.get("raw")
    return raw if isinstance(raw, dict) else {}


def _symbol(trade: Dict[str, Any]) -> str:
    raw = _raw(trade)
    return safe_text(trade.get("symbol") or raw.get("symbol") or trade.get("stock") or raw.get("stock"), "UNKNOWN").replace(".NS", "").upper()


def _side(trade: Dict[str, Any]) -> str:
    raw = _raw(trade)
    side = safe_text(trade.get("side") or raw.get("side") or trade.get("direction") or raw.get("direction"), "UNKNOWN").upper()
    if side in {"BUY", "BULLISH"}:
        return "LONG"
    if side in {"SELL", "BEARISH"}:
        return "SHORT"
    return side


def _strategy(trade: Dict[str, Any]) -> str:
    raw = _raw(trade)
    return safe_text(
        trade.get("strategy_family")
        or raw.get("strategy_family")
        or trade.get("setup_type")
        or raw.get("setup_type")
        or trade.get("strategy")
        or raw.get("strategy"),
        "UNKNOWN",
    ).upper()


def _sector(trade: Dict[str, Any]) -> str:
    raw = _raw(trade)
    return safe_text(trade.get("sector") or raw.get("sector") or trade.get("industry") or raw.get("industry"), "UNKNOWN").upper()


def _outcome_text(outcome: Any) -> str:
    if isinstance(outcome, dict):
        outcome = (
            outcome.get("outcome")
            or outcome.get("result")
            or outcome.get("status")
            or outcome.get("exit_reason")
            or outcome.get("trade_result")
        )
    text = safe_text(outcome, "UNKNOWN").upper().replace(" ", "_")
    if text in WIN_OUTCOMES:
        return "WIN"
    if text in LOSS_OUTCOMES:
        return "LOSS"
    if text in {"OPEN", "ACTIVE", "LIVE", "RUNNING"}:
        return "OPEN"
    return text or "UNKNOWN"


def _outcome_pnl(outcome: Any) -> float:
    data = _as_dict(outcome)
    return safe_float(data.get("pnl") or data.get("profit") or data.get("net_pnl") or data.get("return_amount"), 0.0)


def _rr(trade: Dict[str, Any]) -> float:
    raw = _raw(trade)
    return safe_float(trade.get("rr") or raw.get("rr") or trade.get("risk_reward") or raw.get("risk_reward"), 1.0)


def _confidence(trade: Dict[str, Any]) -> float:
    raw = _raw(trade)
    explicit = safe_float(
        trade.get("confidence_score")
        or raw.get("confidence_score")
        or trade.get("causal_confidence_score")
        or raw.get("causal_confidence_score")
        or trade.get("probability_score")
        or raw.get("probability_score"),
        -1.0,
    )
    if explicit >= 0:
        return clamp(explicit, 0.0, 100.0)

    label = safe_text(trade.get("confidence") or raw.get("confidence"), "").upper()
    if label == "HIGH":
        return 85.0
    if label == "MEDIUM":
        return 60.0
    if label == "LOW":
        return 35.0
    return 50.0


def _rank_quality(trade: Dict[str, Any]) -> float:
    raw = _raw(trade)
    for key in (
        "final_portfolio_rank",
        "final_cross_asset_rank",
        "new_blended_rank_score",
        "blended_rank_score",
        "elite_quality_score",
        "final_score",
        "score",
        "rank_score",
    ):
        if key in trade and trade.get(key) is not None:
            return clamp(trade.get(key), 0.0, 100.0)
        if key in raw and raw.get(key) is not None:
            return clamp(raw.get(key), 0.0, 100.0)
    return 50.0


def calculate_trade_reward(trade: Any, outcome: Any, context: Any = None) -> float:
    trade = _as_dict(trade)
    result = _outcome_text(outcome)
    rr = _rr(trade)
    rank = _rank_quality(trade)
    pnl = _outcome_pnl(outcome)

    if result == "WIN":
        reward = 25.0 + min(35.0, rr * 12.0) + ((rank - 50.0) * 0.18)
        if pnl > 0:
            reward += min(12.0, abs(pnl) / 1000.0)
        return round(clamp(reward), 2)

    if result == "LOSS":
        penalty = -25.0 - min(30.0, rr * 8.0) - max(0.0, rank - 65.0) * 0.25
        if pnl < 0:
            penalty -= min(12.0, abs(pnl) / 1000.0)
        return round(clamp(penalty), 2)

    return 0.0


def calculate_risk_adjusted_reward(trade: Any, outcome: Any, context: Any = None) -> float:
    trade = _as_dict(trade)
    base = calculate_trade_reward(trade, outcome, context)
    risk_amount = safe_float(trade.get("risk_amount") or _raw(trade).get("risk_amount"), 0.0)
    pnl = _outcome_pnl(outcome)
    rr = _rr(trade)
    adjustment = 0.0

    if risk_amount > 0 and pnl:
        r_multiple = pnl / risk_amount
        adjustment += clamp(r_multiple * 8.0, -20.0, 20.0)
    elif _outcome_text(outcome) == "WIN":
        adjustment += min(12.0, rr * 3.0)
    elif _outcome_text(outcome) == "LOSS":
        adjustment -= max(6.0, min(18.0, rr * 4.0))

    portfolio_heat = safe_float(trade.get("portfolio_heat_score") or _raw(trade).get("portfolio_heat_score"), 50.0)
    if portfolio_heat >= 70 and _outcome_text(outcome) == "LOSS":
        adjustment -= 8.0
    elif portfolio_heat <= 30 and _outcome_text(outcome) == "WIN":
        adjustment += 4.0

    return round(clamp(base + adjustment), 2)


def calculate_drawdown_penalty(performance_data: Any = None) -> float:
    data = _as_dict(performance_data)
    drawdown = safe_float(data.get("drawdown_pct") or data.get("current_drawdown_pct"), 0.0)
    loss_streak = safe_float(data.get("loss_streak") or data.get("recent_losses"), 0.0)
    daily_loss_pct = safe_float(data.get("daily_loss_pct"), 0.0)
    penalty = (drawdown * 2.5) + (loss_streak * 4.0) + (daily_loss_pct * 3.0)
    return round(clamp(-penalty, -100.0, 0.0), 2)


def calculate_false_confidence_penalty(trade: Any, outcome: Any) -> float:
    trade = _as_dict(trade)
    if _outcome_text(outcome) != "LOSS":
        return 0.0
    confidence = _confidence(trade)
    rank = _rank_quality(trade)
    penalty = 0.0
    if confidence >= 80:
        penalty += 18.0
    elif confidence >= 65:
        penalty += 10.0
    if rank >= 80:
        penalty += 10.0
    elif rank >= 68:
        penalty += 5.0
    return round(clamp(-penalty, -100.0, 0.0), 2)


def calculate_delayed_reward(trade: Any, outcome: Any, context: Any = None) -> float:
    trade = _as_dict(trade)
    context = _as_dict(context)
    result = _outcome_text(outcome)
    holding_hours = safe_float(
        _as_dict(outcome).get("holding_hours")
        or trade.get("holding_hours")
        or context.get("holding_hours"),
        0.0,
    )
    expected_hours = safe_float(trade.get("expected_holding_hours") or context.get("expected_holding_hours"), 6.0)
    if result == "WIN":
        if holding_hours and expected_hours and holding_hours <= expected_hours * 1.5:
            return round(clamp(8.0), 2)
        return round(clamp(4.0), 2)
    if result == "LOSS":
        if holding_hours and expected_hours and holding_hours > expected_hours * 2.0:
            return -8.0
        return -3.0
    return 0.0


def build_regime_reward_key(trade: Any, context: Any = None) -> str:
    trade = _as_dict(trade)
    context = _as_dict(context)
    regime = safe_text(
        context.get("market_regime")
        or context.get("market_type")
        or context.get("risk_mode")
        or trade.get("market_regime")
        or _raw(trade).get("market_regime"),
        "UNKNOWN",
    ).upper()
    side = _side(trade)
    strategy = _strategy(trade)
    sector = _sector(trade)
    return f"{regime}|{side}|{strategy}|{sector}"


def update_regime_reward_memory(memory: Any, trade: Any, outcome: Any, context: Any = None) -> Dict[str, Any]:
    source = _as_dict(memory)
    updated = dict(source)
    key = build_regime_reward_key(trade, context)
    bucket = dict(_as_dict(updated.get(key)))
    reward = calculate_risk_adjusted_reward(trade, outcome, context)
    result = _outcome_text(outcome)

    trades = int(safe_float(bucket.get("trades"), 0.0)) + 1
    wins = int(safe_float(bucket.get("wins"), 0.0)) + (1 if result == "WIN" else 0)
    losses = int(safe_float(bucket.get("losses"), 0.0)) + (1 if result == "LOSS" else 0)
    total_reward = safe_float(bucket.get("total_reward"), 0.0) + reward

    bucket.update({
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "total_reward": round(total_reward, 2),
        "avg_reward": round(total_reward / max(1, trades), 2),
        "last_reward": reward,
    })
    updated[key] = bucket
    return updated


def calculate_strategy_reward(trade: Any, outcome: Any, context: Any = None) -> float:
    trade = _as_dict(trade)
    base = calculate_risk_adjusted_reward(trade, outcome, context)
    confluence = safe_float(trade.get("elite_confluence_score") or _raw(trade).get("elite_confluence_score"), 50.0)
    uniqueness = safe_float(trade.get("elite_uniqueness_score") or _raw(trade).get("elite_uniqueness_score"), 50.0)
    adjustment = ((confluence - 50.0) * 0.10) + ((uniqueness - 50.0) * 0.05)
    return round(clamp(base + adjustment), 2)


def prioritize_reinforcement_memory(memory_items: Any) -> float:
    items = _as_list(memory_items)
    if isinstance(memory_items, dict):
        items = list(memory_items.values())
    if not items:
        return 50.0

    priorities = []
    for item in items:
        row = _as_dict(item)
        trades = safe_float(row.get("trades") or row.get("count"), 0.0)
        avg_reward = abs(safe_float(row.get("avg_reward") or row.get("reward"), 0.0))
        recency = safe_float(row.get("recency_score"), 50.0)
        priorities.append(clamp((min(50.0, trades * 4.0) * 0.35) + (min(50.0, avg_reward) * 0.45) + (recency * 0.20), 0.0, 100.0))
    return round(sum(priorities) / max(1, len(priorities)), 2)


def calculate_exploration_exploitation_score(memory: Any = None, context: Any = None) -> float:
    memory = _as_dict(memory)
    context = _as_dict(context)
    total_trades = safe_float(memory.get("total_trades") or memory.get("trades"), 0.0)
    stability = check_policy_stability(memory).get("stability_score", 50.0)
    market_uncertainty = safe_float(context.get("uncertainty_score") or context.get("market_uncertainty"), 50.0)

    # Higher score means exploit known edges; lower means keep exploring.
    score = 50.0 + min(25.0, total_trades * 0.8) + ((stability - 50.0) * 0.25) - ((market_uncertainty - 50.0) * 0.20)
    return round(clamp(score, 0.0, 100.0), 2)


def _normalize_replay_trade(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": record.get("symbol"),
        "side": record.get("side"),
        "strategy_family": record.get("setup_type") or record.get("strategy"),
        "sector": record.get("sector") or record.get("sector_rotation_label"),
        "entry": record.get("entry"),
        "sl": record.get("sl"),
        "target": record.get("target"),
        "rr": record.get("rr"),
        "score": record.get("score"),
        "final_score": record.get("score"),
        "confidence_score": record.get("replay_interpretation_confidence")
        or record.get("replay_realism_confidence")
        or record.get("semantic_label_confidence"),
        "source_type": "HISTORICAL_REPLAY",
        "trading_mode": "RESEARCH_ONLY",
        "raw": record,
    }


def _normalize_replay_outcome(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "outcome": record.get("outcome"),
        "pnl": safe_float(record.get("pnl_points"), 0.0),
        "holding_hours": safe_float(record.get("holding_period_days"), 0.0) * 24.0,
        "source_type": "HISTORICAL_REPLAY",
    }


def _normalize_replay_context(record: Dict[str, Any]) -> Dict[str, Any]:
    regime = (
        record.get("regime_label")
        or record.get("market_context_label")
        or record.get("trend")
        or "HISTORICAL_REPLAY"
    )
    return {
        "market_regime": regime,
        "market_type": regime,
        "uncertainty_score": 50.0,
        "source_type": "HISTORICAL_REPLAY",
        "research_only": True,
        "advisory_only": True,
        "shadow_mode": True,
        "live_mutation": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
        "affects_live_execution_directly": False,
    }


def build_reinforcement_memory_from_replay(
    records: Any,
    existing_memory: Any = None,
    max_records: int = MAX_REPLAY_RECORDS,
) -> Dict[str, Any]:
    """
    Build a bounded Phase 20 advisory memory snapshot from historical replay rows.

    This is intentionally shadow-only. It returns local memory data and never
    mutates live ranking, scanner output, broker state, Telegram, or Supabase.
    """
    source_records = [record for record in _as_list(records) if isinstance(record, dict)]
    bounded_records = source_records[-max(1, min(int(safe_float(max_records, MAX_REPLAY_RECORDS)), MAX_REPLAY_RECORDS)) :]
    prior = _as_dict(existing_memory)
    regime_memory = dict(_as_dict(prior.get("regime_memory")))
    reports: List[Dict[str, Any]] = []
    wins = 0
    losses = 0

    for record in bounded_records:
        outcome_label = _outcome_text(record.get("outcome"))
        if outcome_label not in {"WIN", "LOSS"}:
            continue

        trade = _normalize_replay_trade(record)
        outcome = _normalize_replay_outcome(record)
        context = _normalize_replay_context(record)
        regime_memory = update_regime_reward_memory(regime_memory, trade, outcome, context)
        report = build_reinforcement_learning_report(
            trade,
            outcome,
            context=context,
            memory={"regime_memory": regime_memory, "total_trades": len(bounded_records)},
        )
        reports.append(report)
        wins += 1 if outcome_label == "WIN" else 0
        losses += 1 if outcome_label == "LOSS" else 0

    policy_stability = check_policy_stability({"regime_memory": regime_memory})
    return {
        "version": "20.0",
        "last_updated": _now_utc(),
        "source_type": "HISTORICAL_REPLAY",
        "research_only": True,
        "advisory_only": True,
        "shadow_mode": True,
        "runtime_bounded": True,
        "records_received": len(source_records),
        "records_processed": len(reports),
        "max_records_per_run": MAX_REPLAY_RECORDS,
        "total_trades": sum(int(safe_float(bucket.get("trades"), 0.0)) for bucket in regime_memory.values()),
        "total_wins": wins,
        "total_losses": losses,
        "regime_memory": regime_memory,
        "policy_stability": policy_stability,
        "memory_priority": prioritize_reinforcement_memory(regime_memory),
        "exploration_exploitation_score": calculate_exploration_exploitation_score(
            {"regime_memory": regime_memory, "total_trades": len(reports)},
            {"market_uncertainty": 50.0},
        ),
        "sample_reports": reports[-10:],
        "safety": {
            "final_decision_engine_rank_mutation": False,
            "scanner_mutation": False,
            "execution_mutation": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
            "autonomous_self_modifying_live_trading": False,
        },
    }


def write_reinforcement_learning_report(memory: Dict[str, Any], path: Path = REINFORCEMENT_REPORT_PATH) -> None:
    lines = [
        "TITAN PHASE 20 REINFORCEMENT LEARNING REPORT",
        "=" * 60,
        f"Updated: {memory.get('last_updated')}",
        f"Source: {memory.get('source_type')}",
        f"Research only: {memory.get('research_only')}",
        f"Advisory only: {memory.get('advisory_only')}",
        f"Shadow mode: {memory.get('shadow_mode')}",
        f"Records processed: {memory.get('records_processed')}",
        f"Memory priority: {memory.get('memory_priority')}",
        f"Exploration/exploitation score: {memory.get('exploration_exploitation_score')}",
        f"Policy stability: {memory.get('policy_stability', {}).get('state')}",
        "",
        "SAFETY",
        "-" * 60,
    ]
    for key, value in sorted(_as_dict(memory.get("safety")).items()):
        lines.append(f"{key}: {str(value).lower()}")

    lines.extend(["", "TOP REGIME REWARD MEMORY", "-" * 60])
    buckets = list(_as_dict(memory.get("regime_memory")).items())
    buckets.sort(key=lambda item: int(safe_float(_as_dict(item[1]).get("trades"), 0.0)), reverse=True)
    for name, bucket in buckets[:12]:
        row = _as_dict(bucket)
        lines.append(
            f"{name}: trades={row.get('trades')}, wins={row.get('wins')}, "
            f"losses={row.get('losses')}, avg_reward={row.get('avg_reward')}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def refresh_reinforcement_memory_from_replay(
    records: Any,
    write_files: bool = True,
    memory_path: Path = REINFORCEMENT_MEMORY_PATH,
    report_path: Path = REINFORCEMENT_REPORT_PATH,
    status_path: Path = REINFORCEMENT_STATUS_PATH,
) -> Dict[str, Any]:
    existing_memory = _read_json(memory_path)
    memory = build_reinforcement_memory_from_replay(records, existing_memory=existing_memory)
    status = {
        "timestamp_utc": memory.get("last_updated"),
        "status": "CONNECTED_SHADOW" if memory.get("records_processed") else "CONNECTED_NO_REPLAY_RECORDS",
        "phase": "PHASE_20_REINFORCEMENT_LEARNING",
        "research_only": True,
        "advisory_only": True,
        "shadow_mode": True,
        "memory_path": str(memory_path).replace("\\", "/"),
        "report_path": str(report_path).replace("\\", "/"),
        "records_processed": memory.get("records_processed"),
        "policy_stability": memory.get("policy_stability"),
        "safety": memory.get("safety"),
    }
    memory["runtime_status"] = status

    if write_files:
        _write_json(memory_path, memory)
        write_reinforcement_learning_report(memory, report_path)
        _write_json(status_path, status)

    return memory


def check_policy_stability(memory: Any = None) -> Dict[str, Any]:
    memory = _as_dict(memory)
    items = []
    if isinstance(memory.get("regime_memory"), dict):
        items.extend(memory.get("regime_memory").values())
    else:
        items.extend(value for value in memory.values() if isinstance(value, dict))

    if not items:
        return {
            "stable": False,
            "stability_score": 50.0,
            "sample_size": 0,
            "reward_variance": 0.0,
            "state": "INSUFFICIENT_MEMORY",
        }

    rewards = [safe_float(_as_dict(item).get("avg_reward"), 0.0) for item in items]
    sample_size = sum(int(safe_float(_as_dict(item).get("trades"), 0.0)) for item in items)
    mean = sum(rewards) / max(1, len(rewards))
    variance = sum((reward - mean) ** 2 for reward in rewards) / max(1, len(rewards))
    stability_score = clamp(100.0 - min(70.0, variance * 0.25) + min(15.0, sample_size * 0.4), 0.0, 100.0)

    return {
        "stable": bool(stability_score >= 65.0 and sample_size >= 10),
        "stability_score": round(stability_score, 2),
        "sample_size": sample_size,
        "reward_variance": round(variance, 4),
        "state": "STABLE" if stability_score >= 65.0 and sample_size >= 10 else "UNSTABLE_OR_EARLY",
    }


def build_reinforcement_learning_report(trade: Any, outcome: Any, context: Any = None, memory: Any = None) -> Dict[str, Any]:
    trade = _as_dict(trade)
    context = _as_dict(context)
    memory = _as_dict(memory)
    performance_data = context.get("performance_data") if isinstance(context.get("performance_data"), dict) else context

    outcome_label = _outcome_text(outcome)
    base_reward = calculate_trade_reward(trade, outcome, context)
    risk_adjusted = calculate_risk_adjusted_reward(trade, outcome, context)
    drawdown_penalty = calculate_drawdown_penalty(performance_data)
    false_confidence = calculate_false_confidence_penalty(trade, outcome)
    delayed = calculate_delayed_reward(trade, outcome, context)
    strategy_reward = calculate_strategy_reward(trade, outcome, context)
    regime_key = build_regime_reward_key(trade, context)
    policy_stability = check_policy_stability(memory)
    memory_priority = prioritize_reinforcement_memory(memory.get("regime_memory") or memory)
    exploration_score = calculate_exploration_exploitation_score(memory, context)

    final_score = clamp(
        (risk_adjusted * 0.45)
        + (strategy_reward * 0.25)
        + (drawdown_penalty * 0.12)
        + (false_confidence * 0.12)
        + (delayed * 0.06),
        -100.0,
        100.0,
    )

    if final_score >= 15.0:
        action = "REWARD"
    elif final_score <= -15.0:
        action = "PENALIZE"
    else:
        action = "OBSERVE"

    explanations = []
    if outcome_label == "WIN":
        explanations.append("Winning outcome generated positive base reward.")
    elif outcome_label == "LOSS":
        explanations.append("Losing outcome generated negative base reward.")
    else:
        explanations.append("Outcome is not closed; learning action remains observational.")
    if false_confidence < 0:
        explanations.append("High-confidence loss triggered a false-confidence penalty.")
    if drawdown_penalty < 0:
        explanations.append("Current drawdown conditions reduced the reinforcement score.")
    if _rr(trade) >= 2.0 and outcome_label == "WIN":
        explanations.append("Good RR win received additional reward.")
    if not policy_stability.get("stable"):
        explanations.append("Policy stability is still early or unstable; no live policy change should be made.")

    return {
        "symbol": _symbol(trade),
        "outcome": outcome_label,
        "base_reward": round(base_reward, 2),
        "risk_adjusted_reward": round(risk_adjusted, 2),
        "drawdown_penalty": round(drawdown_penalty, 2),
        "false_confidence_penalty": round(false_confidence, 2),
        "delayed_reward": round(delayed, 2),
        "final_reinforcement_score": round(final_score, 2),
        "regime_reward_key": regime_key,
        "strategy_reward": round(strategy_reward, 2),
        "memory_priority": memory_priority,
        "exploration_exploitation_score": exploration_score,
        "policy_stability": policy_stability,
        "learning_action": action,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_winning_trade = {
        "symbol": "TCS",
        "sector": "IT",
        "side": "LONG",
        "strategy_family": "Breakout",
        "rr": 2.6,
        "risk_amount": 1000,
        "confidence": "HIGH",
        "final_portfolio_rank": 86,
        "elite_confluence_score": 84,
        "elite_uniqueness_score": 72,
        "portfolio_heat_score": 24,
    }
    sample_losing_trade = {
        "symbol": "ICICIBANK",
        "sector": "Banking",
        "side": "LONG",
        "strategy_family": "Momentum",
        "rr": 1.7,
        "risk_amount": 1200,
        "confidence": "HIGH",
        "final_portfolio_rank": 82,
        "elite_confluence_score": 61,
        "elite_uniqueness_score": 45,
        "portfolio_heat_score": 78,
    }
    sample_context = {
        "market_regime": "RISK_ON",
        "performance_data": {
            "drawdown_pct": 2.1,
            "loss_streak": 1,
            "daily_loss_pct": 0.5,
        },
        "uncertainty_score": 42,
        "expected_holding_hours": 6,
    }
    sample_memory = {
        "total_trades": 18,
        "regime_memory": {
            "RISK_ON|LONG|BREAKOUT|IT": {"trades": 8, "wins": 6, "losses": 2, "avg_reward": 22.5, "recency_score": 70},
            "RISK_ON|LONG|MOMENTUM|BANKING": {"trades": 10, "wins": 4, "losses": 6, "avg_reward": -8.4, "recency_score": 55},
        },
    }
    reports = [
        build_reinforcement_learning_report(
            sample_winning_trade,
            {"outcome": "TARGET_HIT", "pnl": 2600, "holding_hours": 4},
            sample_context,
            sample_memory,
        ),
        build_reinforcement_learning_report(
            sample_losing_trade,
            {"outcome": "SL_HIT", "pnl": -1200, "holding_hours": 14},
            sample_context,
            sample_memory,
        ),
    ]
    print(json.dumps(reports, indent=2, sort_keys=True))
