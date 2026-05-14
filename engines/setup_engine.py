import os

QUIET_MODE = os.getenv("TITAN_QUIET_MODE", "0") == "1"
from datetime import datetime

from supabase import create_client

from data.loader import load_cached_stock_data
from data.live_price import get_live_price

from scanners.volume_scanner import volume_anomaly_score
from scanners.strength_scanner import price_strength_score
from scanners.compression_scanner import compression_score

from engines.score_engine import final_signal_score
from engines.trade_levels import calculate_trade_levels
from engines.risk_engine import calculate_rr, position_sizing
from engines.filter_engine import passes_quality_filters
from engines.market_filter import market_regime_status
from engines.trend_engine import trend_direction, trade_side_from_trend
from engines.momentum_engine import strong_momentum
from engines.trap_engine import avoid_fake_breakout
from engines.relative_strength_engine import relative_strength_ok
from engines.entry_engine import breakout_ready
from engines.reason_engine import build_reason
from engines.trigger_engine import trigger_status
from engines.structure_engine import structure_ok

from journal.trade_journal import log_trade
from journal.scan_journal import log_scan
from utils.market_hours import is_trade_window, trade_window_text

try:
    from config.universe import (
        MICRO_CAPITAL_PRICE_SOFT_CAP,
        MICRO_CAPITAL_TIGHT_SL_PCT,
        is_adaptive_1k_mode,
    )
except Exception:
    MICRO_CAPITAL_PRICE_SOFT_CAP = 700.0
    MICRO_CAPITAL_TIGHT_SL_PCT = 0.75
    is_adaptive_1k_mode = None

try:
    from engines.institutional_microstructure import analyze_microstructure
except Exception:
    analyze_microstructure = None

try:
    from engines.advanced_regime_engine import detect_advanced_regime
except Exception:
    detect_advanced_regime = None

try:
    from engines.pro_risk_engine import evaluate_professional_risk
except Exception:
    evaluate_professional_risk = None

try:
    from engines.portfolio_construction_engine import analyze_portfolio_construction
except Exception:
    analyze_portfolio_construction = None

try:
    from engines.execution_quality_engine import analyze_execution_quality
except Exception:
    analyze_execution_quality = None

try:
    from engines.data_advantage_engine import (
        apply_data_advantage_layer,
        build_data_advantage_context,
        market_status_from_context,
    )
except Exception:
    apply_data_advantage_layer = None
    build_data_advantage_context = None
    market_status_from_context = None

try:
    from engines.meta_intelligence_engine import apply_meta_intelligence
except Exception:
    apply_meta_intelligence = None

try:
    from engines.probabilistic_world_model import (
        build_probability_report,
        rank_setups_by_probability,
    )
except Exception:
    build_probability_report = None
    rank_setups_by_probability = None

try:
    from engines.causal_market_reasoning_engine import build_causal_reasoning_report
except Exception:
    build_causal_reasoning_report = None

from titan_brain.db import (
    insert_scan,
    insert_scan_symbol,
    insert_trade,
    insert_setup
)



def titan_log(message, important=False):
    """
    Quiet-mode logger.
    TITAN_QUIET_MODE=1 suppresses noisy per-stock logs.
    Important logs/errors still print.
    """
    if important or not QUIET_MODE:
        print(message)

def save_scan_health_log(
    stocks_checked,
    trend_passed,
    momentum_passed,
    structure_passed,
    entry_passed,
    final_passed,
    alerts_sent,
    market_status
):
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            print("⚠️ Supabase secrets missing. Scan health not saved.")
            return

        supabase = create_client(supabase_url, supabase_key)

        supabase.table("scan_health_logs").insert({
            "scan_cycle_id": datetime.now().isoformat(),
            "stocks_checked": stocks_checked,
            "trend_passed": trend_passed,
            "momentum_passed": momentum_passed,
            "structure_passed": structure_passed,
            "entry_passed": entry_passed,
            "final_passed": final_passed,
            "alerts_sent": alerts_sent,
            "market_status": str(market_status),
            "status": "COMPLETED",
            "note": "Scan health log saved successfully"
        }).execute()

        print("✅ Scan health saved")

    except Exception as e:
        if "WinError 10013" in str(e):
            print("[Supabase WARN - scan_health] socket unavailable; scan health not saved.")
        else:
            print(f"❌ Scan health save failed: {e}")


def safe_trade_levels(symbol, side, live_price, data):
    """
    Robust trade-level wrapper.
    Works even if calculate_trade_levels() has different signatures.
    """
    levels = None

    # New/simple style: calculate_trade_levels(df, side="LONG")
    try:
        levels = calculate_trade_levels(data, side=side)
    except TypeError:
        levels = None
    except Exception as e:
        titan_log(f"TRADE LEVEL ERROR SIMPLE → {symbol}: {e}")
        levels = None

    # Alternate keyword style: calculate_trade_levels(df=data, side=side)
    if not levels:
        try:
            levels = calculate_trade_levels(df=data, side=side)
        except TypeError:
            levels = None
        except Exception as e:
            titan_log(f"TRADE LEVEL ERROR DF → {symbol}: {e}")
            levels = None

    # Old style fallback: calculate_trade_levels(side, entry_price, data)
    if not levels:
        try:
            levels = calculate_trade_levels(side=side, entry_price=live_price, data=data)
        except TypeError:
            levels = None
        except Exception as e:
            titan_log(f"TRADE LEVEL ERROR OLD → {symbol}: {e}")
            levels = None

    # Final emergency fallback
    if not levels:
        try:
            entry = float(live_price)

            if side == "LONG":
                stop_loss = round(entry * 0.99, 2)
                target = round(entry * 1.02, 2)
            elif side == "SHORT":
                stop_loss = round(entry * 1.01, 2)
                target = round(entry * 0.98, 2)
            else:
                return None

            levels = {
                "entry": round(entry, 2),
                "stop_loss": stop_loss,
                "target": target
            }

        except Exception as e:
            titan_log(f"TRADE LEVEL FALLBACK FAILED → {symbol}: {e}")
            return None

    # Normalize levels safely.
    # Some calculate_trade_levels() versions return dict.
    # Some return tuple/list like (entry, sl, target).
    if isinstance(levels, dict):
        entry = levels.get("entry") or levels.get("price") or live_price
        stop_loss = levels.get("stop_loss") or levels.get("sl")
        target = levels.get("target") or levels.get("tp") or levels.get("t1")

    elif isinstance(levels, (tuple, list)):
        values = list(levels)
        entry = values[0] if len(values) > 0 else live_price
        stop_loss = values[1] if len(values) > 1 else None
        target = values[2] if len(values) > 2 else None

    else:
        entry = live_price
        stop_loss = None
        target = None

    if entry is None or stop_loss is None or target is None:
        return None

    return {
        "entry": round(float(entry), 2),
        "stop_loss": round(float(stop_loss), 2),
        "target": round(float(target), 2)
    }


def safe_position_sizing(entry, stop_loss):
    """
    Robust position sizing wrapper.
    Some versions of position_sizing() return dict.
    Some return tuple/list.
    This always returns a safe dict.
    """
    try:
        from engines.paper_trading_engine import load_paper_account, calculate_paper_trade_sizing
        sizing = calculate_paper_trade_sizing(
            load_paper_account(),
            {"entry": entry, "sl": stop_loss},
        )
        if isinstance(sizing, dict):
            return {**sizing, "raw": "PAPER_RISK_1PCT"}
    except Exception:
        pass

    try:
        pos_data = position_sizing(entry, stop_loss)

        if isinstance(pos_data, dict):
            return {
                "qty": pos_data.get("qty") or pos_data.get("quantity") or 0,
                "quantity": pos_data.get("qty") or pos_data.get("quantity") or 0,
                "position_size": pos_data.get("position_size") or 0,
                "risk_amount": pos_data.get("risk_amount") or pos_data.get("risk") or 0,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct") or 1.0,
                "risk_per_share": pos_data.get("risk_per_share") or abs(float(entry) - float(stop_loss)),
                "skip_reason": pos_data.get("skip_reason") or "",
                "sizing_valid": bool(pos_data.get("qty") or pos_data.get("quantity")),
                "raw": pos_data
            }

        if isinstance(pos_data, (tuple, list)):
            return {
                "qty": pos_data[0] if len(pos_data) > 0 else 0,
                "quantity": pos_data[0] if len(pos_data) > 0 else 0,
                "position_size": (pos_data[0] if len(pos_data) > 0 else 0) * entry,
                "risk_amount": pos_data[1] if len(pos_data) > 1 else 0,
                "risk_per_trade_pct": 1.0,
                "risk_per_share": abs(float(entry) - float(stop_loss)),
                "skip_reason": "",
                "sizing_valid": bool(pos_data[0] if len(pos_data) > 0 else 0),
                "raw": list(pos_data)
            }

        return {
            "qty": 0,
            "quantity": 0,
            "position_size": 0,
            "risk_amount": 0,
            "risk_per_trade_pct": 1.0,
            "risk_per_share": 0,
            "skip_reason": "MICRO_CAPITAL_QTY_INVALID",
            "sizing_valid": False,
            "raw": pos_data
        }

    except Exception as e:
        titan_log(f"POSITION SIZE ERROR → {e}")
        return {
            "qty": 0,
            "quantity": 0,
            "position_size": 0,
            "risk_amount": 0,
            "risk_per_trade_pct": 1.0,
            "risk_per_share": 0,
            "skip_reason": "MICRO_CAPITAL_QTY_INVALID",
            "sizing_valid": False,
            "raw": None
        }


def _micro_capital_skip_reason(entry, stop_loss, sizing):
    if is_adaptive_1k_mode is None or not is_adaptive_1k_mode():
        return ""

    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
    except Exception:
        return "MICRO_CAPITAL_QTY_INVALID"

    account_balance = _safe_float(sizing.get("account_balance"), 1000.0)
    risk_amount = _safe_float(sizing.get("risk_amount"), account_balance * 0.01)
    risk_per_share = _safe_float(sizing.get("risk_per_share"), abs(entry - stop_loss))
    quantity = int(_safe_float(sizing.get("quantity") or sizing.get("qty"), 0.0))
    position_size = _safe_float(sizing.get("position_size"), 0.0)
    sl_pct = (risk_per_share / entry * 100.0) if entry > 0 else 999.0

    if entry > account_balance:
        return "MICRO_CAPITAL_PRICE_SKIP"
    if quantity < 1:
        if risk_per_share > risk_amount:
            return "MICRO_CAPITAL_SL_TOO_WIDE"
        return "MICRO_CAPITAL_QTY_INVALID"
    if position_size <= 0 or position_size > account_balance:
        return "MICRO_CAPITAL_QTY_INVALID"
    if entry > MICRO_CAPITAL_PRICE_SOFT_CAP and sl_pct > MICRO_CAPITAL_TIGHT_SL_PCT:
        return "MICRO_CAPITAL_SL_TOO_WIDE"
    return ""


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _existing_rank_score(setup):
    if not isinstance(setup, dict):
        return 0.0
    return _safe_float(
        setup.get("final_score", setup.get("score", setup.get("rank_score"))),
        0.0,
    )


def _probability_context(market_status, data_advantage_context=None):
    context = {
        "market_status": market_status,
        "data_advantage_context": data_advantage_context or {},
    }

    if isinstance(market_status, dict):
        context["market_regime"] = (
            market_status.get("regime")
            or market_status.get("status")
            or market_status.get("direction")
            or market_status.get("reason")
            or "neutral"
        )
    else:
        context["market_regime"] = str(market_status or "neutral")

    return context


def apply_probability_fields(setup, context):
    """
    Fail-open probability annotation. It never blocks or rejects a setup.
    """
    if not isinstance(setup, dict):
        return setup

    result = dict(setup)
    existing_score = _existing_rank_score(result)

    if build_probability_report is None:
        result["blended_rank_score"] = existing_score
        return result

    try:
        report = build_probability_report(result, context if isinstance(context, dict) else {})
        probability_score = _safe_float(report.get("final_probability_score"), existing_score)

        result["probability_score"] = probability_score
        result["probability_recommendation"] = report.get("recommendation")
        result["probability_expected_value"] = report.get("expected_value")
        result["probability_confidence"] = report.get("probability_confidence_score")
        result["probability_uncertainty"] = report.get("uncertainty_score")
        result["probability_explanations"] = report.get("explanations", [])
        result["blended_rank_score"] = round((0.70 * existing_score) + (0.30 * probability_score), 4)
    except Exception as e:
        result["blended_rank_score"] = existing_score
        result["probability_error"] = str(e)

    return result


def apply_probability_ranking(setups, context):
    if not isinstance(setups, list):
        return []

    if rank_setups_by_probability is not None:
        try:
            rank_setups_by_probability(setups, context if isinstance(context, dict) else {})
        except Exception:
            pass

    ranked = [apply_probability_fields(setup, context) for setup in setups]
    ranked.sort(
        key=lambda setup: _safe_float(setup.get("blended_rank_score"), _existing_rank_score(setup)),
        reverse=True,
    )
    return ranked


def _base_rank_score(setup):
    if not isinstance(setup, dict):
        return 0.0
    return _safe_float(
        setup.get("blended_rank_score", setup.get("final_score", setup.get("score"))),
        0.0,
    )


def _causal_adjusted_confidence(report):
    if not isinstance(report, dict):
        return 0.0

    confidence = _safe_float(report.get("cause_confidence_score"), 0.0)
    event = str(report.get("event_classification") or "").upper()
    news_chain = report.get("news_to_sector_stock_chain") if isinstance(report.get("news_to_sector_stock_chain"), dict) else {}
    index_chain = report.get("index_sector_stock_causality") if isinstance(report.get("index_sector_stock_causality"), dict) else {}
    leadership = report.get("sector_leadership_cause") if isinstance(report.get("sector_leadership_cause"), dict) else {}
    pressure = report.get("market_wide_pressure") if isinstance(report.get("market_wide_pressure"), dict) else {}
    false_news = report.get("false_news_caution") if isinstance(report.get("false_news_caution"), dict) else {}
    cascade = report.get("cascading_event_risk") if isinstance(report.get("cascading_event_risk"), dict) else {}
    graph = report.get("narrative_causality_graph") if isinstance(report.get("narrative_causality_graph"), dict) else {}

    if _safe_float(leadership.get("leadership_score"), 0.0) >= 65.0:
        confidence += 7.0
    if _safe_float(index_chain.get("causal_score"), 0.0) >= 55.0 or index_chain.get("causal_alignment") == "ALIGNED":
        confidence += 5.0
    if _safe_float(news_chain.get("chain_strength"), 0.0) >= 50.0:
        confidence += 6.0
    if len(graph.get("edges", []) or []) >= 4:
        confidence += 3.0
    if cascade.get("active") and _safe_float(cascade.get("risk_score"), 0.0) < 40.0:
        confidence += 2.0

    if false_news.get("active"):
        confidence -= 8.0
    if _safe_float(report.get("cause_confidence_score"), 0.0) < 35.0:
        confidence -= 6.0
    if _safe_float(cascade.get("risk_score"), 0.0) >= 55.0:
        confidence -= 8.0
    if pressure.get("active") and not index_chain.get("active"):
        confidence -= 4.0
    if event in {"NO_CLEAR_EVENT", "UNKNOWN", ""}:
        confidence -= 3.0

    return max(0.0, min(100.0, round(confidence, 2)))


def apply_causal_fields(setup, context, news_items=None):
    if not isinstance(setup, dict):
        return setup

    result = dict(setup)
    existing_rank = _base_rank_score(result)

    if build_causal_reasoning_report is None:
        result["new_blended_rank_score"] = existing_rank
        return result

    try:
        report = build_causal_reasoning_report(result, context if isinstance(context, dict) else {}, news_items=news_items or [])
        causal_confidence = _causal_adjusted_confidence(report)

        result["causal_primary_cause"] = report.get("primary_cause")
        result["causal_confidence_score"] = causal_confidence
        result["causal_event_classification"] = report.get("event_classification")
        result["causal_market_pressure"] = report.get("market_wide_pressure", {})
        result["causal_sector_leadership"] = report.get("sector_leadership_cause", {})
        result["causal_delayed_effect"] = report.get("delayed_effect_tracking", {})
        result["causal_cascading_risk"] = report.get("cascading_event_risk", {})
        result["causal_explanations"] = report.get("explanations", [])
        result["new_blended_rank_score"] = round((existing_rank * 0.85) + (causal_confidence * 0.15), 4)
    except Exception as e:
        result["new_blended_rank_score"] = existing_rank
        result["causal_error"] = str(e)

    return result


def apply_causal_ranking(setups, context, news_items=None):
    if not isinstance(setups, list):
        return []

    ranked = [apply_causal_fields(setup, context, news_items=news_items) for setup in setups]
    ranked.sort(
        key=lambda setup: _safe_float(setup.get("new_blended_rank_score"), _base_rank_score(setup)),
        reverse=True,
    )
    return ranked


def apply_institutional_phase1(trade_payload, data, side, live_price, market_status):
    """
    Adds Phase 1 institutional metadata.

    Fail-open rule:
    - Engine calculation errors keep the setup alive.
    - Only explicit professional risk blocks remove the setup.
    """
    result = dict(trade_payload)

    microstructure = {
        "available": False,
        "liquidity_quality_score": 50.0,
        "warnings": ["phase1_microstructure_not_available"],
    }
    advanced_regime = {
        "available": False,
        "regime_type": "UNKNOWN",
        "regime_confidence": 0.0,
        "warnings": ["phase1_regime_not_available"],
    }
    professional_risk = {
        "risk_allowed": True,
        "risk_quality_score": 50.0,
        "risk_blocks": [],
        "risk_warnings": ["phase1_risk_not_available"],
    }

    try:
        if analyze_microstructure is not None:
            microstructure = analyze_microstructure(
                df=data,
                side=side,
                live_price=live_price,
            )
    except Exception as e:
        microstructure["error"] = str(e)

    try:
        if detect_advanced_regime is not None:
            advanced_regime = detect_advanced_regime(
                df=data,
                symbol=result.get("symbol"),
                market_status=market_status,
            )
    except Exception as e:
        advanced_regime["error"] = str(e)

    try:
        if evaluate_professional_risk is not None:
            professional_risk = evaluate_professional_risk(
                setup=result,
                microstructure=microstructure,
                regime=advanced_regime,
            )
    except Exception as e:
        professional_risk["error"] = str(e)

    liquidity_quality = _safe_float(microstructure.get("liquidity_quality_score"), 50.0)
    risk_quality = _safe_float(professional_risk.get("risk_quality_score"), 50.0)
    regime_confidence = _safe_float(advanced_regime.get("regime_confidence"), 0.0)
    panic_score = _safe_float(advanced_regime.get("panic_score"), 0.0)
    liquidity_crisis = _safe_float(advanced_regime.get("liquidity_crisis_score"), 0.0)

    institutional_adjustment = 0.0
    institutional_adjustment += (liquidity_quality - 50.0) * 0.01
    institutional_adjustment += (risk_quality - 50.0) * 0.008

    if regime_confidence >= 55 and advanced_regime.get("regime_type") == "TRENDING":
        institutional_adjustment += 0.15

    if panic_score >= 60 or liquidity_crisis >= 60:
        institutional_adjustment -= 0.25

    original_score = _safe_float(result.get("score"), 0.0)
    adjusted_score = max(0.0, original_score + institutional_adjustment)

    result["score"] = round(adjusted_score, 2)
    result["rank_score"] = round(adjusted_score, 2)
    result["institutional_score_adjustment"] = round(institutional_adjustment, 3)
    result["microstructure"] = microstructure
    result["advanced_regime"] = advanced_regime
    result["professional_risk"] = professional_risk
    result["liquidity_quality_score"] = microstructure.get("liquidity_quality_score")
    result["regime_confidence"] = advanced_regime.get("regime_confidence")
    result["risk_quality_score"] = professional_risk.get("risk_quality_score")

    if isinstance(result.get("scores"), dict):
        result["scores"] = dict(result["scores"])
        result["scores"]["institutional_score_adjustment"] = result["institutional_score_adjustment"]
        result["scores"]["institutional_adjusted_score"] = result["score"]

    if isinstance(result.get("market_context"), dict):
        result["market_context"] = dict(result["market_context"])
        result["market_context"]["advanced_regime"] = advanced_regime
        result["market_context"]["liquidity_quality_score"] = result["liquidity_quality_score"]

    if isinstance(result.get("setup_context"), dict):
        result["setup_context"] = dict(result["setup_context"])
        result["setup_context"]["microstructure"] = microstructure
        result["setup_context"]["professional_risk"] = professional_risk

    risk_blocks = professional_risk.get("risk_blocks", [])
    result["phase1_blocked"] = bool(risk_blocks)
    result["phase1_block_reason"] = ", ".join(str(item) for item in risk_blocks)

    return result


def apply_institutional_phase2(trade_payload, data, side, live_price):
    """
    Adds Phase 2 portfolio and execution-quality metadata.

    Fail-open rule:
    - Engine calculation errors keep the setup alive.
    - Phase 2 does not hard-block trades.
    - Score changes are conservative and bounded.
    """
    result = dict(trade_payload)

    portfolio = {
        "available": False,
        "sector_exposure_score": 50.0,
        "portfolio_concentration_risk": 50.0,
        "correlation_proxy": 0.0,
        "beta_like_market_sensitivity": 1.0,
        "volatility_contribution_score": 50.0,
        "portfolio_quality_score": 50.0,
        "portfolio_risk_warnings": ["phase2_portfolio_not_available"],
    }
    execution_quality = {
        "available": False,
        "vwap_like_entry_quality_proxy": 50.0,
        "twap_like_stability_proxy": 50.0,
        "slippage_risk_estimate": 50.0,
        "liquidity_sensitive_entry_quality": 50.0,
        "chase_entry_penalty": 0.0,
        "execution_quality_score": 50.0,
        "warnings": ["phase2_execution_not_available"],
    }

    try:
        if analyze_portfolio_construction is not None:
            portfolio = analyze_portfolio_construction(
                setup=result,
                df=data,
            )
    except Exception as e:
        portfolio["error"] = str(e)

    try:
        if analyze_execution_quality is not None:
            execution_quality = analyze_execution_quality(
                df=data,
                setup=result,
                microstructure=result.get("microstructure", {}),
                live_price=live_price,
            )
    except Exception as e:
        execution_quality["error"] = str(e)

    portfolio_quality = _safe_float(portfolio.get("portfolio_quality_score"), 50.0)
    execution_score = _safe_float(execution_quality.get("execution_quality_score"), 50.0)
    concentration_risk = _safe_float(portfolio.get("portfolio_concentration_risk"), 50.0)
    slippage_risk = _safe_float(execution_quality.get("slippage_risk_estimate"), 50.0)
    chase_penalty = _safe_float(execution_quality.get("chase_entry_penalty"), 0.0)

    phase2_adjustment = 0.0
    phase2_adjustment += (portfolio_quality - 50.0) * 0.004
    phase2_adjustment += (execution_score - 50.0) * 0.005
    phase2_adjustment -= max(0.0, concentration_risk - 60.0) * 0.002
    phase2_adjustment -= max(0.0, slippage_risk - 60.0) * 0.003
    phase2_adjustment -= chase_penalty * 0.003
    phase2_adjustment = max(-0.25, min(0.15, phase2_adjustment))

    original_score = _safe_float(result.get("score"), 0.0)
    adjusted_score = max(0.0, original_score + phase2_adjustment)

    result["score"] = round(adjusted_score, 2)
    result["rank_score"] = round(adjusted_score, 2)
    result["phase2_score_adjustment"] = round(phase2_adjustment, 3)
    result["portfolio_construction"] = portfolio
    result["execution_quality"] = execution_quality
    result["sector_exposure_score"] = portfolio.get("sector_exposure_score")
    result["portfolio_concentration_risk"] = portfolio.get("portfolio_concentration_risk")
    result["correlation_proxy"] = portfolio.get("correlation_proxy")
    result["beta_like_market_sensitivity"] = portfolio.get("beta_like_market_sensitivity")
    result["volatility_contribution_score"] = portfolio.get("volatility_contribution_score")
    result["execution_quality_score"] = execution_quality.get("execution_quality_score")
    result["slippage_risk_estimate"] = execution_quality.get("slippage_risk_estimate")
    result["chase_entry_penalty"] = execution_quality.get("chase_entry_penalty")

    risk_warnings = []
    risk_warnings.extend(portfolio.get("portfolio_risk_warnings", []) or [])
    risk_warnings.extend(execution_quality.get("warnings", []) or [])
    result["phase2_risk_warnings"] = risk_warnings

    if isinstance(result.get("scores"), dict):
        result["scores"] = dict(result["scores"])
        result["scores"]["phase2_score_adjustment"] = result["phase2_score_adjustment"]
        result["scores"]["phase2_adjusted_score"] = result["score"]
        result["scores"]["portfolio_quality_score"] = portfolio.get("portfolio_quality_score")
        result["scores"]["execution_quality_score"] = execution_quality.get("execution_quality_score")

    if isinstance(result.get("market_context"), dict):
        result["market_context"] = dict(result["market_context"])
        result["market_context"]["portfolio_construction"] = portfolio

    if isinstance(result.get("setup_context"), dict):
        result["setup_context"] = dict(result["setup_context"])
        result["setup_context"]["execution_quality"] = execution_quality
        result["setup_context"]["phase2_risk_warnings"] = risk_warnings

    return result


def scan_for_setups():
    if not is_trade_window():
        titan_log(
            f"Outside trade window ({trade_window_text()}). Setup scan and trade creation skipped.",
            important=True,
        )
        return []

    setups = []

    scanned_symbols = []
    setup_symbols = []
    errors = []

    # =========================
    # SCAN HEALTH COUNTERS
    # =========================
    stocks_checked = 0
    trend_passed = 0
    momentum_passed = 0
    structure_passed = 0
    entry_passed = 0
    final_passed = 0
    alerts_sent = 0

    # Detailed failure counters
    no_live_price_count = 0
    no_valid_trend_count = 0
    structure_fail_count = 0
    momentum_fail_count = 0
    fake_breakout_count = 0
    relative_weak_count = 0
    not_ready_count = 0
    quality_fail_count = 0
    confluence_fail_count = 0
    levels_fail_count = 0
    rr_fail_count = 0
    phase1_block_count = 0

    symbols = load_cached_stock_data()
    total_symbols = len(symbols)

    data_advantage_context = {}
    try:
        if build_data_advantage_context is not None:
            data_advantage_context = build_data_advantage_context(symbols)
    except Exception as e:
        data_advantage_context = {
            "available": False,
            "warnings": ["phase4_context_error"],
            "error": str(e),
        }

    try:
        if market_status_from_context is not None:
            market_status = market_status_from_context(data_advantage_context)
        else:
            market_status = market_regime_status()
    except Exception as e:
        market_status = {
            "market_ok": True,
            "reason": "Phase 4 market status failed open",
            "direction": "NEUTRAL",
            "regime": "UNKNOWN",
            "status": "UNKNOWN",
            "volatility": "UNKNOWN",
            "error": str(e),
        }

    titan_log("DYNAMIC / SETUP ENGINE ACTIVE")
    titan_log(f"Symbols received from loader: {total_symbols}")

    scan_record = {
        "total_symbols": total_symbols,
        "scanned_count": 0,
        "setup_count": 0,
        "errors": []
    }

    scan_id = insert_scan(scan_record)

    for symbol, data in symbols.items():
        try:
            scanned_symbols.append(symbol)
            scan_record["scanned_count"] += 1
            stocks_checked += 1

            source = "UPSTOX"
            live_price = get_live_price(symbol)

            if live_price is None:
                try:
                    live_price = float(data["Close"].iloc[-1])
                    source = "CACHE_CLOSE"
                except Exception:
                    no_live_price_count += 1
                    titan_log(f"FILTER RESULT → {symbol} | NO_LIVE_PRICE")
                    insert_scan_symbol(scan_id, {
                        "symbol": symbol,
                        "price": 0,
                        "trend": "NA",
                        "volume_score": 0,
                        "strength_score": 0,
                        "compression_score": 0,
                        "final_score": 0,
                        "passed": False,
                        "reason": "NO_LIVE_PRICE"
                    })
                    continue

            trend = trend_direction(data)
            side = trade_side_from_trend(trend)

            if side is None:
                no_valid_trend_count += 1
                titan_log(f"FILTER RESULT → {symbol} | NO_VALID_TREND")
                insert_scan_symbol(scan_id, {
                    "symbol": symbol,
                    "price": live_price,
                    "trend": trend,
                    "volume_score": 0,
                    "strength_score": 0,
                    "compression_score": 0,
                    "final_score": 0,
                    "passed": False,
                    "reason": "NO_VALID_TREND"
                })
                continue

            trend_passed += 1

            volume_score = volume_anomaly_score(data)
            strength_score = price_strength_score(data)
            comp_score = compression_score(data)

            final_score = final_signal_score(
                volume_score,
                strength_score,
                comp_score
            )

            structure_result = structure_ok(data, side=side)
            momentum_result = strong_momentum(data, side=side)
            fake_breakout_ok = avoid_fake_breakout(data)
            relative_strength_result = relative_strength_ok(data, side=side)
            entry_result = breakout_ready(data, side=side)

            if structure_result:
                structure_passed += 1

            if momentum_result:
                momentum_passed += 1

            if entry_result:
                entry_passed += 1

            quality_ok = passes_quality_filters(
                {
                    "score": final_score,
                    "rr": 2,
                    "volume_x": volume_score,
                    "strength": strength_score,
                    "compression": comp_score
                }
            )

            confirmations = 0
            confirmations += 1 if structure_result else 0
            confirmations += 1 if momentum_result else 0
            confirmations += 1 if fake_breakout_ok else 0
            confirmations += 1 if relative_strength_result else 0
            confirmations += 1 if entry_result else 0
            confirmations += 1 if quality_ok else 0

            print(
                f"ENTRY DEBUG → {symbol} | price={round(float(live_price), 2)} | source={source} | "
                f"trend={trend} | side={side} | volume={round(float(volume_score), 2)} | "
                f"strength={round(float(strength_score), 2)} | compression={round(float(comp_score), 2)} | "
                f"final_score={round(float(final_score), 2)} | structure={structure_result} | "
                f"momentum={momentum_result} | fake_breakout_ok={fake_breakout_ok} | "
                f"relative_strength={relative_strength_result} | entry={entry_result} | "
                f"quality={quality_ok} | confirmations={confirmations}"
            )

            passed = False
            fail_reason = "UNKNOWN"
            entry = None
            stop_loss = None
            target = None
            rr = 0
            pos_data = None
            quantity = 0
            position_size = 0
            risk_amount = 0

            if not structure_result:
                structure_fail_count += 1
                fail_reason = "STRUCTURE_FAIL"

            elif not momentum_result:
                momentum_fail_count += 1
                fail_reason = "MOMENTUM_FAIL"

            elif not fake_breakout_ok:
                fake_breakout_count += 1
                fail_reason = "FAKE_BREAKOUT"

            elif not relative_strength_result:
                relative_weak_count += 1
                fail_reason = "RELATIVE_WEAK"

            elif not entry_result:
                not_ready_count += 1
                fail_reason = "NOT_READY"

            elif not quality_ok:
                quality_fail_count += 1
                fail_reason = "QUALITY_FAIL"

            elif confirmations < 3:
                confluence_fail_count += 1
                fail_reason = "CONFLUENCE_FAIL"

            else:
                levels = safe_trade_levels(
                    symbol=symbol,
                    side=side,
                    live_price=live_price,
                    data=data
                )

                if not levels:
                    levels_fail_count += 1
                    fail_reason = "LEVELS_FAIL"
                else:
                    entry = levels["entry"]
                    stop_loss = levels["stop_loss"]
                    target = levels["target"]

                    rr = calculate_rr(entry, stop_loss, target, side)

                    if rr < 1.5:
                        rr_fail_count += 1
                        fail_reason = "RR_FAIL"

                    else:
                        pos_data = safe_position_sizing(entry, stop_loss)
                        micro_skip_reason = _micro_capital_skip_reason(entry, stop_loss, pos_data)
                        quantity = pos_data.get("quantity") or pos_data.get("qty", 0)
                        position_size = pos_data.get("position_size", 0)
                        risk_amount = pos_data.get("risk_amount", 0)

                        if micro_skip_reason:
                            fail_reason = micro_skip_reason
                            titan_log(
                                f"FILTER RESULT -> {symbol} | PAPER_SIZE_SKIP | {micro_skip_reason}",
                                important=True,
                            )
                        elif not pos_data.get("sizing_valid", quantity and position_size) or int(quantity or 0) < 1:
                            fail_reason = pos_data.get("skip_reason", "MICRO_CAPITAL_QTY_INVALID")
                            titan_log(
                                f"FILTER RESULT -> {symbol} | PAPER_SIZE_SKIP | {fail_reason}",
                                important=True,
                            )
                        else:
                            passed = True
                            fail_reason = "PASSED"
                            final_passed += 1

            insert_scan_symbol(scan_id, {
                "symbol": symbol,
                "price": live_price,
                "trend": trend,
                "volume_score": volume_score,
                "strength_score": strength_score,
                "compression_score": comp_score,
                "final_score": final_score,
                "passed": passed,
                "reason": fail_reason
            })

            titan_log(f"FILTER RESULT → {symbol} | {fail_reason}")

            if not passed:
                continue

            if pos_data is None:
                pos_data = safe_position_sizing(entry, stop_loss)
                quantity = pos_data.get("quantity") or pos_data.get("qty", 0)
                position_size = pos_data.get("position_size", 0)
                risk_amount = pos_data.get("risk_amount", 0)

            reason = build_reason(
                symbol=symbol,
                side=side,
                volume_score=volume_score,
                strength_score=strength_score,
                compression_score=comp_score,
                final_score=final_score,
                trend=trend,
                market_status=market_status
            )

            trigger = trigger_status(
                symbol=symbol,
                side=side,
                entry=entry,
                price=live_price,
                score=final_score,
                rr=rr,
                market_status=market_status,
            )

            trade_payload = {
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "stop_loss": stop_loss,
                "target": target,
                "rr": rr,
                "score": final_score,
                "rank_score": final_score,
                "position_size": position_size,
                "quantity": quantity,
                "qty": quantity,
                "risk_amount": risk_amount,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct", 1.0),
                "entry_price": entry,
                "sl": stop_loss,
                "tp": target,
                "is_paper_trade": True,
                "scores": {
                    "volume_score": volume_score,
                    "strength_score": strength_score,
                    "compression_score": comp_score,
                    "final_score": final_score
                },
                "market_context": {
                    "market_status": market_status,
                    "trend": trend
                },
                "setup_context": {
                    "structure_ok": structure_result,
                    "momentum_ok": momentum_result,
                    "breakout_ready": entry_result,
                    "confirmations": confirmations,
                    "source": source
                },
                "reason": reason,
                "trigger_status": trigger,
                "status": "OPEN"
            }

            trade_payload = apply_institutional_phase1(
                trade_payload=trade_payload,
                data=data,
                side=side,
                live_price=live_price,
                market_status=market_status,
            )

            if trade_payload.get("phase1_blocked"):
                phase1_block_count += 1
                final_passed = max(0, final_passed - 1)
                titan_log(
                    f"FILTER RESULT → {symbol} | PHASE1_RISK_BLOCK | "
                    f"{trade_payload.get('phase1_block_reason')}",
                    important=True,
                )
                continue

            trade_payload = apply_institutional_phase2(
                trade_payload=trade_payload,
                data=data,
                side=side,
                live_price=live_price,
            )

            if apply_data_advantage_layer is not None:
                trade_payload = apply_data_advantage_layer(
                    trade_payload=trade_payload,
                    symbol=symbol,
                    df=data,
                    side=side,
                    market_context=data_advantage_context,
                )

            if apply_meta_intelligence is not None:
                trade_payload = apply_meta_intelligence(trade_payload)

            trade_payload = apply_probability_fields(
                trade_payload,
                _probability_context(market_status, data_advantage_context),
            )
            trade_payload = apply_causal_fields(
                trade_payload,
                _probability_context(market_status, data_advantage_context),
            )

            trade_id = log_trade(
                trade_payload,
                scan_id=scan_id,
                alert_sent=False,
                market_status=market_status
            )

            insert_setup({
                "trade_id": trade_id,
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "stop_loss": stop_loss,
                "target": target,
                "rr": rr,
                "position_size": position_size,
                "quantity": quantity,
                "qty": quantity,
                "risk_amount": risk_amount,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct", 1.0),
                "scores": trade_payload.get("scores", {
                    "volume_score": volume_score,
                    "strength_score": strength_score,
                    "compression_score": comp_score,
                    "final_score": final_score
                }),
                "market_context": trade_payload.get("market_context", {
                    "market_status": market_status,
                    "trend": trend
                }),
                "setup_context": trade_payload.get("setup_context", {
                    "structure_ok": structure_result,
                    "momentum_ok": momentum_result,
                    "breakout_ready": entry_result,
                    "confirmations": confirmations,
                    "source": source
                }),
                "reason": reason,
                "trigger_status": trigger,
                "status": "OPEN"
            })

            insert_trade({
                "trade_id": trade_id,
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "stop_loss": stop_loss,
                "target": target,
                "rr": rr,
                "position_size": position_size,
                "quantity": quantity,
                "qty": quantity,
                "risk_amount": risk_amount,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct", 1.0),
                "scores": trade_payload.get("scores", {
                    "volume_score": volume_score,
                    "strength_score": strength_score,
                    "compression_score": comp_score,
                    "final_score": final_score
                }),
                "market_context": trade_payload.get("market_context", market_status),
                "setup_context": trade_payload.get("setup_context", {
                    "trend": trend,
                    "confirmations": confirmations,
                    "source": source
                }),
                "reason": reason,
                "trigger_status": trigger,
                "status": "OPEN"
            })

            setups.append(trade_payload)
            setup_symbols.append(symbol)
            scan_record["setup_count"] += 1

        except Exception as e:
            errors.append(f"{symbol}: {e}")
            print(f"❌ ERROR → {symbol}: {e}")
            continue

    if QUIET_MODE:
        print(
            f"[ScanSummary] Checked={stocks_checked} | Trend={trend_passed} | "
            f"Momentum={momentum_passed} | Structure={structure_passed} | "
            f"Entry={entry_passed} | Final={final_passed} | "
            f"Phase1Blocks={phase1_block_count} | Errors={len(errors)}"
        )
    else:
        print("========== SCAN FAILURE BREAKDOWN ==========")
        print(f"Stocks Checked: {stocks_checked}")
        print(f"No Live Price: {no_live_price_count}")
        print(f"No Valid Trend: {no_valid_trend_count}")
        print(f"Structure Fail: {structure_fail_count}")
        print(f"Momentum Fail: {momentum_fail_count}")
        print(f"Fake Breakout: {fake_breakout_count}")
        print(f"Relative Weak: {relative_weak_count}")
        print(f"Not Ready: {not_ready_count}")
        print(f"Quality Fail: {quality_fail_count}")
        print(f"Confluence Fail: {confluence_fail_count}")
        print(f"Levels Fail: {levels_fail_count}")
        print(f"RR Fail: {rr_fail_count}")
        print(f"Phase 1 Risk Blocks: {phase1_block_count}")
        print(f"Final Passed: {final_passed}")
        print("============================================")

    log_scan(
        total_symbols=total_symbols,
        scanned_symbols=scanned_symbols,
        setup_symbols=setup_symbols,
        errors=errors
    )

    save_scan_health_log(
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        momentum_passed=momentum_passed,
        structure_passed=structure_passed,
        entry_passed=entry_passed,
        final_passed=final_passed,
        alerts_sent=alerts_sent,
        market_status=market_status
    )

    if setups:
        setups = apply_probability_ranking(
            setups,
            _probability_context(market_status, data_advantage_context),
        )
        setups = apply_causal_ranking(
            setups,
            _probability_context(market_status, data_advantage_context),
        )
        titan_log(f"✅ Valid setups found: {len(setups)} setups")
    else:
        titan_log("No valid setups found.")

    return setups
