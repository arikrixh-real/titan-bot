from .concept_extractor import extract_concepts


LESSON_TYPES = {"concept", "rule", "risk_warning", "strategy_idea", "market_psychology", "institutional_concept", "testable_hypothesis"}


def extract_lessons(chunk):
    return [item for item in extract_concepts(chunk) if item.get("type") in LESSON_TYPES]
