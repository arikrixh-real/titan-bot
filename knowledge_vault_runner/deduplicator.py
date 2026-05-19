import re


def idea_key(text):
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    words = [word for word in normalized.split() if len(word) > 2]
    return " ".join(words[:18])


def merge_items(existing, new_items):
    by_key = {item.get("idea_key") or idea_key(item.get("text")): item for item in existing if isinstance(item, dict)}
    added = 0
    updated = 0
    for item in new_items:
        key = item.get("idea_key") or idea_key(item.get("text"))
        if not key:
            continue
        item["idea_key"] = key
        current = by_key.get(key)
        if not current:
            by_key[key] = item
            added += 1
            continue
        current["importance"] = max(float(current.get("importance", 0)), float(item.get("importance", 0)))
        current["seen_count"] = int(current.get("seen_count", 1)) + 1
        evidence = current.setdefault("evidence", [])
        for entry in item.get("evidence", []):
            if entry not in evidence:
                evidence.append(entry)
        current["evidence"] = evidence[:12]
        updated += 1
    merged = sorted(by_key.values(), key=lambda row: row.get("importance", 0), reverse=True)
    return merged, {"added": added, "updated": updated, "total": len(merged)}

