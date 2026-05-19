from pathlib import Path

from consciousness_core.experience_utils import load_json, load_standard_reports, load_trade_rows
from consciousness_core.institutional_utils import CORE_DIR, clamp, text_blob
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "data_quality_intelligence.json"


def _missing_reports(paths):
    return [str(path) for path in paths if not Path(path).exists()]


def _proxy_warnings(*payloads):
    warnings = []
    blob = text_blob(*payloads)
    for term in ("proxy", "insufficient", "no_data", "unavailable", "review"):
        if term in blob:
            warnings.append(f"detected {term} data mode or warning in intelligence inputs")
    return sorted(set(warnings))


def run_data_quality_intelligence(output_path=OUTPUT_PATH, **_kwargs):
    reports = load_standard_reports()
    runtime_health = load_json(Path("data") / "runtime" / "titan_runtime_status.json", {})
    worker_health = load_json(Path("data") / "runtime" / "worker_health.json", {})
    daemon_health = load_json(Path("data") / "runtime" / "daemon_health.json", {})
    news = reports.get("news", {})
    backtesting = reports.get("backtesting", {})
    confidence = load_json(CORE_DIR / "confidence_recalibration.json", {}) or reports.get("confidence", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})
    scenarios = load_json(CORE_DIR / "real_scenario_simulation.json", {})
    trades = load_trade_rows()

    expected_reports = [
        Path("data") / "runtime" / "worker_health.json",
        Path("data") / "runtime" / "titan_runtime_status.json",
        Path("data") / "research" / "backtesting_validation_report.json",
        Path("data") / "news_intelligence" / "latest_news_intelligence_2_report.json",
        Path("data") / "no_trade" / "latest_no_trade_intelligence_report.json",
        CORE_DIR / "confidence_recalibration.json",
        CORE_DIR / "liquidity_intelligence.json",
        CORE_DIR / "manipulation_intelligence.json",
    ]
    missing = _missing_reports(expected_reports)
    stale = []
    for path in expected_reports:
        if path.exists():
            try:
                age_seconds = max(0.0, __import__("time").time() - path.stat().st_mtime)
            except OSError:
                age_seconds = 0.0
            if age_seconds > 60 * 60 * 24:
                stale.append({"path": str(path), "age_hours": round(age_seconds / 3600, 2)})

    ohlc_paths = list((Path("data") / "ohlc").glob("*.json")) if (Path("data") / "ohlc").exists() else []
    if not ohlc_paths:
        missing.append(str(Path("data") / "ohlc" / "*.json"))

    low_sample = []
    confidence_sample = int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0)
    if confidence_sample < 20:
        low_sample.append(f"confidence calibration sample is {confidence_sample}, below 20")
    if len(trades) < 50:
        low_sample.append(f"trade outcome sample is {len(trades)}, below 50")

    unreliable = []
    if liquidity.get("source_modes"):
        unreliable.append({"engine": "liquidity_intelligence", "reason": liquidity.get("source_modes")})
    if manipulation.get("suspicion_score") and _proxy_warnings(manipulation):
        unreliable.append({"engine": "manipulation_intelligence", "reason": "trap score includes proxy/review evidence"})
    if not scenarios.get("scenarios"):
        unreliable.append({"engine": "real_scenario_simulation", "reason": "scenario output missing or empty"})

    proxy = _proxy_warnings(runtime_health, worker_health, daemon_health, news, backtesting, confidence, liquidity, manipulation)
    penalty = len(missing) * 8 + len(stale) * 4 + len(proxy) * 6 + len(low_sample) * 10 + len(unreliable) * 7
    score = clamp(100 - penalty, 0, 100)
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only",
        "data_quality_score": round(score, 2),
        "stale_data_warnings": stale,
        "missing_data_warnings": missing,
        "proxy_data_warnings": proxy,
        "low_sample_warnings": low_sample,
        "unreliable_engine_outputs": unreliable,
        "recommended_data_fixes": [
            "refresh missing runtime, news, no-trade, backtesting, and OHLC reports",
            "increase paper/outcome samples before trusting promotion evidence",
            "replace proxy liquidity and microstructure inputs with real market data when available",
            "keep all affected outputs advisory until data quality improves",
        ],
    }
    atomic_write_json(output_path, payload)
    return payload
