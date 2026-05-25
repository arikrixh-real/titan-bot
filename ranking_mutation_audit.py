import ast
import json
from pathlib import Path

from utils.market_hours import as_ist_datetime


AUDIT_PATH = Path("data") / "runtime" / "ranking_mutation_audit.json"
PROJECT_ROOT = Path(".")
AUTHORITATIVE_OWNER = "titan_master_brain/final_decision_engine.py"
RANKING_FIELDS = {
    "final_score": "final_score_write",
    "rank_score": "rank_score_write",
    "score": "setup_score_write",
    "blended_rank_score": "setup_ranking_write",
    "new_blended_rank_score": "setup_ranking_write",
    "final_master_rank": "setup_ranking_write",
    "final_cross_asset_rank": "setup_ranking_write",
    "final_portfolio_rank": "setup_ranking_write",
    "final_microstructure_rank": "setup_ranking_write",
    "final_options_rank": "setup_ranking_write",
    "final_news_intelligence_rank": "setup_ranking_write",
    "final_calendar_rank": "setup_ranking_write",
    "final_liquidity_rank": "setup_ranking_write",
    "final_scenario_rank": "setup_ranking_write",
    "final_debate_rank": "setup_ranking_write",
    "final_reflection_rank": "setup_ranking_write",
    "final_calibration_rank": "setup_ranking_write",
    "final_no_trade_rank": "setup_ranking_write",
    "daily_alert_rank": "signal_ordering_write",
    "confidence": "confidence_write",
    "confidence_score": "confidence_write",
    "recommendation": "recommendation_write",
    "trade_recommendation": "recommendation_write",
    "priority": "trade_priority_write",
    "priority_count": "trade_priority_write",
    "selected_for_alert": "signal_ordering_write",
}
LIVE_RANK_FIELDS = {
    "blended_rank_score",
    "new_blended_rank_score",
    "final_master_rank",
    "final_cross_asset_rank",
    "final_portfolio_rank",
    "final_microstructure_rank",
    "final_options_rank",
    "final_news_intelligence_rank",
    "final_calendar_rank",
    "final_liquidity_rank",
    "final_scenario_rank",
    "final_debate_rank",
    "final_reflection_rank",
    "final_calibration_rank",
    "final_no_trade_rank",
}
DOWNSTREAM_ORDERING_FIELDS = {"daily_alert_rank", "selected_for_alert"}

SAFETY_FLAGS = {
    "advisory_only": True,
    "affects_live_ranking": False,
    "affects_execution": False,
    "broker_mutation": False,
    "telegram_mutation": False,
    "supabase_mutation": False,
    "live_order_behavior": False,
    "recommended_live_weight": 0.0,
    "rank_adjustment": 0.0,
}


def _normal_path(path):
    return str(Path(path)).replace("\\", "/")


def _candidate_files(root=PROJECT_ROOT):
    root = Path(root)
    files = [root / "setup_engine.py", root / AUTHORITATIVE_OWNER]
    files.extend(sorted((root / "engines").glob("*.py")))
    files.extend(sorted((root / "titan_master_brain").glob("*.py")))
    seen = set()
    result = []
    for path in files:
        normal = _normal_path(path)
        if path.exists() and normal not in seen:
            seen.add(normal)
            result.append(path)
    return result


def _function_for_line(tree, line_number):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            if start <= line_number <= end and (best is None or start >= best[0]):
                best = (start, node.name)
    return best[1] if best else "<module>"


def _constant_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _owner(path):
    normal = _normal_path(path)
    if normal.endswith(AUTHORITATIVE_OWNER):
        return "authoritative"
    return "non_authoritative"


def _component(path):
    normal = _normal_path(path)
    if normal.endswith(AUTHORITATIVE_OWNER):
        return "final_decision_engine"
    if normal.endswith("setup_engine.py") or normal.endswith("engines/setup_engine.py"):
        return "setup_engine"
    if "roadmap_" in Path(path).name or "strategy_genome" in Path(path).name:
        return "roadmap_sidecar"
    if "reinforcement_learning" in Path(path).name:
        return "reinforcement_learning"
    if "replay" in Path(path).name or "research" in Path(path).name:
        return "research_system"
    if "data_advantage" in Path(path).name:
        return "data_advantage"
    if "meta_intelligence" in Path(path).name or "meta_" in Path(path).name:
        return "meta_intelligence"
    return "advisory_engine"


def _runtime_active(path):
    name = Path(path).name
    normal = _normal_path(path)
    return bool(
        normal.endswith("setup_engine.py")
        or normal.endswith(AUTHORITATIVE_OWNER)
        or name in {"daily_alert_manager.py", "master_controller.py", "setup_reasoning_engine.py", "setup_normalizer.py"}
    )


def _advisory(path, field):
    normal = _normal_path(path)
    if normal.endswith(AUTHORITATIVE_OWNER):
        return False
    if field in DOWNSTREAM_ORDERING_FIELDS:
        return False
    return True


def _downstream_effect(path, field):
    if field in DOWNSTREAM_ORDERING_FIELDS:
        return "alert_slot_ordering_visibility"
    if field in LIVE_RANK_FIELDS:
        return "live_rank_chain_input_or_override"
    if field in {"final_score", "rank_score", "score"}:
        return "setup_candidate_score_input"
    if "confidence" in field:
        return "confidence_annotation"
    if "recommendation" in field:
        return "recommendation_annotation"
    return "advisory_metadata"


def _dangerous(path, field):
    normal = _normal_path(path)
    if normal.endswith(AUTHORITATIVE_OWNER):
        return False
    return field in LIVE_RANK_FIELDS and _runtime_active(path)


def _record(path, tree, field, lineno, write_shape):
    owner = _owner(path)
    return {
        "file": _normal_path(path),
        "line": lineno,
        "function": _function_for_line(tree, lineno),
        "field": field,
        "mutation_type": RANKING_FIELDS.get(field, "ranking_related_write"),
        "write_shape": write_shape,
        "owner_classification": owner,
        "component": _component(path),
        "authoritative": owner == "authoritative",
        "advisory": _advisory(path, field),
        "runtime_active": _runtime_active(path),
        "dangerous_override": _dangerous(path, field),
        "downstream_effect": _downstream_effect(path, field),
    }


def _scan_file(path):
    try:
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        return [{"file": _normal_path(path), "error": str(exc), "mutation_type": "parse_error"}]

    records = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        elif isinstance(node, ast.AugAssign):
            targets.append(node.target)
        for target in targets:
            if isinstance(target, ast.Subscript):
                field = _constant_string(target.slice)
                if field in RANKING_FIELDS:
                    records.append(_record(path, tree, field, target.lineno, "subscript_assignment"))
            elif isinstance(target, ast.Name) and target.id in {"selected_for_alert"}:
                records.append(_record(path, tree, target.id, target.lineno, "name_assignment"))
        if isinstance(node, ast.Dict):
            for key in node.keys:
                field = _constant_string(key)
                if field in RANKING_FIELDS:
                    records.append(_record(path, tree, field, getattr(key, "lineno", node.lineno), "dict_literal"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
            records.append(
                {
                    "file": _normal_path(path),
                    "line": node.lineno,
                    "function": _function_for_line(tree, node.lineno),
                    "field": "sort",
                    "mutation_type": "signal_ordering_write",
                    "write_shape": "sort_call",
                    "owner_classification": _owner(path),
                    "component": _component(path),
                    "authoritative": _owner(path) == "authoritative",
                    "advisory": _owner(path) != "authoritative",
                    "runtime_active": _runtime_active(path),
                    "dangerous_override": False,
                    "downstream_effect": "ordering_operation",
                }
            )
    return records


def run_ranking_mutation_audit(path=None, now=None, root=None):
    if path is None:
        path = AUDIT_PATH
    if root is None:
        root = PROJECT_ROOT
    now_ist = as_ist_datetime(now)
    mutations = []
    for file_path in _candidate_files(root):
        mutations.extend(_scan_file(file_path))

    dangerous = [item for item in mutations if item.get("dangerous_override")]
    fields_to_files = {}
    for item in mutations:
        field = item.get("field")
        if not field or field == "sort":
            continue
        fields_to_files.setdefault(field, set()).add(item.get("file"))
    duplicate_writers = {
        field: sorted(files)
        for field, files in fields_to_files.items()
        if len(files) > 1 and field in LIVE_RANK_FIELDS.union({"final_score", "rank_score", "daily_alert_rank"})
    }
    runtime_fields_to_files = {}
    for item in mutations:
        field = item.get("field")
        if not field or field == "sort" or not item.get("runtime_active"):
            continue
        runtime_fields_to_files.setdefault(field, set()).add(item.get("file"))
    duplicate_runtime_writers = {
        field: sorted(files)
        for field, files in runtime_fields_to_files.items()
        if len(files) > 1 and field in LIVE_RANK_FIELDS.union({"final_score", "rank_score", "daily_alert_rank"})
    }

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "authoritative_owner": "final_decision_engine",
        "authoritative_owner_path": AUTHORITATIVE_OWNER,
        "total_mutations": len(mutations),
        "mutations": mutations,
        "dangerous_live_overrides": dangerous,
        "duplicate_rank_writers": duplicate_writers,
        "duplicate_runtime_rank_writers": duplicate_runtime_writers,
        "advisory_only_mutators": sorted({item.get("component") for item in mutations if item.get("advisory")}),
        "runtime_active_mutators": sorted({item.get("component") for item in mutations if item.get("runtime_active")}),
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_ranking_mutation_audit(), indent=2, sort_keys=True))
