import csv
import json
import re
from pathlib import Path

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

STRUCTURED_FIELDS = {
    "symbol",
    "setup_type",
    "side",
    "regime",
    "outcome",
    "outcome_reason",
    "lesson_learned",
    "reason",
    "confidence",
    "score",
    "rr",
    "trade_result",
}

FIELD_ALIASES = {
    "regime": ("regime", "market_regime", "trend", "environment"),
    "outcome": ("outcome", "result", "trade_result"),
    "trade_result": ("trade_result", "result", "outcome"),
    "reason": ("reason", "entry_reason", "entry", "trigger"),
    "confidence": ("confidence", "confidence_score", "conviction"),
    "score": ("score", "setup_score", "signal_score"),
    "rr": ("rr", "r_multiple", "risk_reward", "risk_reward_ratio"),
}

POSITIVE_OUTCOMES = {"WIN", "PROFIT", "TARGET_HIT", "SUCCESS", "GAIN"}
NEGATIVE_OUTCOMES = {"LOSS", "STOP_LOSS", "SL_HIT", "FAILED", "FAILURE", "NEGATIVE"}
NEUTRAL_OUTCOMES = {"FLAT", "BREAKEVEN", "NO_FOLLOWUP", "INVALID_LEVELS", "INCONCLUSIVE", "UNKNOWN", ""}


def _clean(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip(" -:\t")
    return value[:300]


def _clean_structured(value, max_chars=300):
    if value in (None, ""):
        return None
    cleaned = _clean(value)
    return cleaned[:max_chars] if cleaned else None


def _get_field(row, field):
    keys = FIELD_ALIASES.get(field, (field,))
    normalized = {str(key or "").strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _normalize_outcome(value):
    cleaned = _clean_structured(value, 80)
    if not cleaned:
        return "UNKNOWN"
    normalized = re.sub(r"[^A-Z0-9]+", "_", cleaned.upper()).strip("_")
    if normalized in POSITIVE_OUTCOMES:
        return "WIN"
    if normalized in NEGATIVE_OUTCOMES:
        return "LOSS"
    if normalized in {"BREAK_EVEN", "BREAKEVEN"}:
        return "FLAT"
    if normalized in NEUTRAL_OUTCOMES:
        return normalized or "UNKNOWN"
    if any(token in normalized for token in ("WIN", "PROFIT", "TARGET", "GAIN")):
        return "WIN"
    if any(token in normalized for token in ("LOSS", "STOP", "FAILED", "FAIL")):
        return "LOSS"
    return normalized


def _polarity_from_outcome(outcome):
    normalized = _normalize_outcome(outcome)
    if normalized in POSITIVE_OUTCOMES or normalized == "WIN":
        return "POSITIVE"
    if normalized in NEGATIVE_OUTCOMES or normalized == "LOSS":
        return "NEGATIVE"
    return "NEUTRAL"


def _coerce_number(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return _clean_structured(value, 80)


def _read_structured_rows(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", errors="replace", newline="") as source_file:
            return [dict(row) for row in csv.DictReader(source_file)]
    if suffix == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8", errors="replace") as source_file:
            for line_number, line in enumerate(source_file, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    payload["_line_number"] = line_number
                    rows.append(payload)
        return rows
    return []


def _structured_record(row):
    outcome = _normalize_outcome(_get_field(row, "outcome"))
    trade_result = _normalize_outcome(_get_field(row, "trade_result") or outcome)
    record = {
        "symbol": _clean_structured(_get_field(row, "symbol"), 80),
        "setup_type": _clean_structured(_get_field(row, "setup_type"), 120),
        "side": _clean_structured(_get_field(row, "side"), 20),
        "regime": _clean_structured(_get_field(row, "regime"), 120),
        "outcome": outcome,
        "outcome_reason": _clean_structured(_get_field(row, "outcome_reason"), 300),
        "lesson_learned": _clean_structured(_get_field(row, "lesson_learned"), 300),
        "reason": _clean_structured(_get_field(row, "reason"), 300),
        "confidence": _coerce_number(_get_field(row, "confidence")),
        "score": _coerce_number(_get_field(row, "score")),
        "rr": _coerce_number(_get_field(row, "rr")),
        "trade_result": trade_result,
    }
    if not record["regime"]:
        record["regime"] = _clean_structured(_get_field(row, "trend"), 120)
    return record


def _structured_text(record, lesson_type):
    setup = record.get("setup_type") or "unknown setup"
    symbol = record.get("symbol") or "unknown symbol"
    outcome = record.get("outcome") or "UNKNOWN"
    if lesson_type == "failure_success_reason":
        return record.get("outcome_reason") or record.get("lesson_learned") or f"{setup} on {symbol} resolved as {outcome}."
    if lesson_type == "confidence_lesson":
        confidence = record.get("confidence")
        score = record.get("score")
        basis = record.get("reason") or record.get("lesson_learned") or "structured simulated record"
        return f"confidence={confidence}; score={score}; outcome={outcome}; basis={basis}"
    if lesson_type == "causal_lesson":
        parts = [record.get("reason"), record.get("outcome_reason"), record.get("lesson_learned")]
        return " -> ".join(part for part in parts if part) or f"{setup} on {symbol} produced {outcome}."
    if lesson_type == "stock_behavior":
        regime = record.get("regime") or "unknown regime"
        side = record.get("side") or "unknown side"
        return f"{symbol} {side} {setup} in {regime} resolved as {outcome}."
    if lesson_type == "no_trade_lesson":
        return record.get("lesson_learned") or record.get("outcome_reason") or f"Do not promote {setup} on {symbol} without validation."
    return record.get("lesson_learned") or record.get("reason") or f"{setup} on {symbol} resolved as {outcome}."


def _structured_lesson_types(record):
    outcome = _normalize_outcome(record.get("outcome"))
    lesson_types = ["failure_success_reason", "causal_lesson", "stock_behavior"]
    if record.get("confidence") is not None or record.get("score") is not None:
        lesson_types.append("confidence_lesson")
    if outcome not in {"WIN"}:
        lesson_types.append("no_trade_lesson")
    return lesson_types


def _structured_importance(lesson_type, record):
    score = 0.65
    if lesson_type in {"failure_success_reason", "causal_lesson", "no_trade_lesson"}:
        score += 0.1
    if record.get("outcome") in {"WIN", "LOSS"}:
        score += 0.05
    return round(min(score, 0.95), 3)


def extract_structured_import_lessons(path, source_path, category):
    lessons = []
    for row_index, row in enumerate(_read_structured_rows(path)):
        record = _structured_record(row)
        if not any(record.get(field) for field in ("symbol", "setup_type", "reason", "lesson_learned")):
            continue
        row_hash = stable_hash({key: value for key, value in record.items() if key in STRUCTURED_FIELDS})
        polarity = _polarity_from_outcome(record.get("outcome"))
        evidence = {
            "source_file": source_path,
            "category": category,
            "row_index": row_index,
            "row_hash": row_hash,
            "snippet": _clean_structured(
                " | ".join(
                    str(part)
                    for part in (
                        record.get("symbol"),
                        record.get("setup_type"),
                        record.get("side"),
                        record.get("regime"),
                        record.get("outcome"),
                        record.get("outcome_reason"),
                    )
                    if part not in (None, "")
                ),
                300,
            ),
        }
        for lesson_type in _structured_lesson_types(record):
            value = _structured_text(record, lesson_type)
            if not value or len(value) < 8:
                continue
            subject_key = stable_hash(
                {
                    "symbol": record.get("symbol"),
                    "setup_type": record.get("setup_type"),
                    "side": record.get("side"),
                    "regime": record.get("regime"),
                    "lesson_type": lesson_type,
                }
            )[:24]
            lesson = {
                "source_type": "EXTERNAL_EXPERIENCE",
                "trust_level": "IMPORTED_UNVALIDATED",
                "validation_status": "UNVALIDATED",
                "lesson_type": lesson_type,
                "label": LESSON_LABELS.get(lesson_type, lesson_type),
                "text": f"{LESSON_LABELS.get(lesson_type, lesson_type)}: {value}",
                "value": value,
                "symbol": record.get("symbol"),
                "setup_type": record.get("setup_type"),
                "side": record.get("side"),
                "regime": record.get("regime"),
                "outcome": record.get("outcome"),
                "outcome_reason": record.get("outcome_reason"),
                "lesson_learned": record.get("lesson_learned"),
                "reason": record.get("reason"),
                "confidence": record.get("confidence"),
                "score": record.get("score"),
                "rr": record.get("rr"),
                "trade_result": record.get("trade_result"),
                "failure_success_reason": _structured_text(record, "failure_success_reason"),
                "stock_behavior": _structured_text(record, "stock_behavior"),
                "no_trade_lesson": _structured_text(record, "no_trade_lesson") if lesson_type == "no_trade_lesson" else None,
                "confidence_lesson": _structured_text(record, "confidence_lesson")
                if (record.get("confidence") is not None or record.get("score") is not None)
                else None,
                "causal_lesson": _structured_text(record, "causal_lesson"),
                "polarity": polarity,
                "category": category,
                "importance": _structured_importance(lesson_type, record),
                "seen_count": 1,
                "status": "UNVALIDATED",
                "evidence": [evidence],
                "subject_key": subject_key,
            }
            lesson["lesson_hash"] = stable_hash(
                {"lesson_type": lesson_type, "row_hash": row_hash, "value": value}
            )[:24]
            lessons.append(lesson)
    return lessons



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
