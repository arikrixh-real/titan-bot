import csv
import glob
import json
import time
from pathlib import Path

from consciousness_core.state import atomic_write_json, stable_hash


PROCESSED_OBSERVATIONS_PATH = Path("data") / "consciousness_core" / "processed_observations.json"
DATA_SOURCES = (
    "data/runtime/worker_health.json",
    "data/runtime/daemon_health.json",
    "data/runtime/intelligence_state/*.json",
    "data/runtime/titan_runtime_status.json",
    "data/runtime/dashboard_sync_status.json",
    "data/report_vault/latest_aggregated_packet.json",
    "data/knowledge_vault/reports/knowledge_to_consciousness_packet.json",
    "data/experience_vault/reports/external_experience_packet.json",
    "data/memory/evolution_state.json",
    "reports/evolution_report.txt",
    "data/research/*.json",
    "data/scenario_simulation/*.json",
    "data/self_reflection/*.json",
    "data/confidence_calibration/*.json",
    "data/no_trade/*.json",
    "data/memory_consolidation/*.json",
    "data/auto_repair/*.json",
    "data/execution_safety/*.json",
    "data/news_intelligence/*.json",
    "data/journals/trade_journal.csv",
    "data/journals/trade_outcomes.csv",
    "titan_brain/memory/news_batch_state.json",
)
CRITICAL_PATTERNS = {
    "data/runtime/worker_health.json",
    "data/runtime/daemon_health.json",
    "data/runtime/titan_runtime_status.json",
    "data/report_vault/latest_aggregated_packet.json",
    "data/knowledge_vault/reports/knowledge_to_consciousness_packet.json",
    "data/memory/evolution_state.json",
    "reports/evolution_report.txt",
    "data/journals/trade_outcomes.csv",
}


def load_processed_observations(path=PROCESSED_OBSERVATIONS_PATH):
    try:
        with Path(path).open("r", encoding="utf-8") as processed_file:
            payload = json.load(processed_file)
        if isinstance(payload, dict):
            payload.setdefault("processed_hashes", {})
            return payload
    except Exception:
        pass
    return {"processed_hashes": {}, "last_updated": None}


def save_processed_observations(processed, path=PROCESSED_OBSERVATIONS_PATH):
    atomic_write_json(path, processed)
    return processed


def _read_json(path):
    with path.open("r", encoding="utf-8") as source_file:
        payload = json.load(source_file)
    if isinstance(payload, dict):
        count = len(payload)
    elif isinstance(payload, list):
        count = len(payload)
    else:
        count = 1
    return payload, {"record_count": count}


def _read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as source_file:
        rows = list(csv.DictReader(source_file))
    return rows[-50:], {
        "record_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
    }


def _to_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _severity_from_text(text):
    normalized = str(text or "").upper()
    if any(token in normalized for token in ("ERROR", "TIMEOUT", "FAILED", "CRITICAL", "REJECTED")):
        return "HIGH"
    if any(token in normalized for token in ("WARN", "WARNING", "REVIEW", "NO_DATA", "LOW", "CAUTION")):
        return "MEDIUM"
    return "LOW"


def _actionability(metric, value, severity):
    score = {"LOW": 0.25, "MEDIUM": 0.55, "HIGH": 0.85}.get(severity, 0.35)
    if metric in {"worker_status", "timeout_count", "validation_status", "trade_loss", "no_trade_warning"}:
        score += 0.1
    if isinstance(value, (int, float)) and value:
        score += min(abs(float(value)) / 100.0, 0.2)
    return round(min(score, 1.0), 3)


def _normalized_observation(source, obs_type, metric, value, evidence, entity=None, timestamp=None, severity=None):
    severity = severity or _severity_from_text(value)
    evidence_payload = {
        "source": source,
        "type": obs_type,
        "metric": metric,
        "value": value,
        "entity": entity,
        "evidence": evidence,
    }
    content_hash = stable_hash(evidence_payload)
    return {
        "source": source,
        "type": obs_type,
        "severity": severity,
        "timestamp": timestamp,
        "entity": entity,
        "metric": metric,
        "value": value,
        "evidence": evidence,
        "actionability_score": _actionability(metric, value, severity),
        "content_hash": content_hash,
    }


def _flatten_numeric_report(source, payload, timestamp):
    observations = []
    if not isinstance(payload, dict):
        return observations
    for key in (
        "calibrated_confidence_score",
        "reliability_score",
        "no_trade_score",
        "auto_repair_score",
        "severity_score",
        "win_rate",
        "avg_rr",
        "total_closed_trades",
        "avg_score_winners",
        "avg_score_losers",
    ):
        if key in payload:
            value = _to_float(payload.get(key))
            observations.append(
                _normalized_observation(
                    source,
                    "report_metric",
                    key,
                    value,
                    {"raw_value": payload.get(key)},
                    entity=Path(source).stem,
                    timestamp=timestamp,
                    severity="MEDIUM" if value is not None and value < 50 and "score" in key else "LOW",
                )
            )
    return observations


def _observations_from_worker_health(source, payload, timestamp):
    observations = []
    if not isinstance(payload, dict):
        return observations
    for task, health in payload.items():
        if not isinstance(health, dict):
            continue
        status = str(health.get("status") or health.get("last_status") or "UNKNOWN").upper()
        observations.append(
            _normalized_observation(
                source,
                "worker_health",
                "worker_status",
                status,
                health,
                entity=task,
                timestamp=health.get("last_finished_at") or health.get("last_started_at") or timestamp,
                severity=_severity_from_text(status),
            )
        )
        for metric in ("error_count", "timeout_count", "run_count"):
            if metric in health:
                value = int(health.get(metric) or 0)
                severity = "HIGH" if metric in {"error_count", "timeout_count"} and value >= 2 else "MEDIUM" if value else "LOW"
                observations.append(
                    _normalized_observation(
                        source,
                        "worker_health",
                        metric,
                        value,
                        health,
                        entity=task,
                        timestamp=timestamp,
                        severity=severity,
                    )
                )
    return observations


def _observations_from_intelligence_state(source, payload, timestamp):
    if not isinstance(payload, dict):
        return []
    task = payload.get("task") or Path(source).stem
    observations = [
        _normalized_observation(
            source,
            "intelligence_state",
            "last_status",
            payload.get("last_status"),
            payload,
            entity=task,
            timestamp=payload.get("updated_at") or timestamp,
            severity=_severity_from_text(payload.get("last_status")),
        )
    ]
    if payload.get("last_error"):
        observations.append(
            _normalized_observation(
                source,
                "intelligence_state",
                "last_error",
                payload.get("last_error"),
                payload,
                entity=task,
                timestamp=payload.get("updated_at") or timestamp,
                severity="HIGH",
            )
        )
    return observations


def _observations_from_trade_outcomes(source, rows, timestamp):
    observations = []
    if not isinstance(rows, list):
        return observations
    for row in rows[-50:]:
        if not isinstance(row, dict):
            continue
        outcome = str(row.get("outcome") or row.get("result_reason") or "").upper()
        pnl = _to_float(row.get("realized_pnl") or row.get("pnl_points"))
        score = _to_float(row.get("score") or row.get("rank_score"))
        symbol = row.get("symbol") or row.get("trade_id")
        if outcome in {"SL", "LOSS"} or (pnl is not None and pnl < 0):
            severity = "HIGH" if score is not None and score >= 3.0 else "MEDIUM"
            observation = _normalized_observation(
                source,
                "trade_outcome",
                "trade_loss",
                pnl,
                row,
                entity=symbol,
                timestamp=row.get("closed_at") or timestamp,
                severity=severity,
            )
            observation["source_type"] = "NATIVE_EXPERIENCE"
            observations.append(observation)
        if score is not None and score >= 3.0 and (outcome in {"SL", "LOSS"} or (pnl is not None and pnl < 0)):
            observation = _normalized_observation(
                source,
                "trade_outcome",
                "high_confidence_loss",
                score,
                row,
                entity=symbol,
                timestamp=row.get("closed_at") or timestamp,
                severity="HIGH",
            )
            observation["source_type"] = "NATIVE_EXPERIENCE"
            observations.append(observation)
    return observations


def _observations_from_backtest_report(source, payload, timestamp):
    observations = []
    if not isinstance(payload, dict):
        return observations
    for section, data in payload.items():
        if not isinstance(data, dict):
            continue
        status = data.get("status")
        if status:
            observations.append(
                _normalized_observation(
                    source,
                    "backtest_validation",
                    "validation_status",
                    status,
                    data,
                    entity=section,
                    timestamp=timestamp,
                    severity=_severity_from_text(status),
                )
            )
        for metric in ("sample_size", "win_rate", "quality_score", "expectancy", "profit_factor", "validation_score", "consistency_score"):
            if metric in data:
                value = _to_float(data.get(metric))
                severity = "MEDIUM" if value in (0, 0.0) and metric in {"sample_size", "quality_score", "validation_score"} else "LOW"
                observations.append(
                    _normalized_observation(
                        source,
                        "backtest_validation",
                        metric,
                        value,
                        data,
                        entity=section,
                        timestamp=timestamp,
                        severity=severity,
                    )
                )
    return observations


def _observations_from_no_trade(source, payload, timestamp):
    observations = []
    if not isinstance(payload, dict):
        return observations
    warning = payload.get("no_trade_warning") or payload.get("trade_permission")
    if warning:
        severity = "HIGH" if str(warning).upper() not in {"NONE", "ALLOW"} else "LOW"
        observations.append(
            _normalized_observation(
                source,
                "no_trade",
                "no_trade_warning",
                warning,
                payload,
                entity=payload.get("symbol", "market"),
                timestamp=payload.get("generated_at") or timestamp,
                severity=severity,
            )
        )
    for section, data in payload.items():
        if isinstance(data, dict):
            for key, value in data.items():
                if key.startswith("is_") and value:
                    observations.append(
                        _normalized_observation(
                            source,
                            "no_trade",
                            key,
                            value,
                            data,
                            entity=section,
                            timestamp=payload.get("generated_at") or timestamp,
                            severity="HIGH",
                        )
                    )
    return observations


def _observations_from_report_vault(source, payload, timestamp):
    if not isinstance(payload, dict):
        return []
    observations = []
    summary = payload.get("summary")
    if summary:
        observations.append(
            _normalized_observation(
                source,
                "report_vault_intelligence",
                "aggregated_summary",
                summary,
                {
                    "packet_hash": payload.get("packet_hash"),
                    "report_count": payload.get("report_count"),
                    "source_workers": payload.get("source_workers", []),
                    "trusted_summarized_input": payload.get("trusted_summarized_input"),
                },
                entity="report_aggregator",
                timestamp=payload.get("generated_at") or timestamp,
                severity="MEDIUM" if payload.get("report_count") else "LOW",
            )
        )
    for finding in (payload.get("merged_findings") or [])[:20]:
        observations.append(
            _normalized_observation(
                source,
                "report_vault_intelligence",
                "merged_finding",
                finding.get("finding") if isinstance(finding, dict) else finding,
                finding,
                entity="report_aggregator",
                timestamp=payload.get("generated_at") or timestamp,
                severity=(finding.get("severity") if isinstance(finding, dict) else "MEDIUM"),
            )
        )
    for conflict in (payload.get("conflicts") or [])[:20]:
        observations.append(
            _normalized_observation(
                source,
                "report_vault_intelligence",
                "report_conflict",
                conflict.get("subject") if isinstance(conflict, dict) else conflict,
                conflict,
                entity="report_aggregator",
                timestamp=payload.get("generated_at") or timestamp,
                severity="HIGH",
            )
        )
    return observations


def _observations_from_knowledge_vault(source, payload, timestamp):
    if not isinstance(payload, dict):
        return []
    observations = []
    generated_at = payload.get("generated_at") or timestamp
    for item in (payload.get("observations") or [])[:100]:
        if not isinstance(item, dict):
            continue
        observations.append(
            _normalized_observation(
                source,
                item.get("type") or "knowledge_vault_intelligence",
                item.get("metric") or "knowledge_item",
                item.get("value"),
                {
                    "evidence": item.get("evidence", []),
                    "safety": item.get("safety"),
                    "packet_hash": payload.get("packet_hash"),
                },
                entity=item.get("entity") or "knowledge_vault",
                timestamp=generated_at,
                severity=item.get("severity") or "LOW",
            )
        )
    for warning in (payload.get("extraction_warnings") or [])[:50]:
        observations.append(
            _normalized_observation(
                source,
                "knowledge_vault_intelligence",
                "insufficient_extraction",
                warning.get("reason") if isinstance(warning, dict) else warning,
                warning,
                entity=(warning.get("source_file") if isinstance(warning, dict) else "knowledge_vault"),
                timestamp=generated_at,
                severity="MEDIUM",
            )
        )
    if not observations:
        observations.append(
            _normalized_observation(
                source,
                "knowledge_vault_intelligence",
                "packet_seen",
                payload.get("status"),
                {
                    "run_stats": payload.get("run_stats", {}),
                    "packet_hash": payload.get("packet_hash"),
                    "note": "insufficient extraction: no knowledge observations available",
                },
                entity="knowledge_vault",
                timestamp=generated_at,
                severity="LOW",
            )
        )
    return observations


def _observations_from_experience_vault(source, payload, timestamp):
    if not isinstance(payload, dict):
        return []
    observations = []
    generated_at = payload.get("generated_at") or timestamp
    packet_hash = payload.get("packet_hash")
    for item in (payload.get("observations") or [])[:150]:
        if not isinstance(item, dict):
            continue
        evidence = {
            "evidence": item.get("evidence", []),
            "lesson": item.get("lesson"),
            "safety": item.get("safety"),
            "packet_hash": packet_hash,
            "source_type": "EXTERNAL_EXPERIENCE",
            "trust_level": "IMPORTED_UNVALIDATED",
        }
        observation = _normalized_observation(
            source,
            item.get("type") or "external_experience",
            item.get("metric") or "imported_lesson",
            item.get("value"),
            evidence,
            entity=item.get("entity") or "experience_vault",
            timestamp=generated_at,
            severity=item.get("severity") or "MEDIUM",
        )
        observation["source_type"] = "EXTERNAL_EXPERIENCE"
        observation["trust_level"] = "IMPORTED_UNVALIDATED"
        observation["validation_status"] = item.get("validation_status", "UNVALIDATED")
        observation["external_experience_status"] = item.get("status", "UNVALIDATED")
        observations.append(observation)

    for warning in (payload.get("extraction_warnings") or [])[:50]:
        observation = _normalized_observation(
            source,
            "external_experience",
            "insufficient_extraction",
            warning.get("reason") if isinstance(warning, dict) else warning,
            {
                "warning": warning,
                "packet_hash": packet_hash,
                "source_type": "EXTERNAL_EXPERIENCE",
                "trust_level": "IMPORTED_UNVALIDATED",
            },
            entity=(warning.get("source_file") if isinstance(warning, dict) else "experience_vault"),
            timestamp=generated_at,
            severity="MEDIUM",
        )
        observation["source_type"] = "EXTERNAL_EXPERIENCE"
        observation["trust_level"] = "IMPORTED_UNVALIDATED"
        observation["validation_status"] = "UNVALIDATED"
        observations.append(observation)

    if not observations:
        observation = _normalized_observation(
            source,
            "external_experience",
            "packet_seen",
            payload.get("status"),
            {
                "run_stats": payload.get("run_stats", {}),
                "packet_hash": packet_hash,
                "source_type": "EXTERNAL_EXPERIENCE",
                "trust_level": "IMPORTED_UNVALIDATED",
                "note": "external experience packet contains no lessons yet",
            },
            entity="experience_vault",
            timestamp=generated_at,
            severity="LOW",
        )
        observation["source_type"] = "EXTERNAL_EXPERIENCE"
        observation["trust_level"] = "IMPORTED_UNVALIDATED"
        observation["validation_status"] = "UNVALIDATED"
        observations.append(observation)
    return observations


def _observations_from_payload(source, content, meta, timestamp):
    observations = []
    lower_source = source.lower()
    if source.endswith("latest_aggregated_packet.json"):
        observations.extend(_observations_from_report_vault(source, content, timestamp))
    elif source.endswith("knowledge_to_consciousness_packet.json"):
        observations.extend(_observations_from_knowledge_vault(source, content, timestamp))
    elif source.endswith("external_experience_packet.json"):
        observations.extend(_observations_from_experience_vault(source, content, timestamp))
    elif source.endswith("worker_health.json"):
        observations.extend(_observations_from_worker_health(source, content, timestamp))
    elif "/intelligence_state/" in lower_source:
        observations.extend(_observations_from_intelligence_state(source, content, timestamp))
    elif source.endswith("trade_outcomes.csv"):
        observations.extend(_observations_from_trade_outcomes(source, content, timestamp))
    elif "backtesting_validation" in lower_source:
        observations.extend(_observations_from_backtest_report(source, content, timestamp))
    elif "/no_trade/" in lower_source:
        observations.extend(_observations_from_no_trade(source, content, timestamp))
    observations.extend(_flatten_numeric_report(source, content, timestamp))
    if not observations:
        observations.append(
            _normalized_observation(
                source,
                meta.get("kind", "file"),
                "file_processed",
                meta.get("record_count") or meta.get("line_count") or meta.get("size_bytes"),
                {"summary": meta},
                entity=Path(source).stem,
                timestamp=timestamp,
                severity="LOW",
            )
        )
    return observations


def _read_text(path):
    with path.open("r", encoding="utf-8", errors="replace") as source_file:
        lines = source_file.readlines()
    tail = "".join(lines[-120:])
    return tail, {"line_count": len(lines)}


def _packet_for_path(path):
    stat = path.stat()
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            content, meta = _read_json(path)
            kind = "json"
        elif suffix == ".csv":
            content, meta = _read_csv(path)
            kind = "csv"
        else:
            content, meta = _read_text(path)
            kind = "text"
        status = "ok"
        error = None
    except Exception as exc:
        content = None
        meta = {}
        kind = suffix.lstrip(".") or "unknown"
        status = "error"
        error = str(exc)

    source = str(path).replace("\\", "/")
    meta["kind"] = kind
    meta["size_bytes"] = stat.st_size
    meta["modified_at"] = stat.st_mtime
    if status != "ok":
        return [
            _normalized_observation(
                source,
                "read_error",
                "source_read_error",
                error,
                {"error": error},
                entity=path.stem,
                timestamp=stat.st_mtime,
                severity="HIGH",
            )
        ]
    return _observations_from_payload(source, content, meta, stat.st_mtime)


def collect_observations(include_seen=False):
    all_observations = []
    seen = set()
    processed = load_processed_observations()
    processed_hashes = processed.setdefault("processed_hashes", {})
    now_ts = time.time()
    missing_patterns = []
    for pattern in DATA_SOURCES:
        matches = [Path(match) for match in glob.glob(pattern)]
        if not matches:
            missing_patterns.append(pattern)
        for path in sorted(matches):
            if path in seen or not path.exists() or not path.is_file():
                continue
            seen.add(path)
            all_observations.extend(_packet_for_path(path))

    for pattern in missing_patterns:
        if pattern in CRITICAL_PATTERNS:
            all_observations.append(
                _normalized_observation(
                    pattern,
                    "missing_critical_report",
                    "missing_source",
                    pattern,
                    {"pattern": pattern},
                    entity=Path(pattern).stem,
                    timestamp=now_ts,
                    severity="HIGH",
                )
            )

    new_observations = []
    unchanged_count = 0
    for observation in all_observations:
        content_hash = observation["content_hash"]
        if include_seen or content_hash not in processed_hashes:
            new_observations.append(observation)
        else:
            unchanged_count += 1
        processed_hashes[content_hash] = {
            "source": observation.get("source"),
            "metric": observation.get("metric"),
            "last_seen": now_ts,
        }

    processed["last_updated"] = now_ts
    processed["processed_count"] = len(processed_hashes)
    save_processed_observations(processed)
    return {
        "status": "ok",
        "observations": new_observations,
        "all_observation_count": len(all_observations),
        "observation_count": len(new_observations),
        "unchanged_observation_count": unchanged_count,
        "observation_hash": stable_hash(new_observations),
        "missing_patterns": missing_patterns,
        "processed_ledger_path": str(PROCESSED_OBSERVATIONS_PATH),
    }
