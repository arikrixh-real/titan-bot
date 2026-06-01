"""Audit whether TITAN learning/evolution changes improved outcomes."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_RUNTIME = RUNTIME_DIR / "echo"

EVOLUTION_EVIDENCE_AUDIT_PATH = ECHO_RUNTIME / "evolution_evidence_audit.json"
EVOLUTION_PROOF_PATH = ECHO_RUNTIME / "evolution_proof_report.json"
INTEGRATION_PROOF_PATH = ECHO_RUNTIME / "integration_proof_report.json"
FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
OUTPUT_PATH = ECHO_RUNTIME / "outcome_improvement_audit.json"

IST = timezone(timedelta(hours=5, minutes=30))

EVALUATION_CATEGORIES = [
    "closed_outcome_count",
    "win_loss_evidence",
    "before_after_performance_evidence",
    "learning_change_evidence",
    "evolution_change_evidence",
    "strategy_weight_change_evidence",
    "confidence_change_evidence",
    "outcome_feedback_usage",
    "measurable_improvement",
    "sample_size_quality",
]

BASE_FILES = [
    "data/runtime/outcome_tracker_diagnostics.json",
    "data/runtime/trade_contract_diagnostics.json",
    "data/runtime/final_validated_setups.json",
    "data/runtime/learning_status.json",
    "data/runtime/evolution_status.json",
    "data/runtime/memory_status.json",
    "data/runtime/experience_memory_status.json",
    "data/runtime/outcome_tracker_status.json",
    "data/runtime/evolution_engine_status.json",
    "data/runtime/evolution_memory.json",
    "data/runtime/meta_learning_status.json",
    "data/runtime/strategy_weight_change_log.json",
    "data/journals/trade_outcomes.csv",
    "data/journals/trade_outcomes.jsonl",
    "data/journals/trade_results.csv",
    "data/journals/trade_journal.jsonl",
    "data/journals/trade_journal.csv",
    "data/paper_trading/paper_processed_results.json",
    "data/learning/reinforcement_learning_reports.jsonl",
]

SMALL_SAMPLE_THRESHOLD = 30
PROVEN_SAMPLE_THRESHOLD = 100


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path, default: Any | None = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {} if default is None else default


def try_load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"malformed line {exc.lineno}"
    except OSError as exc:
        return None, f"read error {exc.__class__.__name__}"


def as_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def extract_index_files(file_index: Any) -> list[str]:
    if isinstance(file_index, dict):
        candidates = file_index.get("files") or file_index.get("indexed_files") or file_index.get("file_index")
        if isinstance(candidates, list):
            return [
                str(item.get("relative_path", ""))
                for item in candidates
                if isinstance(item, dict) and item.get("relative_path")
            ]
    if isinstance(file_index, list):
        return [
            str(item.get("relative_path", ""))
            for item in file_index
            if isinstance(item, dict) and item.get("relative_path")
        ]
    return []


def discover_files(file_index: Any) -> list[Path]:
    paths = {REPO_ROOT / relative for relative in BASE_FILES}
    interesting_terms = [
        "outcome",
        "trade_result",
        "trade_results",
        "trade_outcomes",
        "journal",
        "performance",
        "learning",
        "evolution",
        "strategy_weight",
        "confidence",
    ]
    for relative in extract_index_files(file_index):
        normalized = relative.replace("\\", "/").lower()
        if any(skip in normalized for skip in ["data/report_vault/", "data/cache/", "__pycache__"]):
            continue
        if normalized.startswith("data/") and normalized.endswith((".json", ".jsonl", ".csv", ".txt")):
            if any(term in normalized for term in interesting_terms):
                paths.add(REPO_ROOT / relative)
    for folder in [REPO_ROOT / "data" / "journals", RUNTIME_DIR, REPO_ROOT / "data" / "learning"]:
        if not folder.exists():
            continue
        for path in folder.glob("*"):
            if path.is_file() and any(term in path.name.lower() for term in interesting_terms):
                paths.add(path)
    return sorted(paths)


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def is_closed_outcome(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return text in {"TP", "SL", "WIN", "LOSS", "CLOSED", "PROFIT", "STOP_LOSS", "TARGET"} or (
        text and text not in {"OPEN", "PENDING", "UNKNOWN", "NONE", "NA", "N/A"}
    )


def is_win(row: dict[str, Any]) -> bool | None:
    outcome = str(row.get("outcome") or row.get("result") or "").strip().upper()
    if outcome in {"TP", "WIN", "PROFIT", "TARGET"}:
        return True
    if outcome in {"SL", "LOSS", "STOP_LOSS"}:
        return False
    pnl = parse_float(row.get("realized_pnl") or row.get("pnl") or row.get("pnl_points"))
    if pnl is None:
        reward = parse_float(row.get("reinforcement_score") or row.get("reinforcement_strategy_reward"))
        if reward is None:
            return None
        return reward > 0
    return pnl > 0


def row_is_synthetic_or_test(row: dict[str, Any]) -> bool:
    text = as_text(row)
    return "synthetic" in text or "test_trade" in text and "true" in text


def read_csv_rows(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if index >= limit:
                    break
                rows.append(dict(row))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []
    return rows


def read_jsonl_rows(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    rows.append(data)
    except OSError:
        return []
    return rows


def flatten_json_records(value: Any, limit: int = 5000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value[:limit]:
            if isinstance(item, dict):
                rows.append(item)
    elif isinstance(value, dict):
        for key in ["trades", "results", "outcomes", "records", "closed_trades", "setups"]:
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested[:limit]:
                    if isinstance(item, dict):
                        rows.append(item)
        if not rows:
            rows.append(value)
    return rows[:limit]


def collect_records(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(REPO_ROOT).as_posix() if path.exists() else path.as_posix()
        file_records: list[dict[str, Any]] = []
        error = None
        if not path.exists():
            error = "missing"
        elif path.suffix.lower() == ".csv":
            file_records = read_csv_rows(path)
        elif path.suffix.lower() == ".jsonl":
            file_records = read_jsonl_rows(path)
        elif path.suffix.lower() == ".json":
            data, error = try_load_json(path)
            if error is None:
                file_records = flatten_json_records(data)
        else:
            error = "unsupported"

        for row in file_records:
            row["_source_file"] = relative
            records.append(row)
        inspected.append(
            {
                "relative_path": relative,
                "exists": path.exists(),
                "error": error,
                "records_read": len(file_records),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        )
    return records, inspected


def outcome_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = []
    wins = 0
    losses = 0
    paper_or_test = 0
    total_pnl = 0.0
    pnl_seen = 0
    for row in records:
        if not is_closed_outcome(row.get("outcome") or row.get("result") or row.get("status")):
            continue
        closed.append(row)
        if row_is_synthetic_or_test(row):
            paper_or_test += 1
        win = is_win(row)
        if win is True:
            wins += 1
        elif win is False:
            losses += 1
        pnl = parse_float(row.get("realized_pnl") or row.get("pnl") or row.get("pnl_points"))
        if pnl is not None:
            total_pnl += pnl
            pnl_seen += 1
    return {
        "closed_outcome_count": len(closed),
        "win_count": wins,
        "loss_count": losses,
        "unknown_result_count": max(0, len(closed) - wins - losses),
        "paper_or_test_count": paper_or_test,
        "total_pnl_observed": round(total_pnl, 4),
        "pnl_record_count": pnl_seen,
        "win_rate": round(wins / (wins + losses), 4) if wins + losses else None,
    }


def text_has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def status_from_score(score: int) -> str:
    if score >= 75:
        return "YES"
    if score >= 40:
        return "PARTIAL"
    if score > 0:
        return "UNKNOWN"
    return "NO"


def category_result(
    category: str,
    score: int,
    evidence_found: list[str],
    evidence_missing: list[str],
    limitation: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "status": status_from_score(score),
        "score": max(0, min(100, score)),
        "evidence_found": list(dict.fromkeys(evidence_found))[:20],
        "evidence_missing": list(dict.fromkeys(evidence_missing))[:12],
        "limitation": limitation,
        "recommended_next_step": next_step,
    }


def build_categories(summary: dict[str, Any], records: list[dict[str, Any]], source_text: str) -> list[dict[str, Any]]:
    closed_count = int(summary["closed_outcome_count"])
    wins = int(summary["win_count"])
    losses = int(summary["loss_count"])
    win_rate = summary["win_rate"]
    paper_or_test = int(summary["paper_or_test_count"])

    before_after = text_has_any(source_text, ["before", "after", "baseline", "previous_win_rate", "post", "pre_"])
    learning_change = text_has_any(source_text, ["learning", "reinforcement", "policy", "reward", "penalize"])
    evolution_change = text_has_any(source_text, ["evolution", "mutation", "genome"])
    weight_change = text_has_any(source_text, ["weight_change", "strategy_weight", "recommended_live_weight", "rank_adjustment"])
    confidence_change = text_has_any(source_text, ["confidence", "calibration", "false_confidence"])
    feedback_usage = text_has_any(source_text, ["outcome", "feedback", "reward", "penalize", "reinforcement_learning_action"])
    measurable = before_after and closed_count >= SMALL_SAMPLE_THRESHOLD and wins + losses > 0

    categories = [
        category_result(
            "closed_outcome_count",
            90 if closed_count >= PROVEN_SAMPLE_THRESHOLD else 55 if closed_count >= SMALL_SAMPLE_THRESHOLD else 20 if closed_count else 0,
            [f"Closed outcome rows found: {closed_count}"] if closed_count else [],
            [] if closed_count else ["No closed outcomes found."],
            "Closed rows may include paper or synthetic records; live outcome proof requires separate tagging.",
            "Separate live, paper, and synthetic closed outcomes before claiming production improvement.",
        ),
        category_result(
            "win_loss_evidence",
            80 if wins + losses >= SMALL_SAMPLE_THRESHOLD else 45 if wins + losses > 0 else 0,
            [f"Wins: {wins}", f"Losses: {losses}", f"Win rate: {win_rate}"] if wins + losses else [],
            [] if wins + losses else ["No usable win/loss outcome rows found."],
            "Win/loss evidence does not by itself prove learning caused improvement.",
            "Compare win/loss rates before and after learning/evolution changes.",
        ),
        category_result(
            "before_after_performance_evidence",
            45 if before_after and closed_count >= SMALL_SAMPLE_THRESHOLD else 25 if before_after else 0,
            ["Before/after or baseline terms found in inspected artifacts."] if before_after else [],
            ["No explicit numeric pre/post performance comparison was proven."] if before_after else ["No reliable before/after performance comparison found."],
            "Keyword evidence must be backed by explicit pre/post metrics to prove improvement.",
            "Create a read-only pre/post performance table from closed outcomes and change timestamps.",
        ),
        category_result(
            "learning_change_evidence",
            65 if learning_change else 0,
            ["Learning/reinforcement terms found in outcome artifacts."] if learning_change else [],
            [] if learning_change else ["No learning change evidence found in inspected artifacts."],
            "Learning activity can exist without improving outcomes.",
            "Link learning updates to later closed outcomes by timestamp and strategy key.",
        ),
        category_result(
            "evolution_change_evidence",
            65 if evolution_change else 0,
            ["Evolution/mutation/genome terms found in inspected artifacts."] if evolution_change else [],
            [] if evolution_change else ["No evolution change evidence found in inspected artifacts."],
            "Evolution state changes do not prove outcome lift.",
            "Link evolution parameter changes to subsequent outcome cohorts.",
        ),
        category_result(
            "strategy_weight_change_evidence",
            65 if weight_change else 0,
            ["Strategy weight/rank adjustment terms found."] if weight_change else [],
            [] if weight_change else ["No strategy weight change evidence found."],
            "Weight changes must be tied to selected trades and later outcomes.",
            "Trace strategy weight changes into setup ranking and closed outcomes.",
        ),
        category_result(
            "confidence_change_evidence",
            55 if confidence_change else 0,
            ["Confidence/calibration terms found."] if confidence_change else [],
            [] if confidence_change else ["No confidence change evidence found."],
            "Confidence terms do not prove calibrated confidence improved outcomes.",
            "Compare predicted confidence buckets against realized win/loss after calibration changes.",
        ),
        category_result(
            "outcome_feedback_usage",
            75 if feedback_usage and closed_count else 30 if feedback_usage else 0,
            ["Outcome feedback/reward terms found."] if feedback_usage else [],
            [] if feedback_usage else ["No outcome feedback usage evidence found."],
            "Feedback usage proves learning input, not necessarily improvement.",
            "Verify feedback changed future scoring or selection and improved later outcomes.",
        ),
        category_result(
            "measurable_improvement",
            50 if measurable else 0,
            ["Closed outcomes and before/after terms both found."] if measurable else [],
            ["No explicit measured improvement delta was proven."] if measurable else ["No measured improvement with adequate pre/post evidence found."],
            "Improvement must be measured on enough closed outcomes and separated from synthetic/paper tests.",
            "Build a read-only improvement cohort report with sample size, win rate, PnL, and period splits.",
        ),
        category_result(
            "sample_size_quality",
            80 if closed_count >= PROVEN_SAMPLE_THRESHOLD and paper_or_test < closed_count else 45 if closed_count >= SMALL_SAMPLE_THRESHOLD else 15 if closed_count else 0,
            [f"Closed outcomes: {closed_count}", f"Paper/test-like outcomes: {paper_or_test}"] if closed_count else [],
            ["Sample size too low for proof."] if closed_count < PROVEN_SAMPLE_THRESHOLD else [],
            "Synthetic or paper outcomes reduce production confidence.",
            "Increase verified closed outcome sample and tag live/paper/synthetic rows explicitly.",
        ),
    ]
    return categories


def verdict(score: int, categories: list[dict[str, Any]], closed_count: int) -> str:
    measurable = next((item for item in categories if item["category"] == "measurable_improvement"), {})
    before_after = next((item for item in categories if item["category"] == "before_after_performance_evidence"), {})
    if closed_count == 0:
        return "NOT_PROVEN"
    if score >= 75 and closed_count >= PROVEN_SAMPLE_THRESHOLD and measurable.get("status") == "YES":
        return "IMPROVEMENT_PROVEN"
    if score >= 45 and closed_count >= SMALL_SAMPLE_THRESHOLD and before_after.get("score", 0) >= 40:
        return "PARTIAL_IMPROVEMENT"
    if score > 20:
        return "ACTIVITY_ONLY"
    return "NOT_PROVEN"


def strongest(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(categories, key=lambda item: (-int(item["score"]), item["category"]))[:5]


def weakest(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(categories, key=lambda item: (int(item["score"]), item["category"]))[:5]


def missing_proofs(categories: list[dict[str, Any]]) -> list[dict[str, str]]:
    proofs = []
    for item in categories:
        for missing in item["evidence_missing"]:
            proofs.append({"category": item["category"], "missing_proof": missing})
        if int(item["score"]) < 75:
            proofs.append({"category": item["category"], "missing_proof": item["limitation"]})
    return proofs[:15]


def sample_warning(summary: dict[str, Any]) -> str:
    closed_count = int(summary["closed_outcome_count"])
    paper_or_test = int(summary["paper_or_test_count"])
    if closed_count == 0:
        return "No closed outcomes found; improvement cannot be proven."
    if closed_count < SMALL_SAMPLE_THRESHOLD:
        return f"Closed outcome sample is small ({closed_count}); improvement cannot be proven."
    if closed_count < PROVEN_SAMPLE_THRESHOLD:
        return f"Closed outcome sample is moderate ({closed_count}); treat improvement as partial until sample reaches {PROVEN_SAMPLE_THRESHOLD}+ verified outcomes."
    if paper_or_test:
        return f"Closed sample includes {paper_or_test} paper/test-like outcomes; separate them before production claims."
    return "Sample size is adequate for audit, subject to live/paper tagging quality."


def recommended_next_missions() -> list[dict[str, Any]]:
    return [
        {
            "mission_title": "Read-only pre/post outcome cohort report",
            "risk_level": "LOW",
            "execution_allowed": False,
            "objective": "Compare outcomes before and after learning/evolution changes with live/paper/synthetic separation.",
        },
        {
            "mission_title": "Decision-to-outcome trace audit",
            "risk_level": "LOW",
            "execution_allowed": False,
            "objective": "Trace learned/evolved strategy changes into selected setups and their closed outcomes.",
        },
        {
            "mission_title": "Confidence calibration outcome audit",
            "risk_level": "LOW",
            "execution_allowed": False,
            "objective": "Measure whether confidence buckets match realized win/loss after calibration changes.",
        },
    ]


def build_report() -> dict[str, Any]:
    evolution_evidence = load_json(EVOLUTION_EVIDENCE_AUDIT_PATH, {})
    evolution_proof = load_json(EVOLUTION_PROOF_PATH, {})
    integration = load_json(INTEGRATION_PROOF_PATH, {})
    file_index = load_json(FILE_INDEX_PATH, {})
    modules = load_json(MODULE_REGISTRY_PATH, {})
    graph = load_json(CONNECTION_GRAPH_PATH, {})

    paths = discover_files(file_index)
    records, inspected = collect_records(paths)
    summary = outcome_summary(records)
    source_text = as_text(
        {
            "records_sample": records[:500],
            "evolution_evidence": evolution_evidence,
            "evolution_proof": evolution_proof,
            "integration": integration,
            "modules": modules,
            "graph": graph,
        }
    )
    categories = build_categories(summary, records, source_text)
    score = round(sum(int(item["score"]) for item in categories) / len(categories))

    return {
        "schema": "titan_echo.outcome_improvement_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "outcome_improvement_score": score,
        "verdict": verdict(score, categories, int(summary["closed_outcome_count"])),
        "closed_outcome_count": summary["closed_outcome_count"],
        "win_loss_summary": summary,
        "categories": categories,
        "strongest_evidence": strongest(categories),
        "weakest_evidence": weakest(categories),
        "missing_proofs": missing_proofs(categories),
        "sample_size_warning": sample_warning(summary),
        "recommended_next_missions": recommended_next_missions(),
        "files_inspected": inspected,
        "audit_standard": "Outcome improvement requires closed outcomes, before/after performance evidence, and enough non-synthetic sample size. Learning/evolution file changes alone are activity evidence only.",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO outcome improvement audit: PASSED")
    print(f"Outcome improvement score: {report['outcome_improvement_score']}")
    print(f"Verdict: {report['verdict']}")
    print(f"Closed outcome count: {report['closed_outcome_count']}")
    print(f"Sample size warning: {report['sample_size_warning']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
