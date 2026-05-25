import json
from datetime import datetime
from pathlib import Path

from engines.time_filter import get_mode_permissions
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from market_data_health import run_market_data_health_check
from runtime_health import run_authoritative_runtime_health_check
from runtime_mode_router import runtime_mode_snapshot
from runtime_topology import build_runtime_topology
from utils.market_hours import IST, as_ist_datetime


STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
HISTORICAL_REPLAY_STATUS_PATH = Path("data") / "runtime" / "historical_replay_status.json"
HISTORICAL_REPLAY_PROGRESS_PATH = Path("data") / "runtime" / "historical_replay_progress.json"
HISTORICAL_EXPERIENCE_REPORT_PATH = (
    Path("data") / "experience_vault" / "imported_trade_logs" / "historical_experience_import_report.json"
)
HISTORICAL_EXPERIENCE_CSV_PATH = (
    Path("data") / "experience_vault" / "imported_trade_logs" / "historical_experience_import.csv"
)
HISTORICAL_EXPERIENCE_JSONL_PATH = (
    Path("data") / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl"
)
PHASE39_STALE_REPLAY_SECONDS = 24 * 60 * 60
PHASE_STATUS_ARTIFACTS = {
    "phase21_autonomous_research": {
        "path": Path("data") / "research" / "autonomous_research_report.json",
        "placement": "master_controller_research_sidecar",
        "mode": "research_only",
        "fields": ("research_mode", "research_priority_score"),
    },
    "phase22_backtesting_validation": {
        "path": Path("data") / "research" / "backtesting_validation_report.json",
        "placement": "master_controller_validation_sidecar",
        "mode": "research_only",
        "fields": ("validation_status", "validation_score"),
    },
    "phase23_paper_trading": {
        "path": Path("data") / "paper_trading" / "latest_paper_trading_report.json",
        "fallback_path": Path("data") / "runtime" / "paper_engine_status.json",
        "placement": "master_controller_paper_sidecar",
        "mode": "paper_only",
        "fields": ("paper_trading_status", "risk_status", "current_balance"),
    },
    "phase24_broker_execution_safety": {
        "path": Path("data") / "execution_safety" / "latest_execution_safety_report.json",
        "placement": "master_controller_execution_safety_sidecar",
        "mode": "safety_only",
        "fields": ("status", "broker_execution_mode", "execution_allowed"),
    },
    "phase25_smart_execution": {
        "path": Path("data") / "execution_safety" / "latest_smart_execution_report.json",
        "placement": "master_controller_execution_quality_sidecar",
        "mode": "advisory_only",
        "fields": ("execution_mode", "execution_recommendation", "execution_quality_score"),
    },
    "phase36_memory_consolidation": {
        "path": Path("data") / "memory_consolidation" / "latest_memory_consolidation_report.json",
        "placement": "master_controller_memory_sidecar",
        "mode": "research_only",
        "fields": ("memory_data_mode", "memory_quality_score", "memory_warning"),
    },
    "phase37_auto_repair": {
        "path": Path("data") / "auto_repair" / "latest_auto_repair_report.json",
        "placement": "master_controller_diagnostic_sidecar",
        "mode": "diagnostic_only",
        "fields": ("repair_data_mode", "repair_status", "severity_score"),
    },
    "phase40_accuracy_validation": {
        "path": Path("data") / "runtime" / "accuracy_validation_status.json",
        "fallback_path": Path("data") / "memory" / "accuracy_validation_state.json",
        "placement": "master_controller_accuracy_validation_sidecar",
        "mode": "advisory_only",
        "fields": ("status", "run_count", "closed_records_this_run", "new_record_ids_this_run"),
    },
    "phase41_meta_learning": {
        "path": Path("data") / "runtime" / "meta_learning_status.json",
        "fallback_path": Path("data") / "memory" / "meta_learning_state.json",
        "placement": "master_controller_meta_learning_sidecar",
        "mode": "advisory_only",
        "fields": ("status", "run_count", "priority_count", "phase40_run_count_seen"),
    },
    "phase42_strategy_genome_architecture": {
        "path": Path("data") / "runtime" / "strategy_genome_status.json",
        "fallback_path": Path("data") / "memory" / "strategy_genome_memory.json",
        "placement": "master_controller_strategy_genome_sidecar",
        "mode": "advisory_only",
        "fields": ("status", "run_count", "continued_from_previous_state", "family_count", "active_regime"),
    },
    "phase43_meta_regime_intelligence": {
        "path": Path("data") / "runtime" / "meta_regime_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "meta_regime_intelligence_state.json",
        "placement": "master_controller_meta_regime_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "run_count",
            "continued_from_previous_state",
            "phase42_consumed",
            "phase42_run_count_seen",
            "transition_risk_score",
            "strategy_regime_mismatch_score",
            "global_meta_regime_risk_score",
        ),
    },
    "phase44_temporal_intelligence": {
        "path": Path("data") / "runtime" / "temporal_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "temporal_intelligence_state.json",
        "placement": "master_controller_phase44_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "current_session",
            "timing_quality_score",
            "replay_timing_behavior",
        ),
    },
    "phase45_market_breadth_intelligence": {
        "path": Path("data") / "runtime" / "market_breadth_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "market_breadth_intelligence_state.json",
        "placement": "master_controller_phase45_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase44_consumed",
            "phase44_run_count_seen",
            "market_participation_health_score",
            "breadth_divergence_score",
            "market_wide_confirmation_quality",
        ),
    },
    "phase46_crowd_psychology_engine": {
        "path": Path("data") / "runtime" / "crowd_psychology_status.json",
        "fallback_path": Path("data") / "memory" / "crowd_psychology_state.json",
        "placement": "master_controller_phase46_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase44_consumed",
            "phase45_consumed",
            "phase44_run_count_seen",
            "phase45_run_count_seen",
            "fear_euphoria",
            "panic_behavior_score",
            "crowd_instability_score",
            "trap_psychology_score",
            "overconfidence_score",
            "emotional_replay_patterns",
        ),
    },
    "phase47_market_narrative_intelligence": {
        "path": Path("data") / "runtime" / "market_narrative_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "market_narrative_intelligence_state.json",
        "placement": "master_controller_phase47_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase45_consumed",
            "phase46_consumed",
            "phase45_run_count_seen",
            "phase46_run_count_seen",
            "dominant_narrative",
            "narrative_persistence_score",
            "narrative_contradiction_score",
        ),
    },
    "phase48_synthetic_market_simulator": {
        "path": Path("data") / "runtime" / "synthetic_market_simulator_status.json",
        "fallback_path": Path("data") / "memory" / "synthetic_market_simulator_state.json",
        "placement": "master_controller_phase48_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "simulation_count",
            "volatility_shock_score",
            "liquidity_collapse_score",
            "fake_breakout_environment_score",
            "panic_simulation_score",
            "regime_stress_score",
            "rare_event_replay_score",
            "synthetic_market_stress_index",
        ),
    },
    "phase49_adversarial_intelligence": {
        "path": Path("data") / "runtime" / "adversarial_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "adversarial_intelligence_state.json",
        "placement": "master_controller_phase49_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase48_consumed",
            "phase48_run_count_seen",
            "stop_hunt_risk_score",
            "trap_structure_score",
            "liquidity_manipulation_score",
            "fake_momentum_score",
            "institutional_bait_score",
            "adversarial_replay_signature_score",
        ),
    },
    "phase50_explainable_ai_engine": {
        "path": Path("data") / "runtime" / "explainable_ai_engine_status.json",
        "fallback_path": Path("data") / "memory" / "explainable_ai_engine_state.json",
        "placement": "master_controller_phase50_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase48_consumed",
            "phase49_consumed",
            "phase48_run_count_seen",
            "phase49_run_count_seen",
            "engine_contribution_trace",
            "reasoning_summary",
            "contradiction_score",
            "explanation_depth_score",
        ),
    },
    "phase51_hierarchical_brain_architecture": {
        "path": Path("data") / "runtime" / "hierarchical_brain_architecture_status.json",
        "fallback_path": Path("data") / "memory" / "hierarchical_brain_architecture_state.json",
        "placement": "master_controller_phase51_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "reflex_layer_score",
            "tactical_layer_score",
            "strategic_layer_score",
            "macro_layer_score",
            "supervisor_layer_score",
            "arbitration_layer_score",
            "hierarchy_balance_score",
            "organized_existing_outputs",
        ),
    },
    "phase52_autonomous_goal_management": {
        "path": Path("data") / "runtime" / "autonomous_goal_management_status.json",
        "fallback_path": Path("data") / "memory" / "autonomous_goal_management_state.json",
        "placement": "master_controller_phase52_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase51_consumed",
            "phase51_run_count_seen",
            "dominant_goal",
            "goal_priority_scores",
            "advisory_objectives",
            "exploration_vs_exploitation",
        ),
    },
    "phase53_knowledge_distillation_engine": {
        "path": Path("data") / "runtime" / "knowledge_distillation_engine_status.json",
        "fallback_path": Path("data") / "memory" / "knowledge_distillation_engine_state.json",
        "placement": "master_controller_phase53_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase51_consumed",
            "phase52_consumed",
            "phase51_run_count_seen",
            "phase52_run_count_seen",
            "prior_intelligence_consumed",
            "high_value_principles",
            "failure_summaries",
            "distillation_scores",
        ),
    },
    "phase54_multi_horizon_intelligence": {
        "path": Path("data") / "runtime" / "multi_horizon_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "multi_horizon_intelligence_state.json",
        "placement": "master_controller_phase54_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "horizon_alignment_scores",
            "horizon_agreement_score",
            "timeframe_conflict_score",
            "timing_synchronization_score",
            "higher_timeframe_pressure_score",
            "lower_timeframe_instability_score",
            "source_consumption",
        ),
    },
    "phase55_capital_flow_intelligence": {
        "path": Path("data") / "runtime" / "capital_flow_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "capital_flow_intelligence_state.json",
        "placement": "master_controller_phase55_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase54_consumed",
            "phase54_run_count_seen",
            "sector_rotation_score",
            "capital_migration_score",
            "risk_on_score",
            "risk_off_score",
            "institutional_flow_proxy_score",
            "participation_exhaustion_score",
            "defensive_transition_score",
            "offensive_transition_score",
            "capital_flow_regime",
        ),
    },
    "phase56_dynamic_risk_intelligence": {
        "path": Path("data") / "runtime" / "dynamic_risk_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "dynamic_risk_intelligence_state.json",
        "placement": "master_controller_phase56_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase54_consumed",
            "phase55_consumed",
            "phase54_run_count_seen",
            "phase55_run_count_seen",
            "volatility_aware_exposure_score",
            "confidence_aware_risk_score",
            "drawdown_aware_caution_score",
            "regime_aware_risk_score",
            "instability_aware_exposure_reduction_score",
            "stress_aware_theoretical_sizing_score",
            "theoretical_shadow_size_multiplier",
            "risk_advisory",
            "source_consumption",
        ),
    },
    "phase57_recursive_self_reflection_engine": {
        "path": Path("data") / "runtime" / "recursive_self_reflection_status.json",
        "fallback_path": Path("data") / "memory" / "recursive_self_reflection_state.json",
        "placement": "master_controller_phase57_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "repeated_reasoning_mistake_score",
            "recurring_failure_chain_score",
            "missed_opportunity_pattern_score",
            "confidence_mismatch_score",
            "contradiction_persistence_score",
            "self_bias_detection_score",
            "reflection_evolution_score",
            "source_consumption",
        ),
    },
    "phase58_long_term_market_memory": {
        "path": Path("data") / "runtime" / "long_term_market_memory_status.json",
        "fallback_path": Path("data") / "memory" / "long_term_market_memory_state.json",
        "placement": "master_controller_phase58_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase57_consumed",
            "phase57_run_count_seen",
            "crisis_memory_score",
            "boom_bust_cycle_score",
            "volatility_regime_transition_score",
            "historical_analog_quality_score",
            "macro_event_memory_score",
            "structural_failure_memory_score",
            "rare_event_archive_score",
            "source_consumption",
        ),
    },
    "phase59_institutional_coordination_intelligence": {
        "path": Path("data") / "runtime" / "institutional_coordination_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "institutional_coordination_intelligence_state.json",
        "placement": "master_controller_phase59_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase57_consumed",
            "phase58_consumed",
            "phase57_run_count_seen",
            "phase58_run_count_seen",
            "desk_coordination_scores",
            "institutional_coordination_score",
            "desk_disagreement_score",
            "coordination_advisory",
            "source_consumption",
        ),
    },
    "phase60_agi_transition_layer": {
        "path": Path("data") / "runtime" / "agi_transition_layer_status.json",
        "fallback_path": Path("data") / "memory" / "agi_transition_layer_state.json",
        "placement": "master_controller_phase60_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "world_model_signal_score",
            "autonomy_readiness_shadow_score",
            "improvement_planning_shadow_score",
            "governance_alignment_score",
            "agi_transition_readiness_score",
            "autonomous_improvement_plan",
            "source_consumption",
        ),
    },
    "phase61_neuro_symbolic_reasoning_engine": {
        "path": Path("data") / "runtime" / "neuro_symbolic_reasoning_status.json",
        "fallback_path": Path("data") / "memory" / "neuro_symbolic_reasoning_state.json",
        "placement": "master_controller_phase61_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase60_consumed",
            "phase60_run_count_seen",
            "contradiction_check_score",
            "causal_consistency_score",
            "symbolic_abstraction_score",
            "logic_rule_coverage_score",
            "neuro_symbolic_conflict_score",
            "reasoning_integrity_score",
            "symbolic_rules",
            "source_consumption",
        ),
    },
    "phase62_meta_cognition_engine": {
        "path": Path("data") / "runtime" / "meta_cognition_engine_status.json",
        "fallback_path": Path("data") / "memory" / "meta_cognition_engine_state.json",
        "placement": "master_controller_phase62_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase60_consumed",
            "phase61_consumed",
            "phase60_run_count_seen",
            "phase61_run_count_seen",
            "reasoning_reliability_score",
            "self_doubt_score",
            "uncertainty_introspection_score",
            "cognitive_conflict_score",
            "confidence_of_reasoning_score",
            "supervision_need_score",
            "meta_cognition_advisory",
            "source_consumption",
        ),
    },
    "phase63_swarm_intelligence_architecture": {
        "path": Path("data") / "runtime" / "swarm_intelligence_architecture_status.json",
        "fallback_path": Path("data") / "memory" / "swarm_intelligence_architecture_state.json",
        "placement": "master_controller_phase63_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "agent_roles",
            "swarm_coordination_score",
            "agent_disagreement_score",
            "specialist_consensus_score",
            "swarm_memory_signal_count",
            "coordination_advisory",
            "source_consumption",
        ),
    },
    "phase64_federated_intelligence_system": {
        "path": Path("data") / "runtime" / "federated_intelligence_system_status.json",
        "fallback_path": Path("data") / "memory" / "federated_intelligence_system_state.json",
        "placement": "master_controller_phase64_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase63_consumed",
            "phase63_run_count_seen",
            "node_readiness_score",
            "memory_synchronization_health_score",
            "cross_module_knowledge_sharing_score",
            "distributed_learning_compatibility_score",
            "privacy_safety_constraint_score",
            "federated_readiness_score",
            "local_federation_nodes",
            "federation_advisory",
            "source_consumption",
        ),
    },
    "phase65_advanced_optimization_framework": {
        "path": Path("data") / "runtime" / "advanced_optimization_framework_status.json",
        "fallback_path": Path("data") / "memory" / "advanced_optimization_framework_state.json",
        "placement": "master_controller_phase65_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase63_consumed",
            "phase64_consumed",
            "phase63_run_count_seen",
            "phase64_run_count_seen",
            "research_priority_optimization_score",
            "memory_compression_priority_score",
            "strategy_sandbox_priority_score",
            "risk_hypothesis_priority_score",
            "resource_allocation_hint_score",
            "scenario_optimization_score",
            "constraint_aware_planning_score",
            "optimization_readiness_score",
            "optimization_plan",
            "source_consumption",
        ),
    },
    "phase66_autonomous_strategy_research_lab": {
        "path": Path("data") / "runtime" / "autonomous_strategy_research_lab_status.json",
        "fallback_path": Path("data") / "memory" / "autonomous_strategy_research_lab_state.json",
        "placement": "master_controller_phase66_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "experiment_quality_score",
            "research_loop_failure_score",
            "sandbox_prioritization_score",
            "strategy_hypothesis_confidence_score",
            "research_stagnation_score",
            "innovation_pressure_score",
            "research_lab_intelligence_score",
            "research_hypotheses",
            "source_consumption",
        ),
    },
    "phase67_synthetic_market_evolution_engine": {
        "path": Path("data") / "runtime" / "synthetic_market_evolution_engine_status.json",
        "fallback_path": Path("data") / "memory" / "synthetic_market_evolution_engine_state.json",
        "placement": "master_controller_phase67_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase66_consumed",
            "phase66_run_count_seen",
            "synthetic_regime_transition_score",
            "evolving_volatility_environment_score",
            "liquidity_collapse_simulation_score",
            "fake_stability_environment_score",
            "adversarial_synthetic_transition_score",
            "synthetic_stress_escalation_score",
            "cognition_robustness_under_synthetic_change_score",
            "synthetic_evolution_intelligence_score",
            "evolving_world_plan",
            "source_consumption",
        ),
    },
    "phase68_global_macro_intelligence_mesh": {
        "path": Path("data") / "runtime" / "global_macro_intelligence_mesh_status.json",
        "fallback_path": Path("data") / "memory" / "global_macro_intelligence_mesh_state.json",
        "placement": "master_controller_phase68_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase66_consumed",
            "phase67_consumed",
            "phase66_run_count_seen",
            "phase67_run_count_seen",
            "macro_synchronization_score",
            "macro_divergence_score",
            "global_liquidity_pressure_score",
            "risk_on_risk_off_wave_score",
            "institutional_macro_pressure_score",
            "defensive_macro_rotation_score",
            "offensive_macro_rotation_score",
            "global_macro_mesh_pressure_score",
            "macro_mesh_advisory",
            "source_consumption",
        ),
    },
    "phase69_portfolio_consciousness_engine": {
        "path": Path("data") / "runtime" / "portfolio_consciousness_engine_status.json",
        "fallback_path": Path("data") / "memory" / "portfolio_consciousness_engine_state.json",
        "placement": "master_controller_phase69_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "sector_concentration_pressure_score",
            "exposure_clustering_score",
            "cross_position_correlation_score",
            "macro_exposure_imbalance_score",
            "hidden_portfolio_fragility_score",
            "portfolio_stress_synchronization_score",
            "defensive_offensive_balance_score",
            "portfolio_consciousness_score",
            "position_relationship_map",
            "source_consumption",
        ),
    },
    "phase70_autonomous_capital_allocation_intelligence": {
        "path": Path("data") / "runtime" / "autonomous_capital_allocation_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "autonomous_capital_allocation_intelligence_state.json",
        "placement": "master_controller_phase70_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase69_consumed",
            "phase69_run_count_seen",
            "capital_efficiency_hypothesis_score",
            "adaptive_allocation_balance_score",
            "allocation_stress_pressure_score",
            "portfolio_concentration_advisory_score",
            "capital_rotation_hypothesis_score",
            "capital_preservation_regime_score",
            "research_resource_allocation_hint_score",
            "shadow_allocation_intelligence_score",
            "shadow_allocation_hypotheses",
            "source_consumption",
        ),
    },
    "phase71_master_agi_trading_orchestrator": {
        "path": Path("data") / "runtime" / "master_agi_trading_orchestrator_status.json",
        "fallback_path": Path("data") / "memory" / "master_agi_trading_orchestrator_state.json",
        "placement": "master_controller_phase71_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "connected",
            "run_count",
            "continued_from_previous_state",
            "phase69_consumed",
            "phase70_consumed",
            "phase69_run_count_seen",
            "phase70_run_count_seen",
            "orchestration_coherence_score",
            "subsystem_disagreement_score",
            "cognitive_bottleneck_score",
            "orchestration_stability_score",
            "autonomous_coordination_quality_score",
            "consciousness_convergence_readiness_score",
            "master_agi_orchestration_score",
            "orchestration_intelligence_map",
            "source_consumption",
        ),
    },
}
PHASE39_MEMORY_ARTIFACTS = {
    "adaptive_memory": {
        "path": Path("data") / "memory" / "historical_adaptive_intelligence_state.json",
        "report_path": Path("reports") / "historical_adaptive_intelligence_report.txt",
        "progress_key": "adaptive_memory",
    },
    "rl_shadow_refresh": {
        "path": Path("data") / "memory" / "reinforcement_learning_memory.json",
        "report_path": Path("reports") / "phase20_reinforcement_learning_report.txt",
        "runtime_path": Path("data") / "runtime" / "reinforcement_learning_status.json",
        "progress_key": "reinforcement_learning",
    },
    "volatility_memory": {
        "path": Path("data") / "memory" / "volatility_expansion_compression_memory.json",
        "report_path": Path("reports") / "volatility_memory_report.txt",
    },
    "trap_memory": {
        "path": Path("data") / "memory" / "trap_fakeout_memory.json",
        "report_path": Path("reports") / "trap_memory_report.txt",
    },
    "confidence_decay_memory": {
        "path": Path("data") / "memory" / "confidence_decay_memory.json",
        "report_path": Path("reports") / "confidence_decay_memory_report.txt",
    },
    "transition_instability_memory": {
        "path": Path("data") / "memory" / "transition_instability_memory.json",
        "report_path": Path("reports") / "transition_instability_memory_report.txt",
    },
    "multi_timeframe_conflict_memory": {
        "path": Path("data") / "memory" / "multi_timeframe_conflict_memory.json",
        "report_path": Path("reports") / "multi_timeframe_conflict_memory_report.txt",
    },
    "no_trade_refinement_memory": {
        "path": Path("data") / "memory" / "no_trade_refinement_memory.json",
        "report_path": Path("reports") / "no_trade_refinement_memory_report.txt",
    },
}
PHASE39_REPLAY_FIELD_GROUPS = {
    "replay_realism": (
        "replay_realism",
        "signal_age_minutes",
        "holding_period_days",
        "session_context_label",
        "entry_timing_label",
        "exit_timing_label",
        "holding_time_label",
        "decay_risk_label",
        "replay_realism_confidence",
    ),
    "semantic_replay_labels": (
        "semantic_labels",
        "trap_label",
        "fake_breakout_label",
        "liquidity_sweep_label",
        "regime_label",
        "volatility_state_label",
        "mtf_alignment_label",
        "gap_behavior_label",
        "panic_euphoria_label",
    ),
    "interpretation_engine": (
        "interpreted_outcome_label",
        "failure_reason_label",
        "success_reason_label",
        "behavioral_pattern_label",
        "emotional_market_proxy",
        "market_context_label",
        "conviction_quality_label",
        "experience_weight",
    ),
}


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_latest_jsonl_record_safe(path):
    meta = {
        "available": False,
        "reason": "missing",
        "line_number": None,
        "invalid_line_count": 0,
    }
    try:
        path = Path(path)
        if not path.exists():
            return {}, meta
        meta["reason"] = "empty"
        latest_record = {}
        latest_line_number = None
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                meta["reason"] = "no_valid_json_object"
                try:
                    payload = json.loads(line)
                except Exception:
                    meta["invalid_line_count"] += 1
                    continue
                if not isinstance(payload, dict):
                    meta["invalid_line_count"] += 1
                    continue
                latest_record = payload
                latest_line_number = line_number
    except Exception:
        meta["reason"] = "unreadable"
        return {}, meta
    if latest_record:
        meta["available"] = True
        meta["reason"] = "ok"
        meta["line_number"] = latest_line_number
    return latest_record, meta


def _read_csv_header_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            header = handle.readline().strip()
    except Exception:
        return []
    return [item.strip() for item in header.split(",") if item.strip()]


def _parse_datetime_safe(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_seconds_from_timestamp(value, now):
    parsed = _parse_datetime_safe(value)
    if parsed is None:
        return None
    current = as_ist_datetime(now)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=current.tzinfo)
    return max(0.0, (current - parsed.astimezone(current.tzinfo)).total_seconds())


def _path_available(path):
    if path is None:
        return False
    try:
        return Path(path).exists()
    except OSError:
        return False


def _phase39_artifact_summary(name, spec, progress):
    progress_key = spec.get("progress_key") or name
    progress_payload = progress.get(progress_key)
    artifact_path = spec.get("path")
    report_path = spec.get("report_path")
    runtime_path = spec.get("runtime_path")
    connected = (
        bool(progress_payload)
        or _path_available(artifact_path)
        or _path_available(report_path)
        or _path_available(runtime_path)
    )

    return {
        "connected": connected,
        "active": connected,
        "artifact_path": str(artifact_path).replace("\\", "/") if artifact_path else None,
        "report_path": str(report_path).replace("\\", "/") if report_path else None,
        "runtime_status_path": str(runtime_path).replace("\\", "/") if runtime_path else None,
        "progress_key": progress_key,
        "progress_present": bool(progress_payload),
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
    }


def _phase39_replay_field_status(jsonl_record):
    field_source = set(jsonl_record.keys())
    summaries = {}
    for group, fields in PHASE39_REPLAY_FIELD_GROUPS.items():
        present = sorted(field for field in fields if field in field_source)
        summaries[group] = {
            "active": bool(present),
            "fields_present": present,
            "fields_expected": list(fields),
            "advisory_only": True,
            "research_only": True,
            "shadow_mode": True,
        }
    return summaries


def _phase39_research_memory_observatory(now=None):
    """
    Phase 39 is visibility-only. It reads existing replay/research artifacts and
    never participates in live ranking, execution, alert filtering, or scanning.
    """
    status = _read_json_safe(HISTORICAL_REPLAY_STATUS_PATH)
    progress = _read_json_safe(HISTORICAL_REPLAY_PROGRESS_PATH)
    import_report = _read_json_safe(HISTORICAL_EXPERIENCE_REPORT_PATH)
    jsonl_record, jsonl_record_meta = _read_latest_jsonl_record_safe(HISTORICAL_EXPERIENCE_JSONL_PATH)
    replay_fields = _phase39_replay_field_status(jsonl_record)

    latest_replay_timestamp = (
        progress.get("last_completed_at_ist")
        or status.get("timestamp_ist")
        or import_report.get("generated_at")
    )
    latest_replay_record_count = progress.get("last_records_generated")
    if latest_replay_record_count is None:
        latest_replay_record_count = import_report.get("records_generated")
    stale_age_seconds = _age_seconds_from_timestamp(latest_replay_timestamp, now)
    stale_replay = stale_age_seconds is None or stale_age_seconds > PHASE39_STALE_REPLAY_SECONDS

    research_refresh = progress.get("research_memory_refresh") if isinstance(progress.get("research_memory_refresh"), dict) else {}
    maturity_engines = {}
    for name in (
        "volatility_memory",
        "trap_memory",
        "confidence_decay_memory",
        "transition_instability_memory",
        "multi_timeframe_conflict_memory",
        "no_trade_refinement_memory",
    ):
        summary = _phase39_artifact_summary(name, PHASE39_MEMORY_ARTIFACTS[name], progress)
        summary["progress_present"] = name in research_refresh
        summary["active"] = summary["connected"] or name in research_refresh
        maturity_engines[name] = summary

    adaptive_memory = _phase39_artifact_summary("adaptive_memory", PHASE39_MEMORY_ARTIFACTS["adaptive_memory"], progress)
    rl_shadow_refresh = _phase39_artifact_summary("rl_shadow_refresh", PHASE39_MEMORY_ARTIFACTS["rl_shadow_refresh"], progress)
    research_memory_refresh_active = bool(research_refresh)

    warnings = []
    if not jsonl_record_meta["available"]:
        warnings.append(f"phase39_latest_jsonl_record_{jsonl_record_meta['reason']}")
    if stale_replay:
        warnings.append("phase39_replay_artifacts_stale")
    for group, summary in replay_fields.items():
        if not summary["active"]:
            warnings.append(f"phase39_{group}_not_visible_in_latest_import")
    if not research_memory_refresh_active:
        warnings.append("phase39_research_memory_refresh_not_visible")
    if not adaptive_memory["active"]:
        warnings.append("phase39_adaptive_memory_refresh_not_visible")
    if not rl_shadow_refresh["active"]:
        warnings.append("phase39_rl_shadow_refresh_not_visible")

    safety = {
        "visibility_only": True,
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "live_rank_mutation_allowed": False,
        "scanner_changes": False,
        "broker_orders": False,
        "telegram_changes": False,
        "supabase_writes": False,
        "dashboard_changes": False,
        "execution_packet_changes": False,
        "alert_filter_changes": False,
        "live_order_behavior_changes": False,
        "autonomous_mutation": False,
    }

    return {
        "phase": "PHASE_39_RUNTIME_VISIBILITY_RESEARCH_MEMORY_OBSERVATORY",
        "name": "Runtime Visibility / Research Memory Observatory",
        "status": "WARNING" if warnings else "OK",
        "pyramid_placement": "runtime_status_visibility_only",
        "connected_to_runtime_status": True,
        "connected_to_master_controller": False,
        "affects_live_ranking_or_execution": False,
        "latest_replay_generation_timestamp": latest_replay_timestamp,
        "latest_replay_record_count": latest_replay_record_count,
        "replay_artifact_age_seconds": round(stale_age_seconds, 3) if stale_age_seconds is not None else None,
        "stale_replay_threshold_seconds": PHASE39_STALE_REPLAY_SECONDS,
        "stale_replay": stale_replay,
        "replay_status": progress.get("status") or status.get("status") or import_report.get("status") or "UNKNOWN",
        "latest_jsonl_record_status": jsonl_record_meta,
        "replay_realism_active": replay_fields["replay_realism"]["active"],
        "semantic_replay_labels_active": replay_fields["semantic_replay_labels"]["active"],
        "interpretation_engine_active": replay_fields["interpretation_engine"]["active"],
        "replay_field_visibility": replay_fields,
        "adaptive_memory_refreshed": adaptive_memory["active"],
        "adaptive_memory": adaptive_memory,
        "research_memory_refresh_active": research_memory_refresh_active,
        "research_memory_refresh_keys": sorted(research_refresh.keys()),
        "rl_shadow_refresh_active": rl_shadow_refresh["active"],
        "rl_shadow_refresh": rl_shadow_refresh,
        "experience_maturity_memory_engines_active": any(item["active"] for item in maturity_engines.values()),
        "experience_maturity_memory_engines": maturity_engines,
        "runtime_safety_summary": safety,
        "warnings": warnings,
    }


def _historical_replay_status_summary():
    status = _read_json_safe(HISTORICAL_REPLAY_STATUS_PATH)
    progress = _read_json_safe(HISTORICAL_REPLAY_PROGRESS_PATH)
    if not status and not progress:
        return {
            "status": "WAITING",
            "enabled_off_market": True,
            "cadence_seconds": 3600,
            "safety": {
                "telegram": False,
                "broker": False,
                "live_trade_mutation": False,
            },
        }

    return {
        "status": status.get("status") or progress.get("status") or "UNKNOWN",
        "last_run_at_ist": status.get("timestamp_ist"),
        "last_completed_at_ist": progress.get("last_completed_at_ist"),
        "last_skipped_at_ist": progress.get("last_skipped_at_ist"),
        "last_skip_reason": progress.get("last_skip_reason"),
        "last_records_generated": progress.get("last_records_generated"),
        "total_records_generated": progress.get("total_records_generated"),
        "batches_completed": progress.get("batches_completed"),
        "enabled_off_market": True,
        "cadence_seconds": 3600,
        "safety": {
            "telegram": False,
            "broker": False,
            "live_trade_mutation": False,
        },
    }


def _authoritative_runtime_health_summary():
    try:
        return run_authoritative_runtime_health_check()
    except Exception as exc:
        return {
            "overall_status": "FAIL",
            "error": str(exc),
            "safety_flags": {
                "advisory_only": True,
                "research_only": True,
                "affects_live_ranking": False,
                "affects_execution": False,
                "broker_mutation": False,
                "telegram_mutation": False,
                "supabase_mutation": False,
                "live_order_behavior": False,
                "recommended_live_weight": 0.0,
                "rank_adjustment": 0.0,
            },
        }


def _market_data_health_summary():
    try:
        return run_market_data_health_check()
    except Exception as exc:
        return {
            "overall_status": "FAIL",
            "error": str(exc),
            "safety_flags": {
                "advisory_only": True,
                "affects_live_ranking": False,
                "affects_execution": False,
                "broker_mutation": False,
                "telegram_mutation": False,
                "supabase_mutation": False,
                "live_order_behavior": False,
                "recommended_live_weight": 0.0,
                "rank_adjustment": 0.0,
            },
        }


def _runtime_topology_summary():
    try:
        topology = build_runtime_topology()
    except Exception as exc:
        return {
            "topology_health": "FAIL",
            "error": str(exc),
            "safety_flags": {
                "advisory_only": True,
                "affects_live_ranking": False,
                "affects_execution": False,
                "broker_mutation": False,
                "telegram_mutation": False,
                "supabase_mutation": False,
                "live_order_behavior": False,
                "recommended_live_weight": 0.0,
                "rank_adjustment": 0.0,
            },
        }
    graph = topology.get("dependency_graph") or {}
    visibility = topology.get("engine_visibility") or {}
    memory_health = topology.get("memory_health") or {}
    return {
        "topology_health": topology.get("topology_health"),
        "authoritative_runtime_owner": topology.get("authoritative_runtime_owner"),
        "authoritative_heartbeat": topology.get("authoritative_heartbeat"),
        "runtime_priority_order": topology.get("runtime_priority_order"),
        "runtime_integrity_score": topology.get("runtime_integrity_score"),
        "dependency_integrity_score": topology.get("dependency_integrity_score"),
        "observability_score": topology.get("observability_score"),
        "runtime_consistency_score": topology.get("runtime_consistency_score"),
        "runtime_conflicts": topology.get("runtime_conflicts") or [],
        "stale_runtime_sources": topology.get("stale_runtime_sources") or [],
        "dependency_graph_summary": graph,
        "runtime_visibility_summary": {
            "engines_not_reporting_status": visibility.get("engines_not_reporting_status") or [],
            "engines_disconnected_from_runtime_chain": visibility.get("engines_disconnected_from_runtime_chain") or [],
            "visibility_only_connected_engines": visibility.get("visibility_only_connected_engines") or [],
            "phases_contributing_nothing": visibility.get("phases_contributing_nothing") or [],
            "duplicated_runtime_visibility_paths": visibility.get("duplicated_runtime_visibility_paths") or [],
            "stale_memory_count": len(visibility.get("engines_with_stale_memory") or []),
        },
        "memory_health": memory_health,
        "legacy_engine_visibility": memory_health.get("legacy_engine_visibility") or {},
        "memory_freshness_score": memory_health.get("memory_freshness_score"),
        "memory_integrity_score": memory_health.get("memory_integrity_score"),
        "stale_memory_count": memory_health.get("stale_memory_files"),
        "orphan_memory_count": memory_health.get("orphan_memory_files"),
        "corrupted_memory_count": memory_health.get("corrupted_memory_files"),
        "archive_candidate_count": memory_health.get("archive_candidate_count"),
        "stale_legacy_memory_count": memory_health.get("stale_legacy_memory_count"),
        "memory_cleanup_summary": memory_health.get("memory_cleanup_summary") or {},
        "memory_lineage_summary": memory_health.get("memory_lineage_summary") or {},
        "memory_contribution_summary": memory_health.get("memory_contribution_summary") or {},
        "lineage_integrity_score": memory_health.get("lineage_integrity_score"),
        "missing_visibility_count": len(memory_health.get("missing_visibility_summary") or []),
        "safety_flags": topology.get("safety_flags") or {},
    }


def _phase_status_summaries():
    summaries = {}
    for phase, spec in PHASE_STATUS_ARTIFACTS.items():
        path = spec["path"]
        payload = _read_json_safe(path)
        artifact_path = path
        if not payload and spec.get("fallback_path"):
            artifact_path = spec["fallback_path"]
            payload = _read_json_safe(artifact_path)

        summary = {
            "connected": bool(payload),
            "artifact_path": str(artifact_path).replace("\\", "/"),
            "pyramid_placement": payload.get("pyramid_placement") or spec["placement"],
            "mode": spec["mode"],
            "advisory_only": payload.get("advisory_only", True),
            "research_only": payload.get("research_only", spec["mode"] == "research_only"),
            "paper_only": payload.get("paper_only", spec["mode"] == "paper_only"),
            "shadow_mode": payload.get("shadow_mode", True),
            "safety": {
                "live_order_allowed": bool(payload.get("live_order_allowed", False)),
                "live_rank_mutation_allowed": bool(payload.get("live_rank_mutation_allowed", False)),
                "affects_live_ranking": bool(payload.get("affects_live_ranking", False)),
                "affects_execution": bool(payload.get("affects_execution", False)),
                "broker_orders": bool(payload.get("broker_orders", False)),
                "broker_mutation": bool(payload.get("broker_mutation", False)),
                "telegram_changes": bool(payload.get("telegram_changes", False)),
                "telegram_mutation": bool(payload.get("telegram_mutation", False)),
                "supabase_mutation": bool(payload.get("supabase_mutation", False)),
                "supabase_writes": bool(payload.get("supabase_writes", False)),
                "auto_file_changes_allowed": bool(payload.get("auto_file_changes_allowed", False)),
            },
            "values": {},
        }
        for field in spec["fields"]:
            if field in payload:
                summary["values"][field] = payload.get(field)
        summaries[phase] = summary
    return summaries


def build_runtime_status(value=None):
    now = as_ist_datetime(value)
    permissions = get_mode_permissions(now)
    phase38_guard = evaluate_phase38_runtime_guard(
        {
            "runtime_mode": permissions["mode"],
            "current_mode": permissions["mode"],
            "live_execution_enabled": False,
            "telegram_enabled": "telegram_alerts" in permissions["live_allowed_engines"],
            "broker_enabled": False,
        }
    )

    authoritative_runtime_health = _authoritative_runtime_health_summary()
    market_data_health = _market_data_health_summary()
    runtime_topology = _runtime_topology_summary()
    return {
        "timestamp_ist": now.astimezone(IST).isoformat(),
        "mode": permissions["mode"],
        "live_allowed_engines": permissions["live_allowed_engines"],
        "research_allowed_engines": permissions["research_allowed_engines"],
        "blocked_engines": permissions["blocked_engines"],
        "reason": permissions["reason"],
        "phase38_runtime_guard": phase38_guard,
        "authoritative_runtime_health": authoritative_runtime_health,
        "market_data_health": market_data_health,
        "runtime_topology": runtime_topology,
        "dependency_graph_summary": runtime_topology.get("dependency_graph_summary"),
        "runtime_visibility_summary": runtime_topology.get("runtime_visibility_summary"),
        "memory_health": runtime_topology.get("memory_health"),
        "legacy_engine_visibility": runtime_topology.get("legacy_engine_visibility"),
        "memory_freshness_score": runtime_topology.get("memory_freshness_score"),
        "memory_integrity_score": runtime_topology.get("memory_integrity_score"),
        "stale_memory_count": runtime_topology.get("stale_memory_count"),
        "orphan_memory_count": runtime_topology.get("orphan_memory_count"),
        "corrupted_memory_count": runtime_topology.get("corrupted_memory_count"),
        "archive_candidate_count": runtime_topology.get("archive_candidate_count"),
        "stale_legacy_memory_count": runtime_topology.get("stale_legacy_memory_count"),
        "memory_cleanup_summary": runtime_topology.get("memory_cleanup_summary"),
        "memory_lineage_summary": runtime_topology.get("memory_lineage_summary"),
        "memory_contribution_summary": runtime_topology.get("memory_contribution_summary"),
        "lineage_integrity_score": runtime_topology.get("lineage_integrity_score"),
        "missing_visibility_count": runtime_topology.get("missing_visibility_count"),
        "runtime_integrity_score": runtime_topology.get("runtime_integrity_score"),
        "topology_health": runtime_topology.get("topology_health"),
        "historical_replay": _historical_replay_status_summary(),
        "phase39_research_memory_observatory": _phase39_research_memory_observatory(now),
        "phase_sidecar_status": _phase_status_summaries(),
    }


def write_runtime_status(path=STATUS_PATH, value=None):
    status = build_runtime_status(value)
    status["runtime_mode"] = runtime_mode_snapshot()
    phase38_context = {
        **status.get("runtime_mode", {}),
        "runtime_mode": status.get("mode"),
        "telegram_enabled": "telegram_alerts" in status.get("live_allowed_engines", []),
        "broker_enabled": False,
    }
    status["phase38_runtime_guard"] = evaluate_phase38_runtime_guard(phase38_context)
    write_phase38_runtime_status(phase38_context)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    write_runtime_status()
