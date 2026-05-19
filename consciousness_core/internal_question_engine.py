from consciousness_core.state import now_ist


QUESTIONS = (
    "What is happening now?",
    "Why is it happening?",
    "What evidence supports this?",
    "What contradicts this?",
    "What did TITAN miss?",
    "What failed before?",
    "What should TITAN learn next?",
    "What should TITAN improve next?",
    "What should be blocked or reduced?",
)


def generate_internal_questions(observation_packet, state=None):
    count = observation_packet.get("observation_count", 0)
    missing = observation_packet.get("missing_patterns", [])
    focus = (state or {}).get("current_focus", "system continuity")
    return [
        {
            "question": question,
            "context": {
                "current_focus": focus,
                "observations_available": count,
                "missing_source_count": len(missing),
            },
            "created_at": now_ist(),
            "status": "OPEN",
        }
        for question in QUESTIONS
    ]

