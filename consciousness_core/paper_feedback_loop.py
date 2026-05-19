from consciousness_core.experience_utils import is_loss, is_win, load_json, load_trade_rows, parse_float
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "paper_feedback.json"


def _paper_processed_stats(rows):
    wins = 0
    losses = 0
    for row in rows if isinstance(rows, list) else []:
        text = str(row).upper()
        if "|TP|" in text or text.endswith("|TP"):
            wins += 1
        if "|SL|" in text or text.endswith("|SL"):
            losses += 1
    total = wins + losses
    return {
        "source": "paper_processed_results",
        "sample_size": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "total_pnl": 0.0,
    }


def _trade_stats(rows):
    wins = sum(1 for row in rows if is_win(row))
    losses = sum(1 for row in rows if is_loss(row))
    total_pnl = sum(parse_float(row.get("realized_pnl") or row.get("pnl_points")) for row in rows)
    total = wins + losses
    return {
        "source": "trade_outcomes",
        "sample_size": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "total_pnl": round(total_pnl, 2),
    }


def _closed_position_stats(positions):
    rows = positions if isinstance(positions, list) else []
    wins = 0
    losses = 0
    pnl = 0.0
    for position in rows:
        if not isinstance(position, dict):
            continue
        value = parse_float(position.get("realized_pnl") or position.get("pnl") or position.get("profit_loss"))
        pnl += value
        if value > 0:
            wins += 1
        if value < 0:
            losses += 1
    total = wins + losses
    return {
        "source": "paper_closed_positions",
        "sample_size": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "total_pnl": round(pnl, 2),
    }


def _backtest_stats(backtest):
    candidates = []
    if isinstance(backtest, dict):
        for key in ("historical_backtest", "out_of_sample_validation"):
            value = backtest.get(key, {})
            if isinstance(value, dict):
                candidates.append(value.get("test", value))
        walk_forward = backtest.get("walk_forward_test", {})
        if isinstance(walk_forward, dict):
            candidates.extend(item for item in walk_forward.get("windows", []) if isinstance(item, dict))
    sample = sum(int(item.get("sample_size") or 0) for item in candidates)
    wins = sum(int(item.get("wins") or 0) for item in candidates)
    losses = sum(int(item.get("losses") or 0) for item in candidates)
    total_pnl = sum(parse_float(item.get("total_pnl")) for item in candidates)
    total = wins + losses
    return {
        "source": "backtesting_validation",
        "sample_size": sample or total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "total_pnl": round(total_pnl, 2),
    }


def _combine_stats(stats):
    sample_size = sum(item["sample_size"] for item in stats)
    wins = sum(item["wins"] for item in stats)
    losses = sum(item["losses"] for item in stats)
    pnl = sum(item["total_pnl"] for item in stats)
    total = wins + losses
    return {
        "sample_size": sample_size,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "loss_rate": round((losses / total) * 100, 2) if total else 0.0,
        "total_pnl": round(pnl, 2),
    }


def _feedback_for_experiment(experiment, aggregate_stats):
    success = experiment.get("success_condition", {})
    fail = experiment.get("fail_condition", {})
    sandbox = experiment.get("sandbox_snapshot", {})
    risk_score = parse_float(sandbox.get("risk_score"))
    required = int(success.get("minimum_sample_size") or experiment.get("required_sample_size") or 30)
    win_rate = aggregate_stats["win_rate"]
    loss_rate = aggregate_stats["loss_rate"]
    total_pnl = aggregate_stats["total_pnl"]
    sample_size = aggregate_stats["sample_size"]

    if risk_score > parse_float(fail.get("risk_score_above"), 0.35) or loss_rate >= parse_float(fail.get("maximum_loss_rate"), 55.0):
        outcome = "FAIL"
        decision = "REJECT"
    elif sample_size < required:
        outcome = "INSUFFICIENT_SAMPLE"
        decision = "CONTINUE_PAPER_TEST"
    elif win_rate >= parse_float(success.get("minimum_win_rate"), 52.0) and total_pnl >= parse_float(success.get("minimum_total_pnl"), 0.0):
        outcome = "PASS"
        decision = "PROMOTE_TO_HUMAN_REVIEW"
    elif total_pnl < 0:
        outcome = "FAIL"
        decision = "REJECT"
    else:
        outcome = "MIXED"
        decision = "CONTINUE_PAPER_TEST"

    confidence = clamp((sample_size / max(required, 1)) * 70 + max(win_rate - 50, 0), 0, 100)
    return {
        "experiment_id": experiment.get("experiment_id"),
        "proposal_id": experiment.get("proposal_id"),
        "target_engine": experiment.get("target_engine"),
        "outcome": outcome,
        "decision": decision,
        "confidence": round(confidence, 2),
        "required_sample_size": required,
        "observed_sample_size": sample_size,
        "observed_win_rate": win_rate,
        "observed_loss_rate": loss_rate,
        "observed_total_pnl": total_pnl,
        "risk_score": risk_score,
        "live_apply_allowed": False,
        "evidence_summary": aggregate_stats,
    }


def run_paper_feedback_loop(output_path=OUTPUT_PATH, **_kwargs):
    experiments_payload = load_json(CORE_DIR / "experiments.json", {})
    experiments = experiments_payload.get("experiments", []) if isinstance(experiments_payload, dict) else []
    paper_processed = load_json("data/paper_trading/paper_processed_results.json", [])
    paper_closed = load_json("data/paper_trading/paper_closed_positions.json", [])
    backtest = load_json("data/research/backtesting_validation_report.json", {})
    trade_rows = load_trade_rows()

    source_stats = [
        _paper_processed_stats(paper_processed),
        _closed_position_stats(paper_closed),
        _trade_stats(trade_rows),
        _backtest_stats(backtest),
    ]
    aggregate_stats = _combine_stats(source_stats)
    feedback = [
        _feedback_for_experiment(experiment, aggregate_stats)
        for experiment in experiments
        if isinstance(experiment, dict)
    ]
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "paper_feedback_only_no_live_execution",
        "source_stats": source_stats,
        "aggregate_stats": aggregate_stats,
        "feedback": feedback[-500:],
        "summary": {
            "feedback_count": len(feedback),
            "pass_count": sum(1 for item in feedback if item.get("outcome") == "PASS"),
            "fail_count": sum(1 for item in feedback if item.get("outcome") == "FAIL"),
            "uncertain_count": sum(1 for item in feedback if item.get("decision") == "CONTINUE_PAPER_TEST"),
            "live_apply_allowed": False,
        },
    }
    atomic_write_json(output_path, payload)
    return payload
