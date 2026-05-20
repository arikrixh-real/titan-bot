import re

from .hashing import stable_hash


def _normalized_words(text):
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    return " ".join(word for word in normalized.split() if len(word) > 2)


def _merge_key(item):
    key_basis = [
        item.get("lesson_type"),
        item.get("setup_type"),
        item.get("regime"),
        item.get("stock_behavior"),
        item.get("category"),
        " ".join(_normalized_words(item.get("value", "")).split()[:12]),
    ]
    return stable_hash("|".join(str(part or "") for part in key_basis))[:24]


def _subject_key(item):
    return item.get("subject_key") or stable_hash(
        {
            "lesson_type": item.get("lesson_type"),
            "setup_type": item.get("setup_type"),
            "regime": item.get("regime"),
            "stock_behavior": item.get("stock_behavior"),
            "category": item.get("category"),
        }
    )[:24]


def _is_conflict(existing, item):
    return (
        existing.get("lesson_type") == item.get("lesson_type")
        and _subject_key(existing) == _subject_key(item)
        and existing.get("polarity") in {"POSITIVE", "NEGATIVE"}
        and item.get("polarity") in {"POSITIVE", "NEGATIVE"}
        and existing.get("polarity") != item.get("polarity")
    )


def merge_lessons(existing, new_items):
    by_key = {_merge_key(item): item for item in existing if isinstance(item, dict)}
    subjects = {}
    for item in by_key.values():
        subjects.setdefault(_subject_key(item), []).append(item)

    added = 0
    updated = 0
    contradictions = 0
    for item in new_items:
        key = _merge_key(item)
        current = by_key.get(key)
        if current:
            current["importance"] = max(float(current.get("importance", 0)), float(item.get("importance", 0)))
            current["seen_count"] = int(current.get("seen_count", 1)) + 1
            evidence = current.setdefault("evidence", [])
            for entry in item.get("evidence", []):
                if entry not in evidence:
                    evidence.append(entry)
            current["evidence"] = evidence[:25]
            updated += 1
            continue

        conflicting = [
            subject_item
            for subject_item in subjects.get(_subject_key(item), [])
            if _is_conflict(subject_item, item)
        ]
        if conflicting:
            item["status"] = "CONTRADICTION"
            item["contradiction_with"] = [entry.get("lesson_hash") for entry in conflicting]
            for entry in conflicting:
                entry["status"] = "CONTRADICTION"
                links = entry.setdefault("contradiction_with", [])
                if item.get("lesson_hash") not in links:
                    links.append(item.get("lesson_hash"))
            contradictions += 1

        by_key[key] = item
        subjects.setdefault(_subject_key(item), []).append(item)
        added += 1

    merged = sorted(by_key.values(), key=lambda row: row.get("importance", 0), reverse=True)
    return merged, {
        "added": added,
        "updated": updated,
        "contradictions": contradictions,
        "total": len(merged),
    }

