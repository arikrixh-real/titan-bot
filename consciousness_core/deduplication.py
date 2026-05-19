import re

from consciousness_core.state import stable_hash


SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
PRIORITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def semantic_key(*parts):
    return stable_hash([normalize_text(part) for part in parts])


def proposal_key(proposal):
    return stable_hash(
        [
            normalize_text(proposal.get("target_engine")),
            normalize_text(proposal.get("suggested_action")),
            proposal.get("parameter_hint") or {},
        ]
    )


def stronger_label(left, right, ranks):
    left_value = str(left or "").upper()
    right_value = str(right or "").upper()
    if ranks.get(right_value, 0) > ranks.get(left_value, 0):
        return right_value
    return left_value or right_value


def append_evidence(existing, new):
    merged = list(existing or [])
    for item in new or []:
        merged.append(item)
    return merged
