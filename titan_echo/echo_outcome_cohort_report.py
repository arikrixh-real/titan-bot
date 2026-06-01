"""Build conservative pre/post outcome cohort evidence for TITAN."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_RUNTIME = RUNTIME_DIR / "echo"
FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
OUTCOME_AUDIT_PATH = ECHO_RUNTIME / "outcome_improvement_audit.json"
OUTPUT_PATH = ECHO_RUNTIME / "outcome_cohort_report.json"
IST = timezone(timedelta(hours=5, minutes=30))

SOURCE_FILES = [
    "data/journals/trade_outcomes.csv",
    "data/journals/trade_outcomes.jsonl",
    "data/journals/trade_results.csv",
    "data/journals/trade_journal.csv",
    "data/journals/trade_journal.jsonl",
    "data/runtime/outcome_tracker_status.json",
    "data/runtime/outcome_tracker_diagnostics.json",
    "data/runtime/final_validated_setups.json",
    "data/runtime/strategy_weight_change_log.json",
    "data/runtime/evolution_memory.json",
    "data/runtime/meta_learning_status.json",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path, default: Any | None = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {} if default is None else default


def as_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def index_files() -> list[str]:
    data = load_json(FILE_INDEX_PATH, {})
    items = data.get("files") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [str(item.get("relative_path", "")) for item in items if isinstance(item, dict)]


def discover_files() -> list[Path]:
    paths = {REPO_ROOT / item for item in SOURCE_FILES}
    terms = ["outcome", "trade_result", "trade_outcomes", "journal", "confidence", "learning", "evolution", "strategy_weight"]
    for relative in index_files():
        lower = relative.replace("\\", "/").lower()
        if lower.startswith("data/report_vault/") or lower.startswith("data/cache/"):
            continue
        if lower.startswith("data/") and lower.endswith((".csv", ".json", ".jsonl")) and any(term in lower for term in terms):
            paths.add(REPO_ROOT / relative)
    return sorted(paths)


def read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except Exception:
        return []
    return rows


def flatten_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows = []
        for key in ["trades", "results", "outcomes", "records", "setups", "closed_trades"]:
            nested = value.get(key)
            if isinstance(nested, list):
                rows.extend(item for item in nested if isinstance(item, dict))
        return rows or [value]
    return []


def collect_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    inspected = []
    for path in discover_files():
        relative = path.relative_to(REPO_ROOT).as_posix() if path.exists() else path.as_posix()
        file_rows: list[dict[str, Any]] = []
        error = None
        if not path.exists():
            error = "missing"
        elif path.suffix.lower() == ".csv":
            file_rows = read_csv(path)
        elif path.suffix.lower() == ".jsonl":
            file_rows = read_jsonl(path)
        elif path.suffix.lower() == ".json":
            file_rows = flatten_json(load_json(path, {}))
        for row in file_rows:
            row["_source_file"] = relative
            rows.append(row)
        inspected.append({"relative_path": relative, "exists": path.exists(), "records_read": len(file_rows), "error": error})
    return rows, inspected


def parse_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).strip())
    except ValueError:
        return None


def row_time(row: dict[str, Any]) -> str:
    for key in ["closed_at", "checked_at", "timestamp", "opened_at", "timestamp_ist", "generated_at_ist"]:
        if row.get(key):
            return str(row[key])
    return ""


def outcome_known(row: dict[str, Any]) -> bool:
    text = str(row.get("outcome") or row.get("result") or row.get("status") or "").upper()
    return bool(text and text not in {"OPEN", "PENDING", "UNKNOWN", "NONE", "N/A", "NA"})


def win_value(row: dict[str, Any]) -> bool | None:
    text = str(row.get("outcome") or row.get("result") or "").upper()
    if text in {"TP", "WIN", "PROFIT", "TARGET"}:
        return True
    if text in {"SL", "LOSS", "STOP_LOSS"}:
        return False
    pnl = parse_float(row.get("realized_pnl") or row.get("pnl") or row.get("pnl_points"))
    return None if pnl is None else pnl > 0


def execution_cohort(row: dict[str, Any]) -> str:
    text = as_text(row)
    if "synthetic" in text:
        return "synthetic"
    if "paper" in text or str(row.get("is_paper_trade", "")).lower() == "true":
        return "paper"
    if str(row.get("broker_orders", "")).lower() == "true" or "live_execution" in text:
        return "live"
    return "unknown"


def confidence(row: dict[str, Any]) -> float | None:
    for key in ["confidence", "confidence_score", "rank_score", "score"]:
        value = parse_float(row.get(key))
        if value is not None:
            return value
    return None


def split_pre_post(rows: list[dict[str, Any]], marker_terms: list[str]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    marker_times = sorted(row_time(row) for row in rows if any(term in as_text(row) for term in marker_terms) and row_time(row))
    if not marker_times:
        return "COHORT_SEPARATION_NOT_PROVEN", [], []
    marker = marker_times[0]
    pre = [row for row in rows if row_time(row) and row_time(row) < marker]
    post = [row for row in rows if row_time(row) and row_time(row) >= marker]
    if not pre or not post:
        return "COHORT_SEPARATION_NOT_PROVEN", pre, post
    return marker, pre, post


def summarize(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    known = [row for row in rows if outcome_known(row)]
    wins = sum(1 for row in known if win_value(row) is True)
    losses = sum(1 for row in known if win_value(row) is False)
    confs = [confidence(row) for row in known]
    confs = [item for item in confs if item is not None]
    evidence_quality = "UNKNOWN"
    if len(known) >= 100:
        evidence_quality = "MODERATE"
    if len(known) >= 100 and len(confs) >= 30:
        evidence_quality = "PARTIAL"
    return {
        "cohort": name,
        "outcome_count": len(rows),
        "known_outcomes": len(known),
        "unknown_outcomes": max(0, len(rows) - len(known)),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / (wins + losses), 4) if wins + losses else None,
        "confidence_statistics": {
            "count": len(confs),
            "average": round(sum(confs) / len(confs), 4) if confs else None,
            "min": min(confs) if confs else None,
            "max": max(confs) if confs else None,
        },
        "evidence_quality": evidence_quality,
    }


def comparison(pre: list[dict[str, Any]], post: list[dict[str, Any]]) -> dict[str, Any]:
    pre_s = summarize("pre", pre)
    post_s = summarize("post", post)
    if pre_s["win_rate"] is None or post_s["win_rate"] is None:
        return {"status": "COHORT_SEPARATION_NOT_PROVEN", "delta_win_rate": None, "pre": pre_s, "post": post_s}
    return {
        "status": "PARTIAL" if min(pre_s["known_outcomes"], post_s["known_outcomes"]) >= 30 else "UNKNOWN",
        "delta_win_rate": round(post_s["win_rate"] - pre_s["win_rate"], 4),
        "pre": pre_s,
        "post": post_s,
    }


def build_report() -> dict[str, Any]:
    rows, inspected = collect_rows()
    cohorts = {name: summarize(name, [row for row in rows if execution_cohort(row) == name]) for name in ["live", "paper", "synthetic", "unknown"]}
    learning_marker, pre_learning, post_learning = split_pre_post(rows, ["learning", "reinforcement", "policy"])
    evolution_marker, pre_evolution, post_evolution = split_pre_post(rows, ["evolution", "mutation", "genome"])
    learning_cmp = comparison(pre_learning, post_learning)
    evolution_cmp = comparison(pre_evolution, post_evolution)
    separation_proven = learning_marker != "COHORT_SEPARATION_NOT_PROVEN" or evolution_marker != "COHORT_SEPARATION_NOT_PROVEN"
    score = 0
    if any(cohorts[name]["known_outcomes"] for name in cohorts):
        score += 25
    if cohorts["paper"]["known_outcomes"] or cohorts["synthetic"]["known_outcomes"] or cohorts["unknown"]["known_outcomes"]:
        score += 15
    if separation_proven:
        score += 20
    if learning_cmp.get("status") == "PARTIAL" or evolution_cmp.get("status") == "PARTIAL":
        score += 15
    if any((cmp.get("delta_win_rate") or 0) > 0 for cmp in [learning_cmp, evolution_cmp]):
        score += 10
    confidence_score = min(score, 70)
    strongest = sorted(cohorts.values(), key=lambda item: item["known_outcomes"], reverse=True)[:3]
    weakest = [item for item in cohorts.values() if item["known_outcomes"] == 0] or sorted(cohorts.values(), key=lambda item: item["known_outcomes"])[:3]
    return {
        "schema": "titan_echo.outcome_cohort_report.v1",
        "timestamp_ist": timestamp_ist(),
        "cohort_separation_status": "PARTIAL" if separation_proven else "COHORT_SEPARATION_NOT_PROVEN",
        "cohorts": cohorts,
        "pre_learning_marker": learning_marker,
        "learning_comparison": learning_cmp,
        "pre_evolution_marker": evolution_marker,
        "evolution_comparison": evolution_cmp,
        "cohort_comparison_score": score,
        "improvement_confidence_score": confidence_score,
        "strongest_cohort_evidence": strongest,
        "weakest_cohort_evidence": weakest,
        "missing_evidence": [
            "Live/paper/synthetic separation is incomplete." if cohorts["unknown"]["known_outcomes"] else "",
            "Cohort causality is not proven without explicit learning/evolution change timestamps tied to selected decisions.",
            "Before/after comparison remains PARTIAL unless pre and post cohorts are clean and adequately sized.",
        ],
        "files_inspected": inspected,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO outcome cohort report: PASSED")
    print(f"Improvement confidence score: {report['improvement_confidence_score']}")
    print(f"Cohort separation status: {report['cohort_separation_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
