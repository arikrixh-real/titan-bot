"""
Consolidate imported historical experience records into memory reports.

Safety contract:
- Reads only historical replay JSONL records.
- Does not touch live runtime, Telegram, broker, Supabase, or order paths.
- Normal writes go only through engines.memory_consolidation_engine.
- --dry-run disables memory_consolidation_engine file writes and prints summary only.

Safe test command:
python research/consolidate_historical_experience.py --dry-run --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engines import memory_consolidation_engine


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "experience_vault"
    / "imported_trade_logs"
    / "historical_experience_import.jsonl"
)

CONTEXT = {
    "market_regime": "HISTORICAL_REPLAY",
    "trading_mode": "RESEARCH_ONLY",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def read_jsonl_records(path: Path, limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    skipped = 0

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(parsed, dict):
                skipped += 1
                continue

            parsed.setdefault("_source_line", line_number)
            records.append(parsed)
            if limit is not None and len(records) >= limit:
                break

    return records, skipped


def build_memory_data(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(
        lambda: {
            "scores": [],
            "rr_values": [],
            "wins": 0,
            "losses": 0,
            "outcomes": defaultdict(int),
        }
    )

    for record in records:
        setup_type = str(record.get("setup_type") or "UNKNOWN").strip() or "UNKNOWN"
        symbol = str(record.get("symbol") or "UNKNOWN").strip() or "UNKNOWN"
        trend = str(record.get("trend") or "UNKNOWN").strip() or "UNKNOWN"
        outcome = str(record.get("outcome") or "UNKNOWN").strip().upper() or "UNKNOWN"
        score = safe_float(record.get("score"))
        rr = safe_float(record.get("rr"))

        bucket = grouped[(setup_type, symbol, trend)]
        bucket["scores"].append(score)
        bucket["rr_values"].append(rr)
        bucket["outcomes"][outcome] += 1
        if outcome == "WIN":
            bucket["wins"] += 1
        elif outcome == "LOSS":
            bucket["losses"] += 1

    memory_data: List[Dict[str, Any]] = []
    for index, ((setup_type, symbol, trend), bucket) in enumerate(sorted(grouped.items()), start=1):
        sample_count = len(bucket["scores"])
        avg_score = sum(bucket["scores"]) / sample_count if sample_count else 0.0
        avg_rr = sum(bucket["rr_values"]) / sample_count if sample_count else 0.0
        win_rate = (bucket["wins"] / sample_count) * 100.0 if sample_count else 0.0

        memory_data.append(
            {
                "id": f"historical_replay_{index}",
                "memory_key": f"{setup_type}:{symbol}:{trend}",
                "pattern": setup_type,
                "setup_type": setup_type,
                "symbol": symbol,
                "trend": trend,
                "regime": trend,
                "score": round(avg_score, 2),
                "rr": round(avg_rr, 3),
                "result": "WIN" if bucket["wins"] >= bucket["losses"] else "LOSS",
                "sample_count": sample_count,
                "win_rate": round(win_rate, 2),
                "outcomes": dict(bucket["outcomes"]),
                "source_type": "HISTORICAL_REPLAY",
                "trading_mode": "RESEARCH_ONLY",
            }
        )

    return memory_data


def print_summary(
    report: Dict[str, Any],
    records: List[Dict[str, Any]],
    memory_data: List[Dict[str, Any]],
    skipped: int,
    dry_run: bool,
) -> None:
    outcomes: Dict[str, int] = defaultdict(int)
    for record in records:
        outcomes[str(record.get("outcome") or "UNKNOWN").upper()] += 1

    print("Historical memory consolidation summary")
    print(f"dry_run: {dry_run}")
    print(f"input_path: {INPUT_PATH}")
    print(f"records_loaded: {len(records)}")
    print(f"records_skipped: {skipped}")
    print(f"memory_summaries: {len(memory_data)}")
    print(f"context: {json.dumps(CONTEXT, sort_keys=True)}")
    print(f"outcomes: {json.dumps(dict(sorted(outcomes.items())), sort_keys=True)}")
    print(f"memory_data_mode: {report.get('memory_data_mode')}")
    print(f"memory_quality_score: {report.get('memory_quality_score')}")
    print(f"memory_bias: {report.get('memory_bias')}")
    print(f"memory_warning: {report.get('memory_warning')}")
    print(f"live_order_allowed: {report.get('live_order_allowed')}")
    if dry_run:
        print("output_files_written: false")
    else:
        print("output_files_written: true")
        print(f"report_path: {memory_consolidation_engine.REPORT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consolidate historical replay experience records.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum JSONL records to load.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing memory consolidation output files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer")
    if not INPUT_PATH.exists():
        raise SystemExit(f"Input JSONL not found: {INPUT_PATH}")

    records, skipped = read_jsonl_records(INPUT_PATH, args.limit)
    memory_data = build_memory_data(records)

    original_write_json = memory_consolidation_engine._write_json
    if args.dry_run:
        memory_consolidation_engine._write_json = lambda _path, _payload: None

    try:
        report = memory_consolidation_engine.build_memory_consolidation_report(
            memory_data=memory_data,
            trade_history=records,
            context=CONTEXT,
        )
    finally:
        memory_consolidation_engine._write_json = original_write_json

    print_summary(report, records, memory_data, skipped, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
