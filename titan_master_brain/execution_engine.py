"""
TITAN MASTER BRAIN - EXECUTION ENGINE
STEP 8C TELEGRAM LIVE

Purpose:
- Convert selected daily alert candidates into Telegram-ready packets.
- Print clean execution output.
- Send Telegram signals using existing alerts.telegram_alert.send_telegram_message().
- Does NOT place broker orders.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _extract_any(candidate, keys):
    """
    Safely extract value from candidate or candidate['raw'].
    """
    if not isinstance(candidate, dict):
        return None

    for key in keys:
        if candidate.get(key) is not None:
            return candidate.get(key)

    raw = candidate.get("raw", {})
    if isinstance(raw, dict):
        for key in keys:
            if raw.get(key) is not None:
                return raw.get(key)

    return None


def build_signal_message(data):
    return f"""
🚀 TITAN TRADE SIGNAL

📌 Stock: {data.get("symbol")}
📍 Side: {data.get("side")}

🎯 Entry: {data.get("entry")}
🛑 SL: {data.get("sl")}
🏁 Target: {data.get("target")}
⚖️ RR: {data.get("rr")}

🧠 Decision: {data.get("decision")}
🔥 Confidence: {data.get("confidence")}
⭐ Tier: {data.get("quality_tier")}
📊 Score: {data.get("score")}
🏆 Rank: {data.get("daily_alert_rank")}

⏰ Time: {datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")}

⚠️ Educational/analysis signal. Follow risk management.
""".strip()


def prepare_execution_packets(daily_alert_result):
    selected = daily_alert_result.get("selected_for_alert", []) or []
    packets = []

    for candidate in selected:
        if not isinstance(candidate, dict):
            continue

        data = {
            "symbol": _extract_any(candidate, ["symbol", "stock", "ticker"]),
            "side": _extract_any(candidate, ["side", "direction", "trade_side"]),
            "entry": _extract_any(candidate, ["entry", "entry_price"]),
            "sl": _extract_any(candidate, ["sl", "stop_loss", "stoploss"]),
            "target": _extract_any(candidate, ["target", "tp", "t1", "target1"]),
            "rr": _extract_any(candidate, ["rr", "risk_reward", "risk_reward_ratio"]),
            "score": _extract_any(candidate, ["score", "final_score", "rank_score"]),
            "decision": candidate.get("decision"),
            "confidence": candidate.get("confidence"),
            "quality_tier": candidate.get("quality_tier"),
            "daily_alert_rank": candidate.get("daily_alert_rank"),
            "daily_alert_key": candidate.get("daily_alert_key"),
            "raw": candidate,
        }

        data["message"] = build_signal_message(data)
        packets.append(data)

    return {
        "execution_mode": "READY_FOR_TELEGRAM" if packets else "NO_EXECUTION",
        "packets": packets,
        "count": len(packets),
    }


def print_execution_packets(result):
    print("\n" + "=" * 60)
    print("[EXECUTION ENGINE OUTPUT]")
    print("=" * 60)

    print(f"Packets prepared: {result.get('count', 0)}")

    packets = result.get("packets", []) or []

    if not packets:
        print("No execution packets.")
        return

    print("\nReady Signals:\n")

    for i, packet in enumerate(packets, 1):
        print(f"{i}. {packet.get('symbol')} | {packet.get('side')}")
        print(
            f"   Entry: {packet.get('entry')} | SL: {packet.get('sl')} | "
            f"Target: {packet.get('target')} | RR: {packet.get('rr')}"
        )
        print("-" * 40)


def send_telegram_signals(execution_result):
    """
    Sends Telegram messages for prepared packets.
    Uses your existing alerts.telegram_alert.send_telegram_message().

    Returns only successfully sent packets.
    """

    packets = execution_result.get("packets", []) or []

    if not packets:
        print("[Telegram] No signals to send.")
        return []

    sent_packets = []

    try:
        from alerts.telegram_alert import send_telegram_message
    except Exception as e:
        print(f"[Telegram ERROR] Could not import send_telegram_message: {e}")
        return []

    for packet in packets:
        try:
            message = packet.get("message")
            symbol = packet.get("symbol", "UNKNOWN")

            if not message:
                print(f"[Telegram ERROR] Empty message for {symbol}")
                continue

            send_telegram_message(message)
            print(f"[Telegram] Sent: {symbol}")
            sent_packets.append(packet)

        except Exception as e:
            print(f"[Telegram ERROR] {packet.get('symbol', 'UNKNOWN')} -> {e}")

    return sent_packets