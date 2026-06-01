"""ECHO outcome lineage mapper.

Read-only audit for TITAN outcome truth lineage:
Setup -> Decision -> Trade -> Outcome -> Learning -> Evolution.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
MAP_PATH = RUNTIME_ECHO_DIR / "outcome_lineage_map.json"
SUMMARY_PATH = RUNTIME_ECHO_DIR / "outcome_lineage_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

IDENTIFIER_FIELDS = ("setup_id", "signal_id", "decision_id", "trace_id", "trade_id", "outcome_id")

INPUT_FILES = {
    "setup": [
        REPO_ROOT / "data" / "runtime" / "final_validated_setups.json",
        REPO_ROOT / "data" / "runtime" / "near_pass_setups.json",
        REPO_ROOT / "data" / "runtime" / "scanner_status.json",
    ],
    "decision": [
        REPO_ROOT / "data" / "runtime" / "master_brain_status.json",
        REPO_ROOT / "data" / "runtime" / "master_brain_runtime_health.json",
        REPO_ROOT / "data" / "runtime" / "truth_gate_status.json",
        REPO_ROOT / "data" / "runtime" / "scanner_filter_truth_status.json",
    ],
    "trade": [
        REPO_ROOT / "data" / "journals" / "active_trades.csv",
        REPO_ROOT / "data" / "journals" / "open_trades.csv",
        REPO_ROOT / "data" / "journals" / "trade_journal.csv",
        REPO_ROOT / "data" / "journals" / "trade_journal.jsonl",
        REPO_ROOT / "data" / "paper_trading" / "paper_processed_results.json",
        REPO_ROOT / "data" / "paper_trading" / "paper_audit_log.json",
        REPO_ROOT / "data" / "runtime" / "paper_trade_registry.json",
        REPO_ROOT / "data" / "runtime" / "trade_lifecycle_reconciliation.json",
    ],
    "outcome": [
        REPO_ROOT / "data" / "journals" / "trade_outcomes.csv",
        REPO_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
        REPO_ROOT / "data" / "journals" / "trade_results.csv",
        REPO_ROOT / "data" / "runtime" / "outcome_tracker_status.json",
        REPO_ROOT / "data" / "runtime" / "outcome_tracker_diagnostics.json",
        REPO_ROOT / "data" / "runtime" / "synthetic_trade_test.json",
    ],
    "learning": [
        REPO_ROOT / "data" / "learning" / "learning_report.json",
        REPO_ROOT / "data" / "learning" / "reinforcement_learning_reports.jsonl",
        REPO_ROOT / "data" / "runtime" / "meta_learning_status.json",
        REPO_ROOT / "data" / "runtime" / "evolution_memory.json",
    ],
    "evolution": [
        REPO_ROOT / "data" / "evolution" / "proposals" / "self_improvement_proposals.json",
        REPO_ROOT / "data" / "runtime" / "evolution_engine_status.json",
        REPO_ROOT / "data" / "runtime" / "synthetic_market_evolution_engine_status.json",
    ],
    "truth": [
        REPO_ROOT / "data" / "runtime" / "dashboard_truth_registry.json",
        REPO_ROOT / "data" / "runtime" / "trade_contract_diagnostics.json",
        REPO_ROOT / "data" / "runtime" / "trade_journal_diagnostics.json",
        REPO_ROOT / "data" / "runtime" / "final_setup_write_debug.json",
    ],
}


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def safe_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def norm_symbol(value: Any) -> str:
    return safe_text(value).upper().replace(".NS", "")


def norm_side(value: Any) -> str:
    text = safe_text(value).upper()
    if text == "BUY":
        return "LONG"
    if text == "SELL":
        return "SHORT"
    return text


def norm_num(value: Any) -> str:
    try:
        if value in (None, ""):
            return ""
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.6f}".rstrip("0").rstrip(".")
    except Exception:
        return safe_text(value)


def composite_key(record: dict[str, Any]) -> str:
    symbol = norm_symbol(record.get("symbol"))
    side = norm_side(record.get("side") or record.get("setup_type") or record.get("direction"))
    entry = norm_num(record.get("entry") or record.get("entry_price"))
    sl = norm_num(record.get("sl") or record.get("stop_loss"))
    target = norm_num(record.get("target") or record.get("tp"))
    if not all((symbol, side, entry, sl, target)):
        return ""
    return "|".join((symbol, side, entry, sl, target))


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def iter_json_objects(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if any(key in payload for key in ("trade_id", "symbol", "setup_id", "decision_id", "outcome_id", "trace_id", "status", "verdict")):
            found.append(payload)
        for value in payload.values():
            found.extend(iter_json_objects(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(iter_json_objects(item))
    return found


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def read_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append(dict(row))
    except Exception:
        return []
    return rows


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv(path)
    if suffix == ".jsonl":
        return read_jsonl(path)
    if suffix == ".json":
        payload = load_json(path)
        return iter_json_objects(payload)
    return []


def record_key(record: dict[str, Any], fallback: str) -> str:
    for field in ("trade_id", "paper_trade_id", "setup_id", "decision_id", "outcome_id", "trace_id", "candidate_id", "scan_id"):
        value = safe_text(record.get(field))
        if value:
            return f"{field}:{value}"
    key = composite_key(record)
    if key:
        return f"composite:{key}"
    return fallback


def collect_entities() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Counter[str]], list[dict[str, Any]]]:
    entities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identifiers: dict[str, Counter[str]] = {field: Counter() for field in IDENTIFIER_FIELDS}
    missing_files: list[dict[str, Any]] = []
    for entity_type, paths in INPUT_FILES.items():
        for path in paths:
            if not path.exists():
                missing_files.append({"entity_type": entity_type, "path": rel(path), "reason": "MISSING_FILE"})
                continue
            rows = read_records(path)
            for idx, row in enumerate(rows):
                enriched = dict(row)
                enriched["_source_file"] = rel(path)
                enriched["_entity_type"] = entity_type
                enriched["_record_key"] = record_key(enriched, f"{rel(path)}#{idx}")
                enriched["_composite_key"] = composite_key(enriched)
                entities[entity_type].append(enriched)
                for field in IDENTIFIER_FIELDS:
                    value = safe_text(enriched.get(field))
                    if value:
                        identifiers[field][value] += 1
                if safe_text(enriched.get("scan_id")):
                    identifiers["setup_id"][safe_text(enriched.get("scan_id"))] += 1
                if safe_text(enriched.get("paper_trade_id")):
                    identifiers["trade_id"][safe_text(enriched.get("paper_trade_id"))] += 1
    return entities, identifiers, missing_files


def index_by(records: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for field in fields:
            value = safe_text(record.get(field))
            if value:
                index[value].append(record)
        key = record.get("_composite_key")
        if key:
            index[f"composite:{key}"].append(record)
    return index


def link_exists(source: dict[str, Any], target_index: dict[str, list[dict[str, Any]]], fields: tuple[str, ...]) -> tuple[bool, str | None]:
    for field in fields:
        value = safe_text(source.get(field))
        if value and value in target_index:
            return True, f"{field}:{value}"
    key = source.get("_composite_key")
    if key and f"composite:{key}" in target_index:
        return True, f"composite:{key}"
    trade_id = safe_text(source.get("trade_id"))
    if trade_id:
        parts = trade_id.split("|")
        if len(parts) >= 6:
            symbol_side_key = "|".join((norm_symbol(parts[1]), norm_side(parts[2]), norm_num(parts[3]), norm_num(parts[4]), norm_num(parts[5])))
            if f"composite:{symbol_side_key}" in target_index:
                return True, f"trade_id_composite:{symbol_side_key}"
    return False, None


def edge_coverage(source: list[dict[str, Any]], target: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    target_index = index_by(target, fields)
    linked = []
    unlinked = []
    ambiguous = []
    for record in source:
        exists, method = link_exists(record, target_index, fields)
        if not exists:
            unlinked.append(record)
            continue
        match_count = len(target_index.get(method.split(":", 1)[1], [])) if method and not method.startswith("composite:") else len(target_index.get(method or "", []))
        if match_count > 1:
            ambiguous.append({"record_key": record["_record_key"], "method": method, "match_count": match_count})
        linked.append({"record_key": record["_record_key"], "method": method})
    total = len(source)
    score = round((len(linked) / total) * 100, 2) if total else 0.0
    return {
        "source_count": total,
        "linked_count": len(linked),
        "unlinked_count": len(unlinked),
        "ambiguous_count": len(ambiguous),
        "score": score,
        "linked_examples": linked[:20],
        "unlinked_examples": [{"record_key": item["_record_key"], "source_file": item["_source_file"]} for item in unlinked[:20]],
        "ambiguous_examples": ambiguous[:20],
    }


def duplicate_ids(identifiers: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    rows = []
    for field, counts in identifiers.items():
        for value, count in counts.items():
            if count > 1:
                rows.append({"id_type": field, "id_value": value, "count": count})
    rows.sort(key=lambda item: item["count"], reverse=True)
    return rows


def top_gaps(edges: dict[str, dict[str, Any]], duplicates: list[dict[str, Any]], missing_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for edge_name, stats in edges.items():
        if stats["unlinked_count"]:
            gaps.append(
                {
                    "gap": f"{edge_name} has unlinked records",
                    "count": stats["unlinked_count"],
                    "severity": "HIGH" if stats["score"] < 50 else "MEDIUM",
                    "recommended_action": f"Persist shared IDs or composite keys across {edge_name}.",
                }
            )
        if stats["ambiguous_count"]:
            gaps.append(
                {
                    "gap": f"{edge_name} has ambiguous links",
                    "count": stats["ambiguous_count"],
                    "severity": "HIGH",
                    "recommended_action": f"Add unique IDs to disambiguate {edge_name}.",
                }
            )
    if duplicates:
        gaps.append(
            {
                "gap": "duplicate identifiers detected",
                "count": len(duplicates),
                "severity": "HIGH",
                "recommended_action": "Deduplicate or namespace repeated IDs before using lineage as truth.",
            }
        )
    if missing_files:
        gaps.append(
            {
                "gap": "expected audit input files missing",
                "count": len(missing_files),
                "severity": "LOW",
                "recommended_action": "Confirm retired files or restore missing runtime reports.",
            }
        )
    gaps.sort(key=lambda item: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(item["severity"], 3), -int(item["count"])))
    return gaps[:20]


def main() -> int:
    entities, identifiers, missing_files = collect_entities()
    edges = {
        "setup_to_decision": edge_coverage(entities["setup"], entities["decision"], ("setup_id", "signal_id", "decision_id", "trade_id", "scan_id")),
        "decision_to_trade": edge_coverage(entities["decision"], entities["trade"], ("decision_id", "trade_id", "signal_id", "scan_id")),
        "trade_to_outcome": edge_coverage(entities["trade"], entities["outcome"], ("trade_id", "paper_trade_id", "outcome_id", "scan_id")),
        "outcome_to_learning": edge_coverage(entities["outcome"], entities["learning"], ("trade_id", "outcome_id", "paper_trade_id", "scan_id")),
        "learning_to_evolution": edge_coverage(entities["learning"], entities["evolution"], ("trade_id", "outcome_id", "decision_id", "setup_id")),
    }
    duplicates = duplicate_ids(identifiers)
    score_values = [edge["score"] for edge in edges.values()]
    lineage_completeness_score = round(sum(score_values) / len(score_values), 2) if score_values else 0.0
    traceability_score = round((edges["setup_to_decision"]["score"] + edges["decision_to_trade"]["score"] + edges["trade_to_outcome"]["score"]) / 3, 2)
    learning_linkage_score = edges["outcome_to_learning"]["score"]
    evolution_linkage_score = edges["learning_to_evolution"]["score"]
    orphan_count = sum(edge["unlinked_count"] for edge in edges.values())
    if lineage_completeness_score >= 90 and orphan_count == 0 and not duplicates:
        verdict = "COMPLETE"
    elif lineage_completeness_score >= 35 or edges["trade_to_outcome"]["score"] >= 50:
        verdict = "PARTIAL"
    else:
        verdict = "BROKEN"
    gaps = top_gaps(edges, duplicates, missing_files)
    identifier_summary = {
        field: {
            "unique_count": len(counter),
            "total_observed": sum(counter.values()),
            "duplicate_count": sum(1 for count in counter.values() if count > 1),
        }
        for field, counter in identifiers.items()
    }
    summary = {
        "schema": "titan.echo.outcome_lineage_summary.v1",
        "timestamp_ist": timestamp_ist(),
        "lineage_completeness_score": lineage_completeness_score,
        "traceability_score": traceability_score,
        "learning_linkage_score": learning_linkage_score,
        "evolution_linkage_score": evolution_linkage_score,
        "orphan_count": orphan_count,
        "duplicate_id_count": len(duplicates),
        "ambiguous_link_count": sum(edge["ambiguous_count"] for edge in edges.values()),
        "verdict": verdict,
        "TOP_20_LINEAGE_GAPS": gaps,
        "recommended_next_action": (
            "Add persistent IDs across setup, decision, trade, outcome, learning, and evolution writers before relying on lineage truth."
            if verdict != "COMPLETE"
            else "Keep lineage IDs immutable and rerun audit after writer changes."
        ),
    }
    payload = {
        "schema": "titan.echo.outcome_lineage_map.v1",
        "timestamp_ist": timestamp_ist(),
        "input_files": {entity: [rel(path) for path in paths] for entity, paths in INPUT_FILES.items()},
        "identifier_summary": identifier_summary,
        "duplicate_ids": duplicates[:200],
        "missing_input_files": missing_files,
        "entity_counts": {entity: len(rows) for entity, rows in entities.items()},
        "lineage_edges": edges,
        "TOP_20_LINEAGE_GAPS": gaps,
        "scores": {
            "lineage_completeness_score": lineage_completeness_score,
            "traceability_score": traceability_score,
            "learning_linkage_score": learning_linkage_score,
            "evolution_linkage_score": evolution_linkage_score,
        },
        "verdict": verdict,
        "safety_contract": {
            "read_only_audit": True,
            "scanner_mutation": False,
            "master_brain_mutation": False,
            "unified_brain_mutation": False,
            "consciousness_core_mutation": False,
            "broker_mutation": False,
            "risk_logic_mutation": False,
            "deploy": False,
            "restart": False,
            "push": False,
        },
    }
    RUNTIME_ECHO_DIR.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("TITAN ECHO outcome lineage mapper: PASSED")
    print(f"Lineage completeness: {lineage_completeness_score}")
    print(f"Traceability score: {traceability_score}")
    print(f"Orphan count: {orphan_count}")
    print(f"Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
