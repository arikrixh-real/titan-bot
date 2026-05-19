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
    text_contains,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "real_experience_memory.json"


def _trade_patterns(rows):
    failures = Counter()
    successes = Counter()
    setups = defaultdict(lambda: {"wins": 0, "losses": 0, "symbols": Counter(), "avg_score": []})
    stocks = defaultdict(lambda: {"wins": 0, "losses": 0, "setups": Counter(), "regimes": Counter()})
    regimes = defaultdict(lambda: {"wins": 0, "losses": 0, "setups": Counter()})

    for row in rows:
        symbol = symbol_from_row(row)
        side = row.get("side") or "UNKNOWN"
        setup = setup_from_row(row)
        regime = regime_from_row(row)
        reason = row.get("result_reason") or row.get("reason") or setup
        key = f"{symbol}|{side}|{setup}|{regime}"
        score = parse_float(row.get("score") or row.get("rank_score"))

        setups[setup]["symbols"][symbol] += 1
        setups[setup]["avg_score"].append(score)
        stocks[symbol]["setups"][setup] += 1
        stocks[symbol]["regimes"][regime] += 1
        regimes[regime]["setups"][setup] += 1

        if is_win(row):
            successes[f"{key}|{reason}"] += 1
            setups[setup]["wins"] += 1
            stocks[symbol]["wins"] += 1
            regimes[regime]["wins"] += 1
        elif is_loss(row):
            failures[f"{key}|{reason}"] += 1
            setups[setup]["losses"] += 1
            stocks[symbol]["losses"] += 1
            regimes[regime]["losses"] += 1

    setup_archetypes = []
    for setup, data in sorted(setups.items()):
        samples = data["wins"] + data["losses"]
        scores = [score for score in data["avg_score"] if score]
        setup_archetypes.append(
            {
                "setup": setup,
                "samples": samples,
                "wins": data["wins"],
                "losses": data["losses"],
                "win_rate": round((data["wins"] / samples) * 100, 2) if samples else 0.0,
                "avg_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
                "common_symbols": [
                    {"symbol": symbol, "count": count}
                    for symbol, count in data["symbols"].most_common(5)
                ],
            }
        )

    stock_memory = [
        {
            "symbol": symbol,
            "wins": data["wins"],
            "losses": data["losses"],
            "common_setups": [
                {"setup": setup, "count": count}
                for setup, count in data["setups"].most_common(5)
            ],
            "common_regimes": [
                {"regime": regime, "count": count}
                for regime, count in data["regimes"].most_common(5)
            ],
        }
        for symbol, data in sorted(stocks.items())
    ]

    regime_lessons = [
        {
            "regime": regime,
            "wins": data["wins"],
            "losses": data["losses"],
            "lesson": "reduce aggression" if data["losses"] > data["wins"] else "conditions have supported winners",
            "common_setups": [
                {"setup": setup, "count": count}
                for setup, count in data["setups"].most_common(5)
            ],
        }
        for regime, data in sorted(regimes.items())
    ]

    return failures, successes, setup_archetypes, stock_memory[:100], regime_lessons


def _engine_reliability(reports):
    engines = []
    checks = {
        "backtesting": reports.get("backtesting", {}),
        "confidence_calibration": reports.get("confidence", {}),
        "no_trade_intelligence": reports.get("no_trade", {}),
        "news_intelligence": reports.get("news", {}),
        "worker_health": reports.get("worker_health", {}),
    }
    for engine, payload in checks.items():
        weak = text_contains(payload, ("no_data", "insufficient", "proxy", "review", "error", "failed", "missing"))
        ok = text_contains(payload, ("ok", "allow", "healthy", "available", "active"))
        engines.append(
            {
                "engine": engine,
                "reliability": "WEAK" if weak else "USABLE" if ok else "UNKNOWN",
                "evidence": "insufficient/proxy/error signals present" if weak else "positive status signals present" if ok else "no strong evidence",
            }
        )
    return engines


def run_real_experience_memory(output_path=OUTPUT_PATH, **_kwargs):
    rows = load_trade_rows()
    reports = load_standard_reports()
    failures, successes, setup_archetypes, stock_memory, regime_lessons = _trade_patterns(rows)
    confidence = reports.get("confidence", {})
    no_trade = reports.get("no_trade", {})
    news = reports.get("news", {})

    memory = {
        "generated_at": now_ist(),
        "source_trade_rows": len(rows),
        "repeated_failure_patterns": [
            {"pattern": pattern, "count": count}
            for pattern, count in failures.most_common(25)
        ],
        "repeated_success_patterns": [
            {"pattern": pattern, "count": count}
            for pattern, count in successes.most_common(25)
        ],
        "setup_archetypes": setup_archetypes,
        "stock_personality_memory": stock_memory,
        "regime_lessons": regime_lessons,
        "confidence_failure_patterns": [
            {
                "pattern": "weak_or_proxy_calibration",
                "sample_size": confidence.get("predicted_vs_actual", {}).get("sample_size", 0),
                "calibrated_confidence_score": confidence.get("calibrated_confidence_score"),
                "warning": confidence.get("calibration_warning"),
            }
        ],
        "no_trade_lessons": [
            {
                "warning": no_trade.get("no_trade_warning"),
                "permission": no_trade.get("trade_permission"),
                "score": no_trade.get("no_trade_score"),
                "lesson": "respect wait/review signals before increasing aggression",
            }
        ],
        "news_reaction_lessons": [
            {
                "event_classification": news.get("event_classification"),
                "news_warning": news.get("news_warning"),
                "memory_confidence": news.get("news_reaction_memory", {}).get("memory_confidence", 0.0),
                "lesson": "treat news reaction as uncertain when memory confidence is low",
            }
        ],
        "engine_reliability_memory": _engine_reliability(reports),
    }
    atomic_write_json(output_path, memory)
    return memory


if __name__ == "__main__":
    run_real_experience_memory()
