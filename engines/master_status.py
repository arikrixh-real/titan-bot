"""
TITAN - Master Intelligence Status Layer
---------------------------------------

Purpose:
- Creates one clean status snapshot for dashboard + automation monitoring.
- Reads evolution state safely.
- Reads journals safely.
- Shows Titan intelligence stage.
- Does NOT send Telegram alerts.
- Does NOT change Telegram cap.
- Does NOT affect trading logic.
- Does NOT break scan engine.

Output:
data/memory/titan_master_status.json
reports/titan_master_status.txt

Used by:
setup_engine.py
dashboard.py later
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
MEMORY_DIR = DATA_DIR / "memory"
REPORTS_DIR = PROJECT_ROOT / "reports"

TRADE_JOURNAL_PATH = DATA_DIR / "trade_journal.csv"
SCAN_JOURNAL_PATH = DATA_DIR / "scan_journal.csv"

MASTER_STATUS_JSON = MEMORY_DIR / "titan_master_status.json"
MASTER_STATUS_TXT = REPORTS_DIR / "titan_master_status.txt"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dirs() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text == "":
            return default
        return float(text)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text == "":
            return default
        return int(float(text))
    except Exception:
        return default


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
    except Exception:
        return []


def _outcome(row: Dict[str, Any]) -> str:
    for key in ["outcome", "result", "status", "trade_result", "Outcome", "Result", "STATUS"]:
        raw = str(row.get(key, "")).strip().upper()
        if not raw:
            continue

        if raw in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "T1", "T2", "PROFIT", "SUCCESS"}:
            return "WIN"

        if raw in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
            return "LOSS"

        if raw in {"OPEN", "ACTIVE", "PENDING", "RUNNING"}:
            return "OPEN"

    return "OPEN"


def _journal_stats() -> Dict[str, Any]:
    trade_rows = _read_csv_rows(TRADE_JOURNAL_PATH)
    scan_rows = _read_csv_rows(SCAN_JOURNAL_PATH)

    rows = trade_rows if trade_rows else scan_rows

    total = len(rows)
    wins = 0
    losses = 0
    open_trades = 0

    for row in rows:
        result = _outcome(row)
        if result == "WIN":
            wins += 1
        elif result == "LOSS":
            losses += 1
        else:
            open_trades += 1

    closed = wins + losses
    accuracy = round((wins / closed) * 100, 2) if closed else 0.0

    return {
        "total_journal_rows": total,
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "open_trades": open_trades,
        "accuracy_percent": accuracy,
        "trade_journal_exists": TRADE_JOURNAL_PATH.exists(),
        "scan_journal_exists": SCAN_JOURNAL_PATH.exists(),
    }


def _safe_evolution_state() -> Dict[str, Any]:
    try:
        from engines.evolution_engine import get_evolution_state

        return get_evolution_state()
    except Exception as e:
        return {
            "error": str(e),
            "total_closed_trades": 0,
            "win_rate": 0.0,
            "score_boost": 1.0,
            "filter_strictness": 1.0,
            "ranking_confidence": 1.0,
        }


def _intelligence_stage(closed_trades: int) -> Dict[str, Any]:
    if closed_trades < 10:
        return {
            "stage": "LEARNING_PHASE",
            "stage_percent": round((closed_trades / 10) * 100, 2),
            "description": "Collecting first outcomes. Evolution filter and adaptive scoring remain protected.",
        }

    if closed_trades < 30:
        return {
            "stage": "EARLY_EVOLUTION",
            "stage_percent": round(35 + ((closed_trades - 10) / 20) * 25, 2),
            "description": "Evolution, adaptive scoring, pattern intelligence, and filtering are active with low sample size.",
        }

    if closed_trades < 100:
        return {
            "stage": "ACTIVE_EVOLUTION",
            "stage_percent": round(60 + ((closed_trades - 30) / 70) * 25, 2),
            "description": "Titan has enough outcomes to improve ranking and filtering more confidently.",
        }

    return {
        "stage": "MATURE_SELF_LEARNING",
        "stage_percent": 100.0,
        "description": "Titan has mature outcome data and can strongly adapt scoring, ranking, and filtering.",
    }


def _engine_statuses(closed_trades: int) -> Dict[str, str]:
    learning_phase = closed_trades < 10

    return {
        "scan_engine": "ACTIVE",
        "journal_engine": "ACTIVE",
        "outcome_tracker": "ACTIVE",
        "learning_engine": "ACTIVE",
        "evolution_engine": "ACTIVE_WAITING_FOR_DATA" if learning_phase else "ACTIVE",
        "adaptive_scoring": "NEUTRAL_LEARNING_PHASE" if learning_phase else "ACTIVE",
        "pattern_intelligence": "NEUTRAL_LEARNING_PHASE" if learning_phase else "ACTIVE",
        "regime_intelligence": "ACTIVE",
        "elite_selection": "ACTIVE",
        "telegram_cap": "PROTECTED_3_PER_DAY",
        "dashboard_ready": "YES",
    }


def update_master_status(last_scan_summary: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Creates latest TITAN system status snapshot.

    Safe to call every scan.
    """

    _ensure_dirs()

    journal = _journal_stats()
    evolution = _safe_evolution_state()

    closed_trades = _safe_int(
        evolution.get("total_closed_trades", journal.get("closed_trades", 0)),
        0,
    )

    stage = _intelligence_stage(closed_trades)

    status = {
        "updated_at": _now(),
        "system_name": "TITAN",
        "system_flow": "Scan → Journal → Outcome → Learning → Evolution → Adaptive Scoring → Pattern Intelligence → Regime Intelligence → Elite Selection",
        "last_scan_summary": last_scan_summary or {},
        "journal": journal,
        "evolution": {
            "total_closed_trades": closed_trades,
            "total_wins": _safe_int(evolution.get("total_wins", journal.get("wins", 0))),
            "total_losses": _safe_int(evolution.get("total_losses", journal.get("losses", 0))),
            "win_rate_percent": round(_safe_float(evolution.get("win_rate", 0.0)) * 100, 2),
            "score_boost": _safe_float(evolution.get("score_boost", 1.0)),
            "filter_strictness": _safe_float(evolution.get("filter_strictness", 1.0)),
            "ranking_confidence": _safe_float(evolution.get("ranking_confidence", 1.0)),
            "last_updated": evolution.get("last_updated"),
            "notes": evolution.get("evolution_notes", []),
        },
        "intelligence_stage": stage,
        "engines": _engine_statuses(closed_trades),
        "next_activation": {
            "closed_trades_needed_for_active_evolution": max(0, 10 - closed_trades),
            "active_after_closed_trades": 10,
        },
    }

    with MASTER_STATUS_JSON.open("w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)

    _write_text_report(status)

    return status


def _write_text_report(status: Dict[str, Any]) -> None:
    lines = []

    lines.append("TITAN MASTER STATUS")
    lines.append("=" * 60)
    lines.append(f"Updated At: {status.get('updated_at')}")
    lines.append(f"Flow: {status.get('system_flow')}")
    lines.append("")

    stage = status.get("intelligence_stage", {})
    lines.append("INTELLIGENCE STAGE")
    lines.append("-" * 60)
    lines.append(f"Stage: {stage.get('stage')}")
    lines.append(f"Progress: {stage.get('stage_percent')}%")
    lines.append(f"Description: {stage.get('description')}")
    lines.append("")

    journal = status.get("journal", {})
    lines.append("TRADE / JOURNAL STATUS")
    lines.append("-" * 60)
    lines.append(f"Total journal rows: {journal.get('total_journal_rows')}")
    lines.append(f"Closed trades: {journal.get('closed_trades')}")
    lines.append(f"Wins: {journal.get('wins')}")
    lines.append(f"Losses: {journal.get('losses')}")
    lines.append(f"Open trades: {journal.get('open_trades')}")
    lines.append(f"Accuracy: {journal.get('accuracy_percent')}%")
    lines.append("")

    evolution = status.get("evolution", {})
    lines.append("EVOLUTION STATUS")
    lines.append("-" * 60)
    lines.append(f"Closed trades used: {evolution.get('total_closed_trades')}")
    lines.append(f"Win rate: {evolution.get('win_rate_percent')}%")
    lines.append(f"Score boost: {evolution.get('score_boost')}")
    lines.append(f"Filter strictness: {evolution.get('filter_strictness')}")
    lines.append(f"Ranking confidence: {evolution.get('ranking_confidence')}")
    lines.append("")

    lines.append("ENGINE STATUS")
    lines.append("-" * 60)
    for engine, value in status.get("engines", {}).items():
        lines.append(f"{engine}: {value}")

    lines.append("")
    next_activation = status.get("next_activation", {})
    lines.append("NEXT ACTIVATION")
    lines.append("-" * 60)
    lines.append(
        f"Closed trades needed for active evolution: "
        f"{next_activation.get('closed_trades_needed_for_active_evolution')}"
    )

    MASTER_STATUS_TXT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    result = update_master_status()
    print("✅ TITAN Master Status updated")
    print("Stage:", result.get("intelligence_stage", {}).get("stage"))
    print("Progress:", result.get("intelligence_stage", {}).get("stage_percent"), "%")
    print("JSON:", MASTER_STATUS_JSON)
    print("Report:", MASTER_STATUS_TXT)