from datetime import datetime, timedelta
from collections import Counter, defaultdict

from titan_brain.supabase_client import supabase
from titan_brain.db import insert_learning, insert_strategy_weights


LOOKBACK_DAYS = 30
MIN_CONFIDENCE_TRADES = 20


def fetch_table(table_name, limit=1000):
    try:
        result = (
            supabase
            .table(table_name)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[EVOLUTION FETCH ERROR - {table_name}] {e}")
        return []


def avg(values):
    values = [v for v in values if v is not None]
    if not values:
        return 0
    return sum(values) / len(values)


def analyze_scan_symbols(scan_symbols):
    if not scan_symbols:
        return {}

    top_symbols = sorted(
        scan_symbols,
        key=lambda x: x.get("final_score") or 0,
        reverse=True
    )[:10]

    fail_reasons = Counter(
        row.get("reason", "UNKNOWN")
        for row in scan_symbols
    )

    passed = [s for s in scan_symbols if s.get("passed") is True]

    return {
        "top_symbols": [
            {
                "symbol": s.get("symbol"),
                "final_score": s.get("final_score"),
                "trend": s.get("trend")
            }
            for s in top_symbols
        ],
        "common_fail_reasons": dict(fail_reasons.most_common(10)),
        "passed_count": len(passed),
        "total_scanned": len(scan_symbols)
    }


def analyze_news(news_items):
    if not news_items:
        return {}

    sentiment_counter = Counter(
        n.get("sentiment", "NEUTRAL")
        for n in news_items
    )

    impact_counter = Counter(
        n.get("impact_type", "UNKNOWN")
        for n in news_items
    )

    important_news = [
        n for n in news_items
        if (n.get("importance") or 0) >= 70
    ]

    return {
        "sentiment_distribution": dict(sentiment_counter),
        "impact_distribution": dict(impact_counter),
        "high_importance_count": len(important_news),
        "top_important_news": [
            {
                "symbol": n.get("symbol"),
                "headline": n.get("headline"),
                "sentiment": n.get("sentiment"),
                "importance": n.get("importance")
            }
            for n in important_news[:10]
        ]
    }


def analyze_market_conditions(market_rows):
    if not market_rows:
        return {}

    direction_counter = Counter(
        m.get("direction", "UNKNOWN")
        for m in market_rows
    )

    regime_counter = Counter(
        m.get("regime", "UNKNOWN")
        for m in market_rows
    )

    volatility_counter = Counter(
        m.get("volatility", "UNKNOWN")
        for m in market_rows
    )

    return {
        "direction_distribution": dict(direction_counter),
        "regime_distribution": dict(regime_counter),
        "volatility_distribution": dict(volatility_counter)
    }


def analyze_trade_results(trades, results):
    if not trades or not results:
        return {
            "message": "Not enough trade data yet"
        }

    trade_map = {t.get("trade_id"): t for t in trades}
    merged = []

    for r in results:
        trade = trade_map.get(r.get("trade_id"))
        if trade:
            merged.append({
                "trade": trade,
                "result": r
            })

    if not merged:
        return {
            "message": "No matched trade/result pairs"
        }

    wins = [m for m in merged if m["result"].get("result") == "WIN"]
    losses = [m for m in merged if m["result"].get("result") == "LOSS"]

    total = len(merged)
    win_rate = (len(wins) / total) * 100 if total else 0

    score_keys = [
        "volume_score",
        "strength_score",
        "compression_score",
        "final_score"
    ]

    score_learning = {}

    for key in score_keys:
        win_vals = [
            m["trade"].get("scores", {}).get(key)
            for m in wins
            if m["trade"].get("scores", {}).get(key) is not None
        ]

        loss_vals = [
            m["trade"].get("scores", {}).get(key)
            for m in losses
            if m["trade"].get("scores", {}).get(key) is not None
        ]

        score_learning[key] = {
            "win_avg": round(avg(win_vals), 2),
            "loss_avg": round(avg(loss_vals), 2),
            "edge": round(avg(win_vals) - avg(loss_vals), 2)
        }

    return {
        "total_closed_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "score_learning": score_learning
    }


def create_evolution_insight(scan_analysis, news_analysis, market_analysis, trade_analysis):
    insights = []

    if scan_analysis:
        fail_reasons = scan_analysis.get("common_fail_reasons", {})
        if fail_reasons:
            top_fail = max(fail_reasons, key=fail_reasons.get)
            insights.append(f"Most common rejection reason is {top_fail}.")

        passed_count = scan_analysis.get("passed_count", 0)
        total_scanned = scan_analysis.get("total_scanned", 0)

        if total_scanned:
            pass_rate = (passed_count / total_scanned) * 100
            insights.append(f"Current scan pass rate is {round(pass_rate, 2)}%.")

    if news_analysis:
        sentiment = news_analysis.get("sentiment_distribution", {})
        if sentiment:
            dominant_sentiment = max(sentiment, key=sentiment.get)
            insights.append(f"Dominant news sentiment is {dominant_sentiment}.")

    if market_analysis:
        direction = market_analysis.get("direction_distribution", {})
        if direction:
            dominant_direction = max(direction, key=direction.get)
            insights.append(f"Dominant market direction memory is {dominant_direction}.")

    if trade_analysis and "win_rate" in trade_analysis:
        insights.append(
            f"Closed trade win rate is {trade_analysis.get('win_rate')}%."
        )

    if not insights:
        insights.append("TITAN is still collecting data. No strong evolution insight yet.")

    return insights


def generate_strategy_weights_from_trade_analysis(trade_analysis):
    if not trade_analysis or "score_learning" not in trade_analysis:
        return None

    total_trades = trade_analysis.get("total_closed_trades", 0)

    if total_trades < 2:
        return None

    score_learning = trade_analysis["score_learning"]

    def safe_weight(edge):
        base = 1.0 + (edge / 10)

        if base < 0.5:
            return 0.5

        if base > 2.0:
            return 2.0

        return round(base, 2)

    return {
        "version": f"evo_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "volume_weight": safe_weight(score_learning.get("volume_score", {}).get("edge", 0)),
        "strength_weight": safe_weight(score_learning.get("strength_score", {}).get("edge", 0)),
        "compression_weight": safe_weight(score_learning.get("compression_score", {}).get("edge", 0)),
        "structure_weight": 1.0,
        "momentum_weight": 1.0,
        "relative_strength_weight": 1.0,
        "market_regime_weight": 1.0,
        "notes": "Auto-generated by TITAN Evolution Engine",
        "active": True
    }


def run_evolution_engine():
    print("🧬 TITAN Evolution Engine Started")

    scan_symbols = fetch_table("scan_symbols", limit=1000)
    news_items = fetch_table("news_memory", limit=500)
    market_rows = fetch_table("market_conditions", limit=300)
    trades = fetch_table("trades", limit=500)
    results = fetch_table("trade_results", limit=500)

    scan_analysis = analyze_scan_symbols(scan_symbols)
    news_analysis = analyze_news(news_items)
    market_analysis = analyze_market_conditions(market_rows)
    trade_analysis = analyze_trade_results(trades, results)

    insights = create_evolution_insight(
        scan_analysis=scan_analysis,
        news_analysis=news_analysis,
        market_analysis=market_analysis,
        trade_analysis=trade_analysis
    )

    evidence = {
        "scan_analysis": scan_analysis,
        "news_analysis": news_analysis,
        "market_analysis": market_analysis,
        "trade_analysis": trade_analysis,
        "insights": insights
    }

    confidence = 0.2

    if trade_analysis and trade_analysis.get("total_closed_trades"):
        confidence = min(trade_analysis.get("total_closed_trades") / MIN_CONFIDENCE_TRADES, 1)

    insert_learning({
        "learning_type": "EVOLUTION_ANALYSIS",
        "symbol": "ALL",
        "insight": " | ".join(insights),
        "confidence": confidence,
        "evidence": evidence,
        "action_taken": "Stored evolution insight and optional strategy weights",
        "active": True
    })

    weights = generate_strategy_weights_from_trade_analysis(trade_analysis)

    if weights:
        insert_strategy_weights(weights)
        print("✅ Evolution weights stored.")
    else:
        print("ℹ️ Not enough closed trade data for evolution weights yet.")

    print("✅ TITAN evolution analysis completed.")

    return {
        "insights": insights,
        "weights": weights,
        "confidence": confidence
    }