import json
from pathlib import Path

from ranking_mutation_audit import SAFETY_FLAGS, run_ranking_mutation_audit
from ranking_ownership_guard import AUTHORITATIVE_RANKING_OWNER, build_ranking_ownership_status
from utils.market_hours import as_ist_datetime


INTEGRITY_PATH = Path("data") / "runtime" / "ranking_integrity_status.json"


def build_ranking_integrity_status(path=None, now=None):
    if path is None:
        path = INTEGRITY_PATH
    now_ist = as_ist_datetime(now)
    audit = run_ranking_mutation_audit(now=now_ist)
    ownership = build_ranking_ownership_status(now=now_ist)
    dangerous = audit.get("dangerous_live_overrides") or []
    duplicate = audit.get("duplicate_rank_writers") or {}
    duplicate_runtime = audit.get("duplicate_runtime_rank_writers") or {}
    conflicting = sorted(
        {
            item.get("component")
            for item in dangerous
            if item.get("component") != AUTHORITATIVE_RANKING_OWNER
        }
    )
    duplicate_live = {
        field: files
        for field, files in duplicate_runtime.items()
        if field not in {"final_score", "rank_score", "daily_alert_rank"}
    }
    ranking_chain_valid = bool(
        ownership.get("authoritative_ranking_owner") == AUTHORITATIVE_RANKING_OWNER
        and not dangerous
        and not duplicate_live
    )
    penalty = (len(conflicting) * 20) + (len(duplicate_live) * 10)
    ranking_integrity_score = round(max(0.0, 100.0 - penalty), 2)
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "ranking_integrity_score": ranking_integrity_score,
        "authoritative_owner": AUTHORITATIVE_RANKING_OWNER,
        "conflicting_mutators": conflicting,
        "duplicate_rank_writers": duplicate,
        "advisory_only_mutators": audit.get("advisory_only_mutators") or [],
        "dangerous_live_overrides": dangerous,
        "ranking_chain_valid": ranking_chain_valid,
        "ownership_status_path": "data/runtime/ranking_ownership_status.json",
        "mutation_audit_path": "data/runtime/ranking_mutation_audit.json",
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_ranking_integrity_status(), indent=2, sort_keys=True))
