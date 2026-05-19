import json
from pathlib import Path

from engines.evolution_engine import run_evolution_engine as run_local_evolution_engine
from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


EVOLUTION_ENGINE_STATUS_PATH = Path("data") / "runtime" / "evolution_engine_status.json"


def run_evolution_engine():
    now_ist = as_ist_datetime()
    print("[RuntimeEvolution] START")

    result_summary = None
    error_type = None
    error_message = None

    try:
        result = run_local_evolution_engine()
        if isinstance(result, dict):
            result_summary = {
                "total_closed_trades": result.get("total_closed_trades"),
                "total_wins": result.get("total_wins"),
                "total_losses": result.get("total_losses"),
                "win_rate": result.get("win_rate"),
                "score_boost": result.get("score_boost"),
                "filter_strictness": result.get("filter_strictness"),
                "ranking_confidence": result.get("ranking_confidence"),
            }
        status = "EVOLUTION_ENGINE_REAL_RUN_COMPLETE"
        print("[RuntimeEvolution] SUCCESS")
    except Exception as exc:
        status = "EVOLUTION_ENGINE_REAL_RUN_ERROR"
        error_type = type(exc).__name__
        error_message = str(exc)
        print("[RuntimeEvolution] ERROR")

    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": status,
        "real_evolution": True,
        "engine": "engines.evolution_engine.run_evolution_engine",
        "result_summary": result_summary,
        "error_type": error_type,
        "error_message": error_message,
    }

    EVOLUTION_ENGINE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVOLUTION_ENGINE_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
