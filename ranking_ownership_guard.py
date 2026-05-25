import json
from pathlib import Path

from ranking_mutation_audit import AUTHORITATIVE_OWNER, SAFETY_FLAGS, run_ranking_mutation_audit
from utils.market_hours import as_ist_datetime


OWNERSHIP_PATH = Path("data") / "runtime" / "ranking_ownership_status.json"
AUTHORITATIVE_RANKING_OWNER = "final_decision_engine"
ADVISORY_CONTRIBUTORS = [
    "setup_engine",
    "meta_intelligence",
    "data_advantage",
    "replay",
    "roadmap_sidecars",
    "reinforcement_learning",
    "research_systems",
]


def classify_ranking_payload(source, payload):
    payload = payload if isinstance(payload, dict) else {}
    source = str(source or "")
    authoritative = source == AUTHORITATIVE_RANKING_OWNER
    live_rank_fields = {
        "blended_rank_score",
        "new_blended_rank_score",
        "final_master_rank",
        "final_cross_asset_rank",
        "final_portfolio_rank",
        "final_no_trade_rank",
    }
    attempted_override_fields = sorted(field for field in live_rank_fields if field in payload)
    return {
        "source": source,
        "authoritative_live_owner": authoritative,
        "advisory_only": not authoritative,
        "attempted_live_rank_override": bool(attempted_override_fields and not authoritative),
        "attempted_override_fields": attempted_override_fields if not authoritative else [],
        "guard_action": "allow_authoritative" if authoritative else "visibility_only_no_silent_override",
    }


def build_ranking_ownership_status(path=None, now=None):
    if path is None:
        path = OWNERSHIP_PATH
    now_ist = as_ist_datetime(now)
    audit = run_ranking_mutation_audit(now=now_ist)
    setup_mutations = [
        item for item in audit.get("mutations", [])
        if item.get("component") == "setup_engine"
    ]
    roadmap_mutations = [
        item for item in audit.get("mutations", [])
        if item.get("component") == "roadmap_sidecar"
    ]
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "authoritative_ranking_owner": AUTHORITATIVE_RANKING_OWNER,
        "authoritative_owner_path": AUTHORITATIVE_OWNER,
        "authoritative_live_ranking": True,
        "ownership_hierarchy": {
            AUTHORITATIVE_RANKING_OWNER: {
                "authoritative_live_ranking": True,
                "may_override_live_rank": True,
                "may_select_final_output": True,
            },
            "advisory_contributors": {
                name: {
                    "advisory_only": True,
                    "contributes_to_ranking": name == "setup_engine",
                    "authoritative_live_owner": False,
                    "may_suggest": True,
                    "may_annotate": True,
                    "may_directly_override_live_ranking": False,
                }
                for name in ADVISORY_CONTRIBUTORS
            },
        },
        "setup_engine_classification": {
            "contributes_to_ranking": True,
            "authoritative_live_owner": False,
            "mutation_count": len(setup_mutations),
        },
        "roadmap_phase_classification": {
            "advisory_only": True,
            "affects_live_ranking": False,
            "mutation_count": len(roadmap_mutations),
        },
        "audit_path": "data/runtime/ranking_mutation_audit.json",
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_ranking_ownership_status(), indent=2, sort_keys=True))
