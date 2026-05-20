import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path


IST = timezone(timedelta(hours=5, minutes=30))
DIAGNOSTICS_PATH = Path("data") / "runtime" / "signal_path_diagnostics.json"
HEATMAP_PATH = Path("data") / "runtime" / "rejection_heatmap.json"
MAX_SCAN_CYCLES = 100
MAX_SYMBOL_EXAMPLES = 8


def timestamp_ist():
    return datetime.now(IST).isoformat()


def today_ist():
    return datetime.now(IST).date().isoformat()


def safe_read_json(path, default):
    try:
        path = Path(path)
        if not path.exists():
            return default
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload is not None else default
    except Exception:
        return default


def atomic_write_json(path, payload):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        pass


def counter_dict(counter):
    if isinstance(counter, Counter):
        return dict(counter.most_common())
    if isinstance(counter, dict):
        return dict(Counter(counter).most_common())
    return {}


def examples_dict(examples):
    result = {}
    if not isinstance(examples, dict):
        return result
    for reason, symbols in examples.items():
        if isinstance(symbols, list):
            result[str(reason)] = [str(symbol) for symbol in symbols[:MAX_SYMBOL_EXAMPLES]]
    return result


def add_example(examples, reason, symbol):
    reason = str(reason or "UNKNOWN")
    if not symbol:
        return
    bucket = examples.setdefault(reason, [])
    if len(bucket) < MAX_SYMBOL_EXAMPLES and symbol not in bucket:
        bucket.append(str(symbol))


def stage_payload(input_candidates, passed, reasons, examples):
    input_candidates = int(input_candidates or 0)
    passed = int(passed or 0)
    failed = max(input_candidates - passed, 0)
    return {
        "input_candidates": input_candidates,
        "passed": passed,
        "failed": failed,
        "top_fail_reasons": counter_dict(reasons),
        "symbol_examples": examples_dict(examples),
    }


def build_scan_report(
    *,
    scan_cycle_id,
    stocks_checked,
    trend_passed,
    momentum_passed,
    structure_passed,
    entry_passed,
    final_passed,
    alerts_sent,
    trend_reasons=None,
    trend_examples=None,
    momentum_reasons=None,
    momentum_examples=None,
    structure_reasons=None,
    structure_examples=None,
    entry_reasons=None,
    entry_examples=None,
    setup_reasons=None,
    setup_examples=None,
    setup_received=None,
    setup_rejected=None,
    market_filters=None,
    breakout_ready=None,
):
    trend_reasons = trend_reasons or Counter()
    momentum_reasons = momentum_reasons or Counter()
    structure_reasons = structure_reasons or Counter()
    entry_reasons = entry_reasons or Counter()
    setup_reasons = setup_reasons or Counter()

    trend = stage_payload(stocks_checked, trend_passed, trend_reasons, trend_examples or {})
    structure = stage_payload(trend_passed, structure_passed, structure_reasons, structure_examples or {})
    momentum = stage_payload(structure_passed, momentum_passed, momentum_reasons, momentum_examples or {})
    entry_input = momentum_passed
    entry = stage_payload(entry_input, entry_passed, entry_reasons, entry_examples or {})

    setup_received = int(setup_received if setup_received is not None else entry_passed or 0)
    setup_rejected = int(setup_rejected if setup_rejected is not None else max(setup_received - int(final_passed or 0), 0))

    return {
        "timestamp_ist": timestamp_ist(),
        "scan_cycle_id": scan_cycle_id,
        "stocks_checked": int(stocks_checked or 0),
        "trend": trend,
        "momentum": momentum,
        "structure": structure,
        "entry": entry,
        "setup_engine": {
            "received": setup_received,
            "rejected": setup_rejected,
            "top_rejection_reasons": counter_dict(setup_reasons),
            "symbol_examples": examples_dict(setup_examples or {}),
        },
        "market_filters": market_filters or {},
        "final": {
            "breakout_ready": int(breakout_ready if breakout_ready is not None else entry_passed or 0),
            "final_passed": final_passed,
            "alerts_sent": int(alerts_sent or 0),
        },
    }


def save_scan_report(scan_report):
    existing = safe_read_json(DIAGNOSTICS_PATH, {})
    cycles = existing.get("scan_cycles") if isinstance(existing, dict) else []
    if not isinstance(cycles, list):
        cycles = []
    cycles.append(scan_report)
    cycles = cycles[-MAX_SCAN_CYCLES:]

    payload = {
        "updated_at_ist": timestamp_ist(),
        "latest": scan_report,
        "scan_cycles": cycles,
    }
    atomic_write_json(DIAGNOSTICS_PATH, payload)
    update_rejection_heatmap(scan_report)


def _all_stage_reasons(scan_report):
    reasons = Counter()
    symbols = Counter()
    stage_failures = Counter()
    for stage_name in ("trend", "momentum", "structure", "entry"):
        stage = scan_report.get(stage_name, {}) if isinstance(scan_report, dict) else {}
        failures = int(stage.get("failed") or 0)
        stage_failures[stage_name] += failures
        for reason, count in (stage.get("top_fail_reasons") or {}).items():
            reasons[str(reason)] += int(count or 0)
        for reason, stage_symbols in (stage.get("symbol_examples") or {}).items():
            for symbol in stage_symbols or []:
                symbols[str(symbol)] += 1

    setup_engine = scan_report.get("setup_engine", {}) if isinstance(scan_report, dict) else {}
    stage_failures["setup_engine"] += int(setup_engine.get("rejected") or 0)
    for reason, count in (setup_engine.get("top_rejection_reasons") or {}).items():
        reasons[str(reason)] += int(count or 0)
    for reason, stage_symbols in (setup_engine.get("symbol_examples") or {}).items():
        for symbol in stage_symbols or []:
            symbols[str(symbol)] += 1
    return reasons, symbols, stage_failures


def update_rejection_heatmap(scan_report):
    today = today_ist()
    existing = safe_read_json(HEATMAP_PATH, {})
    if not isinstance(existing, dict) or existing.get("date_ist") != today:
        existing = {
            "date_ist": today,
            "updated_at_ist": timestamp_ist(),
            "scan_cycles": 0,
            "total_rejections": 0,
            "rejection_counts": {},
            "rejection_percentages": {},
            "most_filtered_symbols": {},
            "stage_dropoff_counts": {},
            "stage_with_biggest_setup_dropoff": None,
        }

    reasons, symbols, stage_failures = _all_stage_reasons(scan_report)
    existing_counts = Counter(existing.get("rejection_counts") or {})
    existing_symbols = Counter(existing.get("most_filtered_symbols") or {})
    existing_stage_failures = Counter(existing.get("stage_dropoff_counts") or {})

    existing_counts.update(reasons)
    existing_symbols.update(symbols)
    existing_stage_failures.update(stage_failures)

    total_rejections = sum(existing_counts.values())
    percentages = {
        reason: round((count / total_rejections) * 100.0, 2) if total_rejections else 0.0
        for reason, count in existing_counts.most_common()
    }
    biggest_stage = None
    if existing_stage_failures:
        biggest_stage = existing_stage_failures.most_common(1)[0][0]

    heatmap = {
        "date_ist": today,
        "updated_at_ist": timestamp_ist(),
        "scan_cycles": int(existing.get("scan_cycles") or 0) + 1,
        "total_rejections": total_rejections,
        "rejection_counts": dict(existing_counts.most_common()),
        "rejection_percentages": percentages,
        "most_filtered_symbols": dict(existing_symbols.most_common(20)),
        "stage_dropoff_counts": dict(existing_stage_failures.most_common()),
        "stage_with_biggest_setup_dropoff": biggest_stage,
    }
    atomic_write_json(HEATMAP_PATH, heatmap)
