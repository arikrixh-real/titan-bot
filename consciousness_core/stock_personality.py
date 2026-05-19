from collections import Counter, defaultdict
from pathlib import Path

from consciousness_core.experience_utils import (
    is_loss,
    is_win,
    load_standard_reports,
    load_trade_rows,
    parse_float,
    regime_from_row,
    setup_from_row,
    symbol_from_row,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "stock_personality.json"


def run_stock_personality(output_path=OUTPUT_PATH, **_kwargs):
    rows = load_trade_rows()
    reports = load_standard_reports()
    news = reports.get("news", {})
    memory = defaultdict(
        lambda: {
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "scores": [],
            "rrs": [],
            "failure_reasons": Counter(),
            "success_reasons": Counter(),
            "regimes": Counter(),
        }
    )

    for row in rows:
        symbol = symbol_from_row(row)
        data = memory[symbol]
        data["trade_count"] += 1
        data["scores"].append(parse_float(row.get("score") or row.get("rank_score")))
        data["rrs"].append(parse_float(row.get("rr")))
        data["regimes"][regime_from_row(row)] += 1
        reason = row.get("result_reason") or setup_from_row(row)
        if is_win(row):
            data["win_count"] += 1
            data["success_reasons"][reason] += 1
        elif is_loss(row):
            data["loss_count"] += 1
            data["failure_reasons"][reason] += 1

    result = {"generated_at": now_ist(), "symbols": {}}
    for symbol, data in sorted(memory.items()):
        scored = [value for value in data["scores"] if value]
        rrs = [value for value in data["rrs"] if value]
        total_outcomes = data["win_count"] + data["loss_count"]
        win_rate = data["win_count"] / total_outcomes if total_outcomes else 0.0
        regime_count = len([regime for regime, count in data["regimes"].items() if regime != "UNKNOWN" and count])
        news_symbol = (news.get("symbol") or "").replace(".NS", "")
        news_sensitivity = "UNKNOWN"
        if news_symbol in {symbol, "UNKNOWN"}:
            news_sensitivity = "HIGH_UNCERTAINTY" if news.get("news_warning") == "REVIEW" else "NORMAL"
        result["symbols"][symbol] = {
            "trade_count": data["trade_count"],
            "win_count": data["win_count"],
            "loss_count": data["loss_count"],
            "avg_score": round(sum(scored) / len(scored), 2) if scored else 0.0,
            "avg_rr": round(sum(rrs) / len(rrs), 2) if rrs else 0.0,
            "common_failure_reason": data["failure_reasons"].most_common(1)[0][0] if data["failure_reasons"] else None,
            "common_success_reason": data["success_reasons"].most_common(1)[0][0] if data["success_reasons"] else None,
            "regime_sensitivity": "HIGH" if regime_count > 2 else "LOW" if regime_count else "UNKNOWN",
            "news_sensitivity": news_sensitivity,
            "reliability_score": round(max(0.0, min(100.0, (win_rate * 70.0) + min(total_outcomes, 10) * 3.0)), 2),
        }
    atomic_write_json(output_path, result)
    return result


if __name__ == "__main__":
    run_stock_personality()
