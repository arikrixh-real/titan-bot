"""
Build adaptive memory and evolution state from historical replay records only.

Safety contract:
- Reads only data/experience_vault/imported_trade_logs/historical_experience_import.jsonl
- Does not modify existing engines
- Does not touch live runtime, Telegram, broker, or Supabase
- Feeds synthetic closed trade rows into the existing adaptive/evolution engines
- Writes only to data/memory/ and reports/

Safe test command:
python research/build_historical_adaptive_memory.py --dry-run --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engines import adaptive_memory_builder, evolution_engine


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "experience_vault"
    / "imported_trade_logs"
    / "historical_experience_import.jsonl"
)
MEMORY_DIR = PROJECT_ROOT / "data" / "memory"
REPORTS_DIR = PROJECT_ROOT / "reports"
RESEARCH_REPORT_PATH = REPORTS_DIR / "historical_adaptive_memory_report.txt"

RESEARCH_CONTEXT = {
    "source_type": "HISTORICAL_REPLAY",
    "trading_mode": "RESEARCH_ONLY",
    "live_mutation": False,
    "telegram_mutation": False,
    "broker_mutation": False,
    "supabase_mutation": False,
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_symbol(value: Any) -> str:
    return str(value or "UNKNOWN").replace(".NS", "").strip().upper() or "UNKNOWN"


def normalize_side(value: Any) -> str:
    side = str(value or "").strip().upper()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side if side in {"LONG", "SHORT"} else "UNKNOWN"


def normalize_outcome(value: Any) -> Optional[str]:
    outcome = str(value or "").strip().upper()
    if outcome in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if outcome in {"LOSS", "LOST", "SL", "SL_HIT", "STOPLOSS", "STOP_LOSS", "FAILED"}:
        return "LOSS"
    return None


def read_replay_records(path: Path, limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    skipped = 0

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(record, dict):
                skipped += 1
                continue

            record["_source_line"] = line_number
            records.append(record)
            if limit is not None and len(records) >= limit:
                break

    return records, skipped


def build_trade_id(record: Dict[str, Any], index: int) -> str:
    existing = str(record.get("experience_hash") or "").strip()
    if existing:
        return f"historical_replay_{existing[:16]}"
    return f"historical_replay_line_{record.get('_source_line') or index}"


def synthetic_closed_trade_rows(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        outcome = normalize_outcome(record.get("outcome"))
        if outcome not in {"WIN", "LOSS"}:
            continue

        setup_type = str(record.get("setup_type") or "historical_replay").strip() or "historical_replay"
        trend = str(record.get("trend") or "HISTORICAL_REPLAY").strip() or "HISTORICAL_REPLAY"
        reason = str(record.get("reason") or record.get("outcome_reason") or setup_type).strip()
        confirmations = (
            f"setup_type={setup_type}; trend={trend}; "
            f"volume={record.get('volume_score')}; strength={record.get('strength_score')}; "
            f"compression={record.get('compression_score')}; source=historical_replay"
        )
        trade_id = build_trade_id(record, index)

        rows.append(
            {
                "trade_id": trade_id,
                "scan_id": trade_id,
                "symbol": normalize_symbol(record.get("symbol")),
                "side": normalize_side(record.get("side")),
                "entry": safe_float(record.get("entry")),
                "sl": safe_float(record.get("sl")),
                "target": safe_float(record.get("target")),
                "outcome": outcome,
                "result": outcome,
                "status": outcome,
                "rr": safe_float(record.get("rr")),
                "risk_reward": safe_float(record.get("rr")),
                "score": safe_float(record.get("score")),
                "final_score": safe_float(record.get("score")),
                "reason": reason,
                "setup_reason": reason,
                "confirmations": confirmations,
                "market_status": f"HISTORICAL_REPLAY_{trend.upper()}",
                "setup_type": setup_type,
                "signal_time": record.get("signal_time") or record.get("date") or "",
                "source_type": "HISTORICAL_REPLAY",
                "trading_mode": "RESEARCH_ONLY",
            }
        )

    return rows


@contextmanager
def temporary_attr(module: Any, name: str, value: Any) -> Iterator[None]:
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


@contextmanager
def patched_adaptive_inputs(rows: List[Dict[str, Any]]) -> Iterator[None]:
    def read_csv(path: Path) -> List[Dict[str, Any]]:
        if path == adaptive_memory_builder.TRADE_JOURNAL_CSV:
            return list(rows)
        return []

    def read_jsonl(path: Path) -> List[Dict[str, Any]]:
        if path == adaptive_memory_builder.TRADE_OUTCOMES_JSONL:
            return list(rows)
        return []

    with temporary_attr(adaptive_memory_builder, "_read_csv", read_csv):
        with temporary_attr(adaptive_memory_builder, "_read_jsonl", read_jsonl):
            with temporary_attr(
                adaptive_memory_builder,
                "_build_news_memory",
                lambda: {"seen_news_hashes": [], "symbol_sentiment": {}, "sector_sentiment": {}},
            ):
                yield


@contextmanager
def patched_evolution_inputs(rows: List[Dict[str, Any]], dry_run: bool) -> Iterator[None]:
    patches: List[Tuple[Any, str, Any]] = [
        (evolution_engine, "_closed_trades_from_journal", lambda: list(rows)),
    ]
    if dry_run:
        patches.extend(
            [
                (evolution_engine, "_save_json", lambda _path, _data: None),
                (evolution_engine, "_write_evolution_report", lambda _state, _old_state: None),
            ]
        )

    exits: List[Callable[[], None]] = []
    try:
        for module, name, value in patches:
            original = getattr(module, name)
            setattr(module, name, value)
            exits.append(lambda module=module, name=name, original=original: setattr(module, name, original))
        yield
    finally:
        for restore in reversed(exits):
            restore()


def top_bucket_names(memory: Dict[str, Any], limit: int = 10) -> List[Tuple[str, Dict[str, Any]]]:
    items = list(memory.items())
    items.sort(
        key=lambda item: (
            int(item[1].get("trades", 0)),
            float(item[1].get("win_rate", item[1].get("posterior_win_rate", 0.0))),
            float(item[1].get("weight", 1.0)),
        ),
        reverse=True,
    )
    return items[:limit]


def write_research_report(
    records_loaded: int,
    skipped_records: int,
    closed_rows: List[Dict[str, Any]],
    adaptive_state: Dict[str, Any],
    evolution_state: Dict[str, Any],
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    symbols = Counter(row["symbol"] for row in closed_rows)
    setup_types = Counter(row["setup_type"] for row in closed_rows)

    lines = [
        "TITAN HISTORICAL ADAPTIVE MEMORY BUILD REPORT",
        "=" * 60,
        f"Updated: {datetime.now(timezone.utc).isoformat()}",
        f"Input: {INPUT_PATH}",
        f"Records loaded: {records_loaded}",
        f"Records skipped: {skipped_records}",
        f"Synthetic closed trades: {len(closed_rows)}",
        f"Wins: {adaptive_state.get('total_wins')}",
        f"Losses: {adaptive_state.get('total_losses')}",
        f"Adaptive confidence: {adaptive_state.get('global_confidence', {}).get('adaptive_confidence_score')}",
        "",
        "EVOLUTION CONTROLS",
        "-" * 60,
        f"Score boost: {evolution_state.get('score_boost')}",
        f"Filter strictness: {evolution_state.get('filter_strictness')}",
        f"Ranking confidence: {evolution_state.get('ranking_confidence')}",
        "",
        "TOP LEARNED SETUP TAGS",
        "-" * 60,
    ]
    for tag, bucket in top_bucket_names(evolution_state.get("reason_memory", {}), 10):
        lines.append(
            f"{tag}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
            f"losses={bucket.get('losses')}, weight={bucket.get('weight')}"
        )

    lines.extend(["", "TOP SETUP TYPES", "-" * 60])
    for name, count in setup_types.most_common(10):
        lines.append(f"{name}: {count}")

    lines.extend(["", "TOP LEARNED SYMBOLS", "-" * 60])
    for symbol, bucket in top_bucket_names(evolution_state.get("symbol_memory", {}), 10):
        lines.append(
            f"{symbol}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
            f"losses={bucket.get('losses')}, weight={bucket.get('weight')}"
        )

    lines.extend(["", "TOP RAW SYMBOLS", "-" * 60])
    for symbol, count in symbols.most_common(10):
        lines.append(f"{symbol}: {count}")

    lines.extend(["", "SAFETY", "-" * 60, json.dumps(RESEARCH_CONTEXT, sort_keys=True)])
    RESEARCH_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def print_summary(
    records_loaded: int,
    skipped_records: int,
    closed_rows: List[Dict[str, Any]],
    adaptive_state: Dict[str, Any],
    evolution_state: Dict[str, Any],
    dry_run: bool,
) -> None:
    print("Historical adaptive memory build")
    print(f"dry_run: {dry_run}")
    print(f"input_path: {INPUT_PATH}")
    print(f"loaded_records: {records_loaded}")
    print(f"skipped_records: {skipped_records}")
    print(f"synthetic_closed_trades: {len(closed_rows)}")
    print(f"wins: {adaptive_state.get('total_wins')}")
    print(f"losses: {adaptive_state.get('total_losses')}")
    print(f"adaptive_confidence: {adaptive_state.get('global_confidence', {}).get('adaptive_confidence_score')}")
    print(
        "evolution_controls: "
        + json.dumps(
            {
                "score_boost": evolution_state.get("score_boost"),
                "filter_strictness": evolution_state.get("filter_strictness"),
                "ranking_confidence": evolution_state.get("ranking_confidence"),
            },
            sort_keys=True,
        )
    )
    print(
        "top_learned_setup_tags: "
        + json.dumps(
            {name: bucket for name, bucket in top_bucket_names(evolution_state.get("reason_memory", {}), 10)},
            sort_keys=True,
        )
    )
    print(
        "top_learned_symbols: "
        + json.dumps(
            {name: bucket for name, bucket in top_bucket_names(evolution_state.get("symbol_memory", {}), 10)},
            sort_keys=True,
        )
    )
    if dry_run:
        print("output_files_written: false")
    else:
        print("output_files_written: true")
        print(f"adaptive_state_path: {adaptive_memory_builder.ADAPTIVE_STATE_PATH}")
        print(f"adaptive_report_path: {adaptive_memory_builder.ADAPTIVE_REPORT_PATH}")
        print(f"evolution_state_path: {evolution_engine.EVOLUTION_STATE_PATH}")
        print(f"evolution_report_path: {evolution_engine.EVOLUTION_REPORT_PATH}")
        print(f"research_report_path: {RESEARCH_REPORT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build research-only adaptive/evolution memory from historical replay experience."
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum replay records to load.")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing output files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer")
    if not INPUT_PATH.exists():
        raise SystemExit(f"Input JSONL not found: {INPUT_PATH}")

    records, skipped = read_replay_records(INPUT_PATH, args.limit)
    closed_rows = synthetic_closed_trade_rows(records)

    with patched_adaptive_inputs(closed_rows):
        adaptive_state = adaptive_memory_builder.build_adaptive_memory(write_files=not args.dry_run)

    with patched_evolution_inputs(closed_rows, dry_run=args.dry_run):
        evolution_state = evolution_engine.run_evolution_engine()

    if not args.dry_run:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        write_research_report(
            records_loaded=len(records),
            skipped_records=skipped,
            closed_rows=closed_rows,
            adaptive_state=adaptive_state,
            evolution_state=evolution_state,
        )

    print_summary(
        records_loaded=len(records),
        skipped_records=skipped,
        closed_rows=closed_rows,
        adaptive_state=adaptive_state,
        evolution_state=evolution_state,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
