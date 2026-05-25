import ast
import json
from pathlib import Path

from ranking_integrity import build_ranking_integrity_status
from runtime_dependency_graph import SAFETY_FLAGS
from utils.market_hours import as_ist_datetime


PROJECT_ROOT = Path(".")
RUNTIME_DIR = Path("data") / "runtime"

ADVISORY_MUTATION_AUDIT_PATH = RUNTIME_DIR / "advisory_mutation_audit.json"
LIVE_MUTATION_GUARD_STATUS_PATH = RUNTIME_DIR / "live_mutation_guard_status.json"
SHADOW_SYSTEM_ISOLATION_STATUS_PATH = RUNTIME_DIR / "shadow_system_isolation_status.json"

ADVISORY_PATH_PREFIXES = (
    "engines/roadmap_",
    "engines/meta_",
    "engines/reinforcement_learning",
    "engines/strategy_genome",
    "engines/accuracy_validation",
    "engines/backtesting_validation",
    "engines/autonomous_research",
    "engines/evolution",
    "engines/self_reflection",
    "engines/master_shadow",
    "engines/scenario_simulation",
    "research/",
    "consciousness_core/",
    "runtime_historical_replay.py",
)

FORBIDDEN_LIVE_CALLS = {
    "send_telegram_signals",
    "send_telegram_message",
    "place_order",
    "execute_order",
    "execute_trade",
    "prepare_execution_packets",
    "filter_alert_candidates",
    "select_daily_alerts",
    "mark_alerts_sent",
    "_safe_supabase_insert",
    "_safe_supabase_update",
    "track_trade_outcomes",
}

FORBIDDEN_LIVE_ASSIGN_KEYS = {
    "broker_state",
    "telegram_state",
    "supabase_state",
    "execution_packets",
    "scanner_output",
    "selected_for_alert",
    "live_order_allowed",
    "live_rank_mutation_allowed",
    "affects_execution",
    "affects_live_ranking",
    "broker_mutation",
    "telegram_mutation",
    "supabase_mutation",
    "live_order_behavior",
}

MUTATION_FLAG_FALSE_IS_SAFE = {
    "live_order_allowed",
    "live_rank_mutation_allowed",
    "affects_execution",
    "affects_live_ranking",
    "broker_mutation",
    "telegram_mutation",
    "supabase_mutation",
    "live_order_behavior",
}


def _path_key(path):
    return str(Path(path)).replace("\\", "/")


def _normal_relative(path, root=None):
    root = Path(root or PROJECT_ROOT)
    path = Path(path)
    try:
        return _path_key(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return _path_key(path)


def _candidate_files(root=None):
    root = Path(root or PROJECT_ROOT)
    candidates = []
    for prefix in ADVISORY_PATH_PREFIXES:
        prefix_path = root / prefix
        if prefix.endswith(".py"):
            if prefix_path.exists():
                candidates.append(prefix_path)
            continue
        parent = prefix_path.parent
        if not parent.exists():
            continue
        pattern = f"{prefix_path.name}*.py" if prefix_path.name else "*.py"
        candidates.extend(sorted(parent.glob(pattern)))
    seen = set()
    result = []
    for path in candidates:
        key = _normal_relative(path, root)
        if path.exists() and key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _constant_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _constant_bool(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def _function_for_line(tree, line_number):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            if start <= line_number <= end and (best is None or start >= best[0]):
                best = (start, node.name)
    return best[1] if best else "<module>"


def _system_role(relative):
    name = Path(relative).name
    if relative.startswith("engines/roadmap_"):
        return "roadmap_phase"
    if "replay" in relative or relative.startswith("research/"):
        return "replay_or_research_system"
    if "reinforcement_learning" in relative:
        return "reinforcement_learning_shadow"
    if "meta_" in name or "self_reflection" in name:
        return "meta_learning_or_reflection"
    if "strategy_genome" in name or "evolution" in name:
        return "strategy_mutation_or_evolution_shadow"
    if relative.startswith("consciousness_core/"):
        return "consciousness_sidecar"
    return "advisory_sidecar"


def _dict_safety_flags(node):
    flags = {}
    if not isinstance(node, ast.Dict):
        return flags
    for key, value in zip(node.keys, node.values):
        field = _constant_string(key)
        if field in FORBIDDEN_LIVE_ASSIGN_KEYS:
            bool_value = _constant_bool(value)
            if bool_value is not None:
                flags[field] = bool_value
    return flags


def _scan_file(path, root=None):
    relative = _normal_relative(path, root)
    try:
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        return {
            "file": relative,
            "system_role": _system_role(relative),
            "parse_error": str(exc),
            "safety_flags_found": {},
            "unsafe_live_mutation_vectors": [{"type": "parse_error", "error": str(exc)}],
        }

    safety_flags = {}
    unsafe = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            flags = _dict_safety_flags(node)
            safety_flags.update(flags)
            for field, value in flags.items():
                if field in MUTATION_FLAG_FALSE_IS_SAFE and value is True:
                    unsafe.append(
                        {
                            "type": "unsafe_true_mutation_flag",
                            "field": field,
                            "line": getattr(node, "lineno", None),
                            "function": _function_for_line(tree, getattr(node, "lineno", 0)),
                        }
                    )
        if isinstance(node, ast.Call):
            call_name = None
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            if call_name in FORBIDDEN_LIVE_CALLS:
                unsafe.append(
                    {
                        "type": "forbidden_live_call",
                        "call": call_name,
                        "line": node.lineno,
                        "function": _function_for_line(tree, node.lineno),
                    }
                )
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
                if field in FORBIDDEN_LIVE_ASSIGN_KEYS and field not in MUTATION_FLAG_FALSE_IS_SAFE:
                    unsafe.append(
                        {
                            "type": "forbidden_live_state_assignment",
                            "field": field,
                            "line": target.lineno,
                            "function": _function_for_line(tree, target.lineno),
                        }
                    )

    expected_false = {
        field: safety_flags.get(field)
        for field in MUTATION_FLAG_FALSE_IS_SAFE
        if field in safety_flags
    }
    return {
        "file": relative,
        "system_role": _system_role(relative),
        "safety_flags_found": dict(sorted(safety_flags.items())),
        "expected_false_flags": dict(sorted(expected_false.items())),
        "unsafe_live_mutation_vectors": unsafe,
        "isolated": not unsafe,
        "advisory_only": safety_flags.get("affects_live_ranking") is False
        and safety_flags.get("affects_execution") is False,
    }


def build_advisory_mutation_audit(path=None, root=None, now=None):
    path = Path(path or ADVISORY_MUTATION_AUDIT_PATH)
    root = Path(root or PROJECT_ROOT)
    now_ist = as_ist_datetime(now)
    systems = [_scan_file(candidate, root=root) for candidate in _candidate_files(root=root)]
    unsafe = [
        {"file": item["file"], "vectors": item.get("unsafe_live_mutation_vectors") or []}
        for item in systems
        if item.get("unsafe_live_mutation_vectors")
    ]
    role_counts = {}
    for item in systems:
        role_counts[item["system_role"]] = role_counts.get(item["system_role"], 0) + 1
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "advisory_mutation_audit_status": "WARNING" if unsafe else "PASS",
        "systems_scanned": len(systems),
        "system_role_counts": dict(sorted(role_counts.items())),
        "unsafe_live_mutation_vector_count": sum(len(item["vectors"]) for item in unsafe),
        "unsafe_live_mutation_vectors": unsafe,
        "systems": systems,
        "mutation_containment_policy": {
            "advisory_systems_may_write_visibility_artifacts": True,
            "advisory_systems_may_mutate_live_ranking": False,
            "advisory_systems_may_mutate_execution": False,
            "advisory_systems_may_mutate_broker": False,
            "advisory_systems_may_mutate_telegram": False,
            "advisory_systems_may_mutate_supabase": False,
            "advisory_systems_may_mutate_dashboard_rendering": False,
            "automatic_remediation": False,
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_live_mutation_guard_status(audit=None, ranking=None, path=None, now=None):
    path = Path(path or LIVE_MUTATION_GUARD_STATUS_PATH)
    now_ist = as_ist_datetime(now)
    audit = audit if isinstance(audit, dict) else build_advisory_mutation_audit(now=now_ist)
    ranking = ranking if isinstance(ranking, dict) else build_ranking_integrity_status(now=now_ist)
    unsafe_vectors = audit.get("unsafe_live_mutation_vectors") or []
    dangerous_ranking = ranking.get("dangerous_live_overrides") or []
    failures = []
    warnings = []
    if dangerous_ranking:
        failures.append("dangerous_live_ranking_override_detected")
    if unsafe_vectors:
        warnings.append("advisory_live_mutation_vector_detected")
    if ranking.get("authoritative_owner") != "final_decision_engine":
        failures.append("ranking_owner_changed")
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "live_mutation_guard_status": "FAIL" if failures else ("WARNING" if warnings else "PASS"),
        "authoritative_ranking_owner": ranking.get("authoritative_owner"),
        "ranking_chain_valid": ranking.get("ranking_chain_valid"),
        "dangerous_live_overrides": dangerous_ranking,
        "advisory_live_mutation_vectors": unsafe_vectors,
        "guard_visibility": {
            "blocks_silent_live_rank_leakage": True,
            "blocks_silent_execution_leakage": True,
            "blocks_silent_broker_leakage": True,
            "blocks_silent_telegram_leakage": True,
            "blocks_silent_supabase_leakage": True,
            "visibility_only_no_runtime_mutation": True,
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_shadow_system_isolation_status(audit=None, path=None, now=None):
    path = Path(path or SHADOW_SYSTEM_ISOLATION_STATUS_PATH)
    now_ist = as_ist_datetime(now)
    audit = audit if isinstance(audit, dict) else build_advisory_mutation_audit(now=now_ist)
    systems = audit.get("systems") or []
    isolated = [item for item in systems if item.get("isolated")]
    leaking = [item for item in systems if not item.get("isolated")]
    role_status = {}
    for item in systems:
        role = item.get("system_role")
        role_status.setdefault(role, {"total": 0, "isolated": 0, "leaking": 0})
        role_status[role]["total"] += 1
        if item.get("isolated"):
            role_status[role]["isolated"] += 1
        else:
            role_status[role]["leaking"] += 1
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "shadow_system_isolation_status": "WARNING" if leaking else "PASS",
        "systems_scanned": len(systems),
        "isolated_system_count": len(isolated),
        "leaking_system_count": len(leaking),
        "role_status": dict(sorted(role_status.items())),
        "leaking_systems": [
            {
                "file": item.get("file"),
                "system_role": item.get("system_role"),
                "unsafe_live_mutation_vectors": item.get("unsafe_live_mutation_vectors") or [],
            }
            for item in leaking
        ],
        "isolation_contract": {
            "roadmap_phases_advisory_only": True,
            "replay_systems_research_only": True,
            "research_systems_shadow_only": True,
            "meta_learning_systems_shadow_only": True,
            "rl_systems_shadow_only": True,
            "sidecar_systems_visibility_only": True,
            "affects_live_ranking": False,
            "affects_execution": False,
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_batch10_mutation_containment(now=None):
    now_ist = as_ist_datetime(now)
    audit = build_advisory_mutation_audit(now=now_ist)
    guard = build_live_mutation_guard_status(audit=audit, now=now_ist)
    isolation = build_shadow_system_isolation_status(audit=audit, now=now_ist)
    statuses = [
        audit.get("advisory_mutation_audit_status"),
        guard.get("live_mutation_guard_status"),
        isolation.get("shadow_system_isolation_status"),
    ]
    status = "FAIL" if "FAIL" in statuses else ("WARNING" if "WARNING" in statuses else "PASS")
    return {
        "generated_at_ist": now_ist.isoformat(),
        "batch": "BATCH_10_ADVISORY_MUTATION_CONTAINMENT",
        "status": status,
        "artifacts": {
            "advisory_mutation_audit": _path_key(ADVISORY_MUTATION_AUDIT_PATH),
            "live_mutation_guard_status": _path_key(LIVE_MUTATION_GUARD_STATUS_PATH),
            "shadow_system_isolation_status": _path_key(SHADOW_SYSTEM_ISOLATION_STATUS_PATH),
        },
        "summary": {
            "systems_scanned": audit.get("systems_scanned"),
            "unsafe_live_mutation_vector_count": audit.get("unsafe_live_mutation_vector_count"),
            "authoritative_ranking_owner": guard.get("authoritative_ranking_owner"),
            "leaking_system_count": isolation.get("leaking_system_count"),
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }


if __name__ == "__main__":
    print(json.dumps(run_batch10_mutation_containment(), indent=2, sort_keys=True))
