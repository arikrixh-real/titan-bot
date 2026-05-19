from collections import defaultdict
from pathlib import Path

from consciousness_core.experience_utils import (
    is_loss,
    is_win,
    load_standard_reports,
    load_trade_rows,
    parse_float,
    setup_from_row,
    symbol_from_row,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "experience_clusters.json"
CLUSTERS = (
    "false_breakout",
    "trend_continuation",
    "liquidity_trap",
    "gap_trap",
    "news_reversal",
    "sector_divergence",
    "confidence_failure",
    "no_trade_warning",
    "insufficient_validation",
)


def _cluster_for_row(row):
    text = " ".join(str(row.get(key, "")) for key in ("confirmations", "reason", "result_reason")).lower()
    if "breakout" in text and is_loss(row):
        return "false_breakout"
    if "gap" in text:
        return "gap_trap"
    if "liquidity" in text or "spread" in text:
        return "liquidity_trap"
    if "sector" in text and ("weak" in text or "diverg" in text):
        return "sector_divergence"
    if is_loss(row) and parse_float(row.get("score") or row.get("rank_score")) >= 3.0:
        return "confidence_failure"
    if setup_from_row(row) == "trend_continuation" and is_win(row):
        return "trend_continuation"
    return None


def run_experience_clustering(output_path=OUTPUT_PATH, **_kwargs):
    rows = load_trade_rows()
    reports = load_standard_reports()
    clusters = {
        name: {"cluster": name, "count": 0, "wins": 0, "losses": 0, "symbols": defaultdict(int), "evidence": []}
        for name in CLUSTERS
    }
    for row in rows:
        cluster_name = _cluster_for_row(row)
        if not cluster_name:
            continue
        cluster = clusters[cluster_name]
        cluster["count"] += 1
        cluster["wins"] += 1 if is_win(row) else 0
        cluster["losses"] += 1 if is_loss(row) else 0
        cluster["symbols"][symbol_from_row(row)] += 1
        if len(cluster["evidence"]) < 10:
            cluster["evidence"].append(
                {
                    "symbol": symbol_from_row(row),
                    "outcome": row.get("outcome"),
                    "reason": row.get("result_reason") or row.get("reason"),
                }
            )

    if reports.get("news", {}).get("news_warning") == "REVIEW":
        clusters["news_reversal"]["count"] += 1
        clusters["news_reversal"]["evidence"].append({"source": "news_report", "warning": "REVIEW"})
    if reports.get("no_trade", {}).get("no_trade_warning") not in (None, "NONE"):
        clusters["no_trade_warning"]["count"] += 1
        clusters["no_trade_warning"]["evidence"].append({"source": "no_trade_report", "warning": reports["no_trade"].get("no_trade_warning")})
    if "no_data" in str(reports.get("backtesting", {})).lower() or "sample_size': 0" in str(reports.get("backtesting", {})).lower():
        clusters["insufficient_validation"]["count"] += 1
        clusters["insufficient_validation"]["evidence"].append({"source": "backtesting_report", "warning": "insufficient validation sample"})

    output_clusters = []
    for cluster in clusters.values():
        symbols = sorted(cluster["symbols"].items(), key=lambda item: item[1], reverse=True)
        output_clusters.append(
            {
                "cluster": cluster["cluster"],
                "count": cluster["count"],
                "wins": cluster["wins"],
                "losses": cluster["losses"],
                "common_symbols": [{"symbol": symbol, "count": count} for symbol, count in symbols[:5]],
                "evidence": cluster["evidence"],
            }
        )

    result = {"generated_at": now_ist(), "clusters": output_clusters}
    atomic_write_json(output_path, result)
    return result


if __name__ == "__main__":
    run_experience_clustering()
