"""
TITAN Phase 5 - Self-Evaluation Report Adapter
----------------------------------------------

Thin compatibility wrapper around strategy-family memory/report generation.
"""

from __future__ import annotations

from typing import Any, Dict

from engines.strategy_family_memory import (
    build_strategy_family_memory,
    get_self_evaluation_report_path,
    get_strategy_family_memory_path,
)


def build_self_evaluation_report(write_files: bool = True) -> Dict[str, Any]:
    """
    Builds Phase 5 memory and report outside the live ranking hot path.
    """

    return build_strategy_family_memory(write_files=write_files)


__all__ = [
    "build_self_evaluation_report",
    "get_self_evaluation_report_path",
    "get_strategy_family_memory_path",
]
