import os

QUIET_MODE = os.getenv("TITAN_QUIET_MODE", "0") == "1"
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from supabase import create_client

from signal_path_diagnostics import add_example, build_scan_report, save_scan_report
from data.loader import get_last_load_debug, load_cached_stock_data
from data.live_price import get_live_price_debug

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINAL_REJECTION_DEBUG_PATH = PROJECT_ROOT / "data" / "debug" / "final_rejection_breakdown.json"


def _normalize_final_rejection_reason(reason):
    reason = str(reason or "UNKNOWN").strip().upper()
    return {
        "STRUCTURE_FAIL": "STRUCTURE_WEAK",
        "MOMENTUM_FAIL": "MOMENTUM_WEAK",
        "QUALITY_FAIL": "LOW_FINAL_SCORE",
        "CONFLUENCE_FAIL": "ENTRY_CONFIRMATION_FAIL",
        "LEVELS_FAIL": "TRADE_LEVELS_INVALID",
        "RR_FAIL": "RISK_REWARD_INVALID",
        "NOT_READY": "ENTRY_CONFIRMATION_FAIL",
    }.get(reason, reason or "UNKNOWN")


def _record_final_rejection(counter, symbols_by_reason, symbol, reason):
    reason = _normalize_final_rejection_reason(reason)
    counter[reason] += 1
    symbols_by_reason.setdefault(reason, []).append(symbol)


def _save_final_rejection_breakdown(counter, symbols_by_reason, entry_passed, final_passed):
    payload = {
        "timestamp": datetime.now().isoformat(),
        "entry_passed": entry_passed,
        "final_passed": final_passed,
        "total_final_rejections_after_entry": sum(counter.values()),
        "breakdown": dict(counter.most_common()),
        "symbols_by_reason": {
            reason: symbols_by_reason.get(reason, [])
            for reason in dict(counter.most_common())
        },
    }

    try:
        FINAL_REJECTION_DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FINAL_REJECTION_DEBUG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    except Exception as e:
        titan_log(f"FINAL REJECTION DEBUG SAVE ERROR -> {e}", important=True)


def _print_final_rejection_breakdown(counter):
    print("FINAL REJECTION BREAKDOWN")
    print("-------------------------")

    if not counter:
        print("NONE : 0")
        return

    max_reason_len = max(len(reason) for reason in counter)
    for reason, count in counter.most_common():
        print(f"{reason.ljust(max_reason_len)} : {count}")



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
            qty = pos_data.get("qty") or pos_data.get("quantity") or 0
            position_size = pos_data.get("position_size") or 0
            skip_reason = pos_data.get("skip_reason") or ""
            return {
                "qty": qty,
                "quantity": qty,
                "computed_qty": pos_data.get("computed_qty") or qty,
                "position_size": position_size,
                "required_capital": pos_data.get("required_capital") or position_size,
                "risk_amount": pos_data.get("risk_amount") or pos_data.get("risk") or 0,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct") or 1.0,
                "risk_per_share": pos_data.get("risk_per_share") or abs(float(entry) - float(stop_loss)),
                "account_balance": pos_data.get("account_balance") or 1000.0,
                "skip_reason": skip_reason,
                "rejection_reason": pos_data.get("rejection_reason") or skip_reason,
                "sizing_valid": bool(qty),
                "raw": pos_data
            }

        if isinstance(pos_data, (tuple, list)):
            qty = pos_data[0] if len(pos_data) > 0 else 0
            position_size = qty * entry
            return {
                "qty": qty,
                "quantity": qty,
                "computed_qty": qty,
                "position_size": position_size,
                "required_capital": position_size,
                "risk_amount": pos_data[1] if len(pos_data) > 1 else 0,
                "risk_per_trade_pct": 1.0,
                "risk_per_share": abs(float(entry) - float(stop_loss)),
                "account_balance": 1000.0,
                "skip_reason": "",
                "rejection_reason": "",
                "sizing_valid": bool(qty),
                "raw": list(pos_data)
            }

        return {
            "qty": 0,
            "quantity": 0,
            "computed_qty": 0,
            "position_size": 0,
            "required_capital": 0,
            "risk_amount": 0,
            "risk_per_trade_pct": 1.0,
            "risk_per_share": 0,
            "account_balance": 1000.0,
            "skip_reason": "MICRO_CAPITAL_QTY_INVALID",
            "rejection_reason": "MICRO_CAPITAL_QTY_INVALID",
            "sizing_valid": False,
            "raw": pos_data
        }

    except Exception as e:
        titan_log(f"POSITION SIZE ERROR → {e}")
        return {
            "qty": 0,
            "quantity": 0,
            "computed_qty": 0,
            "position_size": 0,
            "required_capital": 0,
            "risk_amount": 0,
            "risk_per_trade_pct": 1.0,
            "risk_per_share": 0,
            "account_balance": 1000.0,
            "skip_reason": "MICRO_CAPITAL_QTY_INVALID",
            "rejection_reason": "MICRO_CAPITAL_QTY_INVALID",
            "sizing_valid": False,
            "raw": None
        }


def _paper_sizing_debug_text(sizing, rejection_reason=""):
    if not isinstance(sizing, dict):
        sizing = {}
    reason = rejection_reason or sizing.get("rejection_reason") or sizing.get("skip_reason") or ""
    return (
        f"account_balance={sizing.get('account_balance')} | "
        f"computed_qty={sizing.get('computed_qty', sizing.get('quantity') or sizing.get('qty'))} | "
        f"required_capital={sizing.get('required_capital', sizing.get('position_size'))} | "
        f"risk_amount={sizing.get('risk_amount')} | "
        f"rejection_reason={reason}"
    )


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
    Fail-open probability annotation. It never blocks, rejects, writes live
    rank fields, or changes setup order. Phase 15 live probability ranking is
    owned by titan_master_brain.final_decision_engine.
    """
    if not isinstance(setup, dict):
        return setup

    result = dict(setup)

    if build_probability_report is None:
        result["probability_rank_role"] = "advisory_setup_only"
        return result

    try:
        report = build_probability_report(result, context if isinstance(context, dict) else {})
        probability_score = _safe_float(report.get("final_probability_score"), _existing_rank_score(result))

        # Backward-compatible metadata only; final_decision_engine recomputes
        # the canonical blended_rank_score from the original live score.
        result["probability_score"] = probability_score
        result["advisory_probability_score"] = probability_score
        result["probability_recommendation"] = report.get("recommendation")
        result["advisory_probability_recommendation"] = report.get("recommendation")
        result["probability_expected_value"] = report.get("expected_value")
        result["probability_confidence"] = report.get("probability_confidence_score")
        result["probability_uncertainty"] = report.get("uncertainty_score")
        result["probability_explanations"] = report.get("explanations", [])
        result["probability_rank_role"] = "advisory_setup_only"
    except Exception as e:
        result["probability_error"] = str(e)
        result["probability_rank_role"] = "advisory_setup_only"

    return result


def apply_probability_ranking(setups, context):
    if not isinstance(setups, list):
        return []

    # Kept for compatibility with existing call sites, but intentionally no
    # longer ranks. The canonical Phase 15 live ranking layer is final_decision_engine.
    return [apply_probability_fields(setup, context) for setup in setups]


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
    final_rejection_breakdown = Counter()
    final_rejection_symbols = {}
    trend_rejection_breakdown = Counter()
    structure_rejection_breakdown = Counter()
    momentum_rejection_breakdown = Counter()
    entry_rejection_breakdown = Counter()
    trend_rejection_symbols = {}
    structure_rejection_symbols = {}
    momentum_rejection_symbols = {}
    entry_rejection_symbols = {}
    upstox_count = 0
    live_cache_count = 0
    csv_close_count = 0
    unknown_price_count = 0

    symbols = load_cached_stock_data()
    total_symbols = len(symbols)
    loader_debug = get_last_load_debug()
    selected_set_hash = loader_debug.get("selected_set_hash")
    selected_symbols_count = loader_debug.get("selected_symbols_count", total_symbols)
    repeated_selection_warning = bool(loader_debug.get("repeated_selection_warning"))
    stale_cache_count = int(loader_debug.get("stale_cache_count") or 0)
    cache_debug = loader_debug.get("cache_debug") or {}

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
    titan_log(
        f"SCAN DEBUG | selected_set_hash={selected_set_hash} | "
        f"selected_symbols_count={selected_symbols_count} | "
        f"repeated_selection_warning={repeated_selection_warning} | "
        f"stale_cache_count={stale_cache_count}",
        important=True,
    )

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

            price_debug = get_live_price_debug(symbol)
            live_price = price_debug.get("price")
            source = price_debug.get("source") or "UNKNOWN"
            price_status = price_debug.get("status") or "UNKNOWN"
            price_reason = price_debug.get("reason") or ""
            symbol_cache_debug = cache_debug.get(symbol, {})

            if live_price is None:
                try:
                    live_price = float(data["Close"].iloc[-1])
                    source = "CSV_CLOSE"
                    price_status = "CSV_CLOSE"
                    price_reason = "Live price unavailable; using selected CSV Close"
                except Exception:
                    source = "UNKNOWN"
                    no_live_price_count += 1
                    unknown_price_count += 1
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
                        "reason": "NO_LIVE_PRICE",
                        "source": source,
                        "price_source": source,
                        "price_status": price_status,
                        "price_reason": price_reason,
                        "selected_set_hash": selected_set_hash,
                        "selected_symbols_count": selected_symbols_count,
                        "repeated_selection_warning": repeated_selection_warning,
                        "stale_cache_count": stale_cache_count,
                        "cache_stale": bool(symbol_cache_debug.get("cache_stale")),
                        "cache_age_hours": symbol_cache_debug.get("cache_age_hours"),
                    })
                    continue

            if source == "UPSTOX":
                upstox_count += 1
            elif source == "LIVE_PRICE_CACHE":
                live_cache_count += 1
            elif source == "CSV_CLOSE":
                csv_close_count += 1
            else:
                unknown_price_count += 1

            trend = trend_direction(data)
            side = trade_side_from_trend(trend)

            if side is None:
                no_valid_trend_count += 1
                trend_rejection_breakdown["NO_VALID_TREND"] += 1
                add_example(trend_rejection_symbols, "NO_VALID_TREND", symbol)
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
                    "reason": "NO_VALID_TREND",
                    "source": source,
                    "price_source": source,
                    "price_status": price_status,
                    "price_reason": price_reason,
                    "selected_set_hash": selected_set_hash,
                    "selected_symbols_count": selected_symbols_count,
                    "repeated_selection_warning": repeated_selection_warning,
                    "stale_cache_count": stale_cache_count,
                    "cache_stale": bool(symbol_cache_debug.get("cache_stale")),
                    "cache_age_hours": symbol_cache_debug.get("cache_age_hours"),
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
                structure_rejection_breakdown[fail_reason] += 1
                add_example(structure_rejection_symbols, fail_reason, symbol)

            elif not momentum_result:
                momentum_fail_count += 1
                fail_reason = "MOMENTUM_FAIL"
                momentum_rejection_breakdown[fail_reason] += 1
                add_example(momentum_rejection_symbols, fail_reason, symbol)

            elif not fake_breakout_ok:
                fake_breakout_count += 1
                fail_reason = "FAKE_BREAKOUT"
                entry_rejection_breakdown[fail_reason] += 1
                add_example(entry_rejection_symbols, fail_reason, symbol)

            elif not relative_strength_result:
                relative_weak_count += 1
                fail_reason = "RELATIVE_WEAK"
                entry_rejection_breakdown[fail_reason] += 1
                add_example(entry_rejection_symbols, fail_reason, symbol)

            elif not entry_result:
                not_ready_count += 1
                fail_reason = "NOT_READY"
                entry_rejection_breakdown[fail_reason] += 1
                add_example(entry_rejection_symbols, fail_reason, symbol)

            elif not quality_ok:
                quality_fail_count += 1
                fail_reason = "QUALITY_FAIL"
                entry_rejection_breakdown[fail_reason] += 1
                add_example(entry_rejection_symbols, fail_reason, symbol)

            elif confirmations < 3:
                confluence_fail_count += 1
                fail_reason = "CONFLUENCE_FAIL"
                entry_rejection_breakdown[fail_reason] += 1
                add_example(entry_rejection_symbols, fail_reason, symbol)

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
                                (
                                    f"FILTER RESULT -> {symbol} | PAPER_SIZE_SKIP | {micro_skip_reason} | "
                                    f"{_paper_sizing_debug_text(pos_data, micro_skip_reason)}"
                                ),
                                important=True,
                            )
                        elif not pos_data.get("sizing_valid", quantity and position_size) or int(quantity or 0) < 1:
                            fail_reason = pos_data.get("skip_reason", "MICRO_CAPITAL_QTY_INVALID")
                            titan_log(
                                (
                                    f"FILTER RESULT -> {symbol} | PAPER_SIZE_SKIP | {fail_reason} | "
                                    f"{_paper_sizing_debug_text(pos_data, fail_reason)}"
                                ),
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
                "reason": fail_reason,
                "source": source,
                "price_source": source,
                "price_status": price_status,
                "price_reason": price_reason,
                "selected_set_hash": selected_set_hash,
                "selected_symbols_count": selected_symbols_count,
                "repeated_selection_warning": repeated_selection_warning,
                "stale_cache_count": stale_cache_count,
                "cache_stale": bool(symbol_cache_debug.get("cache_stale")),
                "cache_age_hours": symbol_cache_debug.get("cache_age_hours"),
                "account_balance": (pos_data or {}).get("account_balance"),
                "computed_qty": (pos_data or {}).get("computed_qty", quantity),
                "required_capital": (pos_data or {}).get("required_capital", position_size),
                "risk_amount": risk_amount,
                "rejection_reason": fail_reason if not passed else "",
            })

            titan_log(f"FILTER RESULT → {symbol} | {fail_reason}")

            if not passed:
                if entry_result:
                    _record_final_rejection(
                        final_rejection_breakdown,
                        final_rejection_symbols,
                        symbol,
                        fail_reason,
                    )
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
                "computed_qty": pos_data.get("computed_qty", quantity),
                "required_capital": pos_data.get("required_capital", position_size),
                "account_balance": pos_data.get("account_balance"),
                "risk_amount": risk_amount,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct", 1.0),
                "rejection_reason": fail_reason if not passed else "",
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
                _record_final_rejection(
                    final_rejection_breakdown,
                    final_rejection_symbols,
                    symbol,
                    trade_payload.get("phase1_block_reason") or "PHASE1_RISK_BLOCK",
                )
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
                "computed_qty": pos_data.get("computed_qty", quantity),
                "required_capital": pos_data.get("required_capital", position_size),
                "account_balance": pos_data.get("account_balance"),
                "risk_amount": risk_amount,
                "risk_per_trade_pct": pos_data.get("risk_per_trade_pct", 1.0),
                "rejection_reason": "",
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
        print(
            f"[ScanDebug] selected_set_hash={selected_set_hash} | "
            f"selected_symbols_count={selected_symbols_count} | "
            f"repeated_selection_warning={repeated_selection_warning} | "
            f"stale_cache_count={stale_cache_count} | "
            f"upstox_count={upstox_count} | live_cache_count={live_cache_count} | "
            f"csv_close_count={csv_close_count} | unknown_price_count={unknown_price_count}"
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
        print("========== SCAN DEBUG ==========")
        print(f"Selected Set Hash: {selected_set_hash}")
        print(f"Selected Symbols Count: {selected_symbols_count}")
        print(f"Repeated Selection Warning: {repeated_selection_warning}")
        print(f"Stale Cache Count: {stale_cache_count}")
        print(f"UPSTOX Count: {upstox_count}")
        print(f"Live Price Cache Count: {live_cache_count}")
        print(f"CSV Close Count: {csv_close_count}")
        print(f"Unknown Price Count: {unknown_price_count}")
        print("============================================")

    _print_final_rejection_breakdown(final_rejection_breakdown)
    _save_final_rejection_breakdown(
        final_rejection_breakdown,
        final_rejection_symbols,
        entry_passed,
        final_passed,
    )
    save_scan_report(
        build_scan_report(
            scan_cycle_id=str(scan_id),
            stocks_checked=stocks_checked,
            trend_passed=trend_passed,
            momentum_passed=momentum_passed,
            structure_passed=structure_passed,
            entry_passed=entry_passed,
            final_passed=final_passed,
            alerts_sent=alerts_sent,
            trend_reasons=trend_rejection_breakdown,
            trend_examples=trend_rejection_symbols,
            momentum_reasons=momentum_rejection_breakdown,
            momentum_examples=momentum_rejection_symbols,
            structure_reasons=structure_rejection_breakdown,
            structure_examples=structure_rejection_symbols,
            entry_reasons=entry_rejection_breakdown,
            entry_examples=entry_rejection_symbols,
            setup_reasons=final_rejection_breakdown,
            setup_examples=final_rejection_symbols,
            setup_received=entry_passed,
            setup_rejected=sum(final_rejection_breakdown.values()),
            market_filters={
                "market_regime": market_status,
                "volatility_filter": None,
                "news_filter": None,
                "risk_filter": {
                    "phase1_blocks": phase1_block_count,
                },
            },
            breakout_ready=entry_passed,
        )
    )

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
