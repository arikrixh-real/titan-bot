from collections import Counter
from pathlib import Path

from consciousness_core.experience_utils import load_json, load_standard_reports, load_trade_rows, parse_market_status, regime_from_row
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "world_model_memory.json"


def run_world_model_memory(output_path=OUTPUT_PATH, **_kwargs):
    rows = load_trade_rows()
    reports = load_standard_reports()
    regimes = Counter(regime_from_row(row) for row in rows)
    volatility = Counter()
    liquidity = Counter()
    for row in rows:
        market = parse_market_status(row)
        volatility[market.get("volatility") or "UNKNOWN"] += 1
        for warning in market.get("warnings") or []:
            if "liquidity" in str(warning).lower() or "proxy" in str(warning).lower():
                liquidity[str(warning)] += 1

    real_memory = load_json(Path("data") / "consciousness_core" / "real_experience_memory.json", {})
    clusters = load_json(Path("data") / "consciousness_core" / "experience_clusters.json", {})
    directives = load_json(Path("data") / "consciousness_core" / "learning_directives.json", {})
    confidence = reports.get("confidence", {})
    no_trade = reports.get("no_trade", {})
    news = reports.get("news", {})

    result = {
        "generated_at": now_ist(),
        "regime_memory": {
            "observed_regimes": [{"regime": name, "count": count} for name, count in regimes.most_common(20)],
            "lessons": real_memory.get("regime_lessons", [])[:20],
        },
        "sector_memory": {
            "status": "INSUFFICIENT_DIRECT_SECTOR_EVIDENCE",
            "lesson": "sector divergence should remain a caution cluster until richer sector data exists",
        },
        "macro_memory": {
            "status": "READ_ONLY",
            "economic_calendar_seen": bool(Path("data/economic_calendar/latest_economic_calendar_report.json").exists()),
            "lesson": "macro context is informative only and must not alter live execution here",
        },
        "volatility_memory": [{"volatility": name, "count": count} for name, count in volatility.most_common(10)],
        "liquidity_memory": [{"signal": name, "count": count} for name, count in liquidity.most_common(10)],
        "strategy_memory": {
            "setup_archetypes": real_memory.get("setup_archetypes", [])[:20],
            "clusters": clusters.get("clusters", [])[:20],
        },
        "engine_memory": {
            "reliability": real_memory.get("engine_reliability_memory", []),
            "learning_directives": directives.get("directives", [])[:20],
            "confidence_warning": confidence.get("calibration_warning"),
            "no_trade_warning": no_trade.get("no_trade_warning"),
            "news_warning": news.get("news_warning"),
        },
        "market_laws": [
            "No live action should be promoted from proxy or zero-sample validation.",
            "Confidence must be treated as conditional on realized calibration evidence.",
            "No-trade and regime warnings should constrain aggression until contradicted by real outcomes.",
            "News memory is unreliable when headline count or memory confidence is low.",
        ],
    }
    atomic_write_json(output_path, result)
    return result


if __name__ == "__main__":
    run_world_model_memory()
