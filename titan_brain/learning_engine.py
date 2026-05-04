from datetime import datetime
from titan_brain.supabase_client import supabase
from titan_brain.db import insert_learning, insert_strategy_weights


def fetch_trade_results():
    try:
        result = supabase.table("trade_results").select("*").execute()
        return result.data or []
    except Exception as e:
        print(f"[LEARNING ERROR - TRADE RESULTS] {e}")
        return []


def fetch_trades():
    try:
        result = supabase.table("trades").select("*").execute()
        return result.data or []
    except Exception as e:
        print(f"[LEARNING ERROR - TRADES] {e}")
        return []


def merge_trades_with_results(trades, results):
    trade_map = {t.get("trade_id"): t for t in trades}
    merged = []

    for r in results:
        trade_id = r.get("trade_id")
        trade = trade_map.get(trade_id)

        if trade:
            merged.append({
                "trade": trade,
                "result": r
            })

    return merged


def calculate_score_learning(merged):
    wins = [m for m in merged if m["result"].get("result") == "WIN"]
    losses = [m for m in merged if m["result"].get("result") == "LOSS"]

    if not wins or not losses:
        return None

    score_keys = [
        "volume_score",
        "strength_score",
        "compression_score",
        "final_score"
    ]

    insights = {}

    for key in score_keys:
        win_values = []
        loss_values = []

        for w in wins:
            value = w["trade"].get("scores", {}).get(key)
            if value is not None:
                win_values.append(value)

        for l in losses:
            value = l["trade"].get("scores", {}).get(key)
            if value is not None:
                loss_values.append(value)

        if not win_values or not loss_values:
            continue

        win_avg = sum(win_values) / len(win_values)
        loss_avg = sum(loss_values) / len(loss_values)

        difference = win_avg - loss_avg

        insights[key] = {
            "win_avg": round(win_avg, 2),
            "loss_avg": round(loss_avg, 2),
            "difference": round(difference, 2)
        }

    return insights


def convert_insights_to_weights(insights):
    if not insights:
        return None

    return {
        "version": f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "volume_weight": insights.get("volume_score", {}).get("difference", 0),
        "strength_weight": insights.get("strength_score", {}).get("difference", 0),
        "compression_weight": insights.get("compression_score", {}).get("difference", 0),
        "structure_weight": 0,
        "momentum_weight": 0,
        "relative_strength_weight": 0,
        "market_regime_weight": 0,
        "notes": "Auto-generated from closed trade results",
        "active": True
    }


def store_learning(insights, weights, total_trades):
    insert_learning({
        "learning_type": "TRADE_RESULT_SCORE_ANALYSIS",
        "symbol": "ALL",
        "insight": "Compared winning trade scores against losing trade scores",
        "confidence": min(total_trades / 50, 1),
        "evidence": {
            "score_insights": insights,
            "weights": weights,
            "total_closed_trades": total_trades
        },
        "action_taken": "Stored updated strategy weight suggestion",
        "active": True
    })

    insert_strategy_weights(weights)


def run_learning_engine():
    print("🧠 TITAN Learning Engine Started")

    results = fetch_trade_results()
    trades = fetch_trades()

    if not results:
        print("No trade results available yet.")
        return None

    merged = merge_trades_with_results(trades, results)

    if len(merged) < 2:
        print("Not enough matched trade data for learning.")
        return None

    insights = calculate_score_learning(merged)

    if not insights:
        print("Need both WIN and LOSS trades for proper learning.")
        return None

    weights = convert_insights_to_weights(insights)

    if not weights:
        print("No useful weight update generated.")
        return None

    store_learning(
        insights=insights,
        weights=weights,
        total_trades=len(merged)
    )

    print("✅ TITAN learning completed.")
    print("📌 New strategy weights stored.")

    return {
        "insights": insights,
        "weights": weights
    }