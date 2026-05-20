import re

from .hashing import stable_hash


FIELD_PATTERNS = {
    "setup_type": r"(?:setup|pattern|strategy)\s*[:=-]\s*([^\n.;]{3,80})",
    "trade_result": r"(?:result|outcome|trade result|pnl)\s*[:=-]\s*([^\n.;]{2,80})",
    "entry_reason": r"(?:entry|entry reason|reason for entry|trigger)\s*[:=-]\s*([^\n.;]{3,120})",
    "failure_success_reason": r"(?:failure|success|worked because|failed because|reason)\s*[:=-]\s*([^\n.;]{3,140})",
    "regime": r"(?:regime|market regime|environment)\s*[:=-]\s*([^\n.;]{3,80})",
    "stock_behavior": r"(?:stock behavior|personality|behavior)\s*[:=-]\s*([^\n.;]{3,120})",
    "liquidity_condition": r"(?:liquidity|volume|spread|depth)\s*[:=-]\s*([^\n.;]{3,120})",
    "news_context": r"(?:news|event|catalyst)\s*[:=-]\s*([^\n.;]{3,120})",
    "trap_evidence": r"(?:trap|manipulation|fakeout|stop run|sweep)\s*[:=-]\s*([^\n.;]{3,140})",
    "no_trade_lesson": r"(?:no trade|avoid|skip)\s*[:=-]\s*([^\n.;]{3,140})",
    "confidence_lesson": r"(?:confidence|conviction|calibration)\s*[:=-]\s*([^\n.;]{3,140})",
    "causal_lesson": r"(?:cause|causal|because)\s*[:=-]\s*([^\n.;]{3,140})",
}

CATEGORY_FIELDS = {
    "market_regimes": ("regime",),
    "stock_personality": ("stock_behavior",),
    "setup_reliability": ("setup_type", "trade_result", "failure_success_reason"),
    "failure_memory": ("failure_success_reason",),
    "liquidity_traps": ("liquidity_condition", "trap_evidence"),
    "manipulation_patterns": ("trap_evidence",),
    "news_reactions": ("news_context",),
    "confidence_calibration": ("confidence_lesson",),
    "no_trade_cases": ("no_trade_lesson",),
    "causal_cases": ("causal_lesson",),
}

KEYWORD_FIELDS = {
    "setup_type": ("breakout", "pullback", "reversal", "opening range", "trend", "mean reversion", "gap"),
    "trade_result": ("win", "winner", "loss", "loser", "target hit", "stop loss", "breakeven"),
    "entry_reason": ("entry", "trigger", "confirmation", "break above", "break below", "retest"),
    "failure_success_reason": ("failed", "worked", "success", "failure", "invalidated", "follow through"),
    "regime": ("bull", "bear", "sideways", "volatile", "range", "trending", "crisis"),
    "stock_behavior": ("relative strength", "relative weakness", "choppy", "clean trend", "whipsaw"),
    "liquidity_condition": ("illiquid", "liquid", "thin", "spread", "volume spike", "absorption"),
    "news_context": ("earnings", "guidance", "rate", "inflation", "policy", "downgrade", "upgrade"),
    "trap_evidence": ("trap", "fakeout", "stop run", "liquidity sweep", "spoof", "manipulation"),
    "no_trade_lesson": ("avoid", "skip", "no trade", "stand aside", "do not trade"),
    "confidence_lesson": ("overconfident", "underconfident", "confidence", "calibration", "position size"),
    "causal_lesson": ("because", "caused", "led to", "therefore", "causal"),
}

LESSON_LABELS = {
    "setup_type": "setup type",
    "trade_result": "trade result",
    "entry_reason": "reason for entry",
    "failure_success_reason": "reason for failure/success",
    "regime": "regime",
    "stock_behavior": "stock behavior",
    "liquidity_condition": "liquidity condition",
    "news_context": "news context",
    "trap_evidence": "trap/manipulation evidence",
    "no_trade_lesson": "no-trade lesson",
    "confidence_lesson": "confidence calibration lesson",
    "causal_lesson": "causal lesson",
}


def _clean(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip(" -:\t")
    return value[:300]


def _evidence_snippet(text, pattern):
    lower = text.lower()
    index = lower.find(pattern.lower())
    if index < 0:
        index = 0
    start = max(0, index - 180)
    end = min(len(text), index + 420)
    return _clean(text[start:end])


def _extract_fields(text):
    fields = {}
    for field, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            fields[field] = _clean(match.group(1))
    lower = text.lower()
    for field, keywords in KEYWORD_FIELDS.items():
        if field in fields:
            continue
        for keyword in keywords:
            if keyword in lower:
                fields[field] = _evidence_snippet(text, keyword)
                break
    return fields


def _polarity(field, value):
    lower = str(value or "").lower()
    if field == "trade_result":
        if any(token in lower for token in ("loss", "loser", "stop", "failed", "negative")):
            return "NEGATIVE"
        if any(token in lower for token in ("win", "winner", "target", "profit", "positive")):
            return "POSITIVE"
    if any(token in lower for token in ("avoid", "skip", "no trade", "failed", "trap", "loss", "overconfident")):
        return "NEGATIVE"
    if any(token in lower for token in ("worked", "success", "confirmed", "reliable", "target")):
        return "POSITIVE"
    return "NEUTRAL"


def _importance(field, category):
    score = 0.45
    if field in {"failure_success_reason", "trap_evidence", "no_trade_lesson", "causal_lesson"}:
        score += 0.2
    if field in CATEGORY_FIELDS.get(category, ()):
        score += 0.15
    return round(min(score, 0.95), 3)


def extract_lessons(chunk, category):
    text = chunk.get("text", "")
    fields = _extract_fields(text)
    lessons = []
    for field, value in fields.items():
        if not value or len(value) < 8:
            continue
        evidence = {
            "source_file": chunk.get("source_path"),
            "category": category,
            "chunk_id": chunk.get("chunk_id"),
            "chunk_hash": chunk.get("text_hash"),
            "snippet": _evidence_snippet(text, value[:40]),
        }
        subject_parts = [
            field,
            fields.get("setup_type"),
            fields.get("regime"),
            fields.get("stock_behavior"),
        ]
        subject_key = " ".join(_clean(part).lower() for part in subject_parts if part)
        lesson = {
            "source_type": "EXTERNAL_EXPERIENCE",
            "trust_level": "IMPORTED_UNVALIDATED",
            "validation_status": "UNVALIDATED",
            "lesson_type": field,
            "label": LESSON_LABELS.get(field, field),
            "text": f"{LESSON_LABELS.get(field, field)}: {value}",
            "value": value,
            "setup_type": fields.get("setup_type"),
            "trade_result": fields.get("trade_result"),
            "entry_reason": fields.get("entry_reason"),
            "failure_success_reason": fields.get("failure_success_reason"),
            "regime": fields.get("regime"),
            "stock_behavior": fields.get("stock_behavior"),
            "liquidity_condition": fields.get("liquidity_condition"),
            "news_context": fields.get("news_context"),
            "trap_evidence": fields.get("trap_evidence"),
            "no_trade_lesson": fields.get("no_trade_lesson"),
            "confidence_lesson": fields.get("confidence_lesson"),
            "causal_lesson": fields.get("causal_lesson"),
            "polarity": _polarity(field, value),
            "category": category,
            "importance": _importance(field, category),
            "seen_count": 1,
            "status": "UNVALIDATED",
            "evidence": [evidence],
        }
        lesson["subject_key"] = stable_hash(subject_key or lesson["text"])[:24]
        lesson["lesson_hash"] = stable_hash({"field": field, "value": value, "evidence": evidence})[:24]
        lessons.append(lesson)
    return lessons

