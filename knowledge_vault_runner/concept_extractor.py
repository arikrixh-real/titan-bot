import re


CATEGORY_PATTERNS = {
    "risk_warning": ("risk", "stop loss", "drawdown", "avoid", "danger", "loss", "position size", "overtrade"),
    "market_psychology": ("fear", "greed", "psychology", "sentiment", "panic", "euphoria", "discipline", "patience"),
    "institutional_concept": ("institutional", "liquidity", "order flow", "absorption", "iceberg", "operator", "smart money"),
    "strategy_idea": ("strategy", "setup", "entry", "breakout", "reversal", "trend", "mean reversion", "confirmation"),
    "testable_hypothesis": ("hypothesis", "test", "backtest", "if ", "when ", "edge", "expectancy"),
    "rule": ("must", "never", "always", "only trade", "rule", "condition", "should"),
    "concept": ("concept", "principle", "model", "framework", "pattern"),
}


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [part.strip(" -\t\r\n") for part in parts if len(part.strip()) >= 40]


def _importance(sentence, category):
    score = 0.35
    lowered = sentence.lower()
    score += min(len(sentence) / 800.0, 0.25)
    score += 0.15 if category in {"risk_warning", "rule", "testable_hypothesis"} else 0.0
    score += 0.1 if any(token in lowered for token in ("because", "therefore", "avoid", "must", "edge")) else 0.0
    return round(min(score, 1.0), 3)


def extract_concepts(chunk):
    text = chunk.get("text", "")
    findings = []
    for sentence in _sentences(text):
        lowered = sentence.lower()
        matched = []
        for category, patterns in CATEGORY_PATTERNS.items():
            if any(pattern in lowered for pattern in patterns):
                matched.append(category)
        if not matched:
            continue
        for category in matched[:3]:
            findings.append(
                {
                    "type": category,
                    "text": sentence[:700],
                    "importance": _importance(sentence, category),
                    "evidence": [
                        {
                            "source_file": chunk.get("source_path"),
                            "chunk_id": chunk.get("chunk_id"),
                            "chunk_index": chunk.get("chunk_index"),
                            "excerpt": sentence[:260],
                        }
                    ],
                }
            )
    return findings[:40]

