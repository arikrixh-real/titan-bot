import time

from .hashing import stable_hash


def build_external_experience_packet(memory, stats, warnings):
    top_lessons = sorted(memory, key=lambda item: item.get("importance", 0), reverse=True)[:100]
    observations = []
    for lesson in top_lessons:
        observations.append(
            {
                "source_type": "EXTERNAL_EXPERIENCE",
                "trust_level": "IMPORTED_UNVALIDATED",
                "validation_status": lesson.get("validation_status", "UNVALIDATED"),
                "type": "external_experience",
                "metric": lesson.get("lesson_type"),
                "value": lesson.get("text"),
                "entity": lesson.get("setup_type") or lesson.get("stock_behavior") or lesson.get("category"),
                "severity": "HIGH" if lesson.get("status") == "CONTRADICTION" else "MEDIUM",
                "actionability_score": lesson.get("importance", 0),
                "status": lesson.get("status", "UNVALIDATED"),
                "evidence": lesson.get("evidence", []),
                "lesson": lesson,
                "safety": "evidence_only_core_must_validate_before_merge",
            }
        )

    packet = {
        "status": "ok",
        "generated_at": time.time(),
        "runner": "experience_vault_runner",
        "source_type": "EXTERNAL_EXPERIENCE",
        "trust_level": "IMPORTED_UNVALIDATED",
        "safety": {
            "live_mutation": False,
            "direct_strategy_changes": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
            "risk_override": False,
            "native_trade_import": False,
            "core_validation_required": True,
            "packet_type": "external_experience_evidence_for_sandbox_validation",
        },
        "run_stats": stats,
        "extraction_warnings": warnings[:100],
        "lessons": top_lessons,
        "observations": observations,
    }
    packet["packet_hash"] = stable_hash(
        {
            "lessons": top_lessons,
            "warnings": warnings[:100],
            "stats": stats,
            "source_type": "EXTERNAL_EXPERIENCE",
        }
    )
    return packet

