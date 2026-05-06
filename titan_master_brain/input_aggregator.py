# TITAN MASTER BRAIN - INPUT AGGREGATOR (STEP 3B)
# Now includes setup normalizer integration

from datetime import datetime
import json
import os

from titan_master_brain.memory_reasoning_engine import analyze_memory
from titan_master_brain.setup_normalizer import normalize_setups


def _safe_market():
    try:
        from engines.market_filter import market_regime_status
        return {
            "status": "OK",
            "data": market_regime_status(),
            "error": None
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "data": {"market_ok": False, "reason": "market_filter_error"},
            "error": str(e)
        }


def _safe_setups():
    try:
        from engines.setup_engine import scan_for_setups

        raw = scan_for_setups()

        # 🔥 NEW: normalize everything safely
        setups = normalize_setups(raw)

        return {
            "status": "OK",
            "data": setups,
            "count": len(setups),
            "error": None
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "data": [],
            "count": 0,
            "error": str(e)
        }


def _safe_memory():
    possible_paths = [
        "data/journals/trade_outcomes.jsonl",
        "data/journals/trade_outcomes.json",
        "journal/trade_journal.json",
        "data/journals/trade_journal.jsonl",
    ]

    for path in possible_paths:
        try:
            if not os.path.exists(path):
                continue

            recent = []

            if path.endswith(".jsonl"):
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-30:]
                    for line in lines:
                        try:
                            recent.append(json.loads(line.strip()))
                        except:
                            pass

            elif path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    recent = data[-30:]
                elif isinstance(data, dict):
                    for key in ["trades", "outcomes", "records", "data"]:
                        if isinstance(data.get(key), list):
                            recent = data.get(key)[-30:]
                            break

            return {
                "status": "OK",
                "source": path,
                "recent": recent,
                "analysis": analyze_memory({"recent": recent}),
                "error": None
            }

        except Exception as e:
            return {
                "status": "ERROR",
                "source": path,
                "recent": [],
                "analysis": analyze_memory({"recent": []}),
                "error": str(e)
            }

    return {
        "status": "EMPTY",
        "source": None,
        "recent": [],
        "analysis": analyze_memory({"recent": []}),
        "error": "No memory file found"
    }


def build_master_input():
    market = _safe_market()
    setups = _safe_setups()
    memory = _safe_memory()

    print("[MasterBrain] Market:", market.get("data"))
    print("[MasterBrain] Setups:", setups.get("count"))
    print("[MasterBrain] Memory records:", memory.get("analysis", {}).get("total_records"))

    return {
        "timestamp": datetime.now().isoformat(),
        "market": market,
        "setups": setups,
        "memory": memory,
        "system_health": {
            "market_connection": market.get("status"),
            "setup_connection": setups.get("status"),
            "memory_connection": memory.get("status"),
            "normalizer_active": True
        }
    }