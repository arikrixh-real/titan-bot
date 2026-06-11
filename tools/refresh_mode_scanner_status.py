"""Compatibility entrypoint for mode scanner status publication.

The canonical writer is ``runtime_continuous_core.run_continuous_runtime_core``.
This module exists for older scheduler/CLI references and must not maintain
independent scanner snapshot writing logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def refresh_mode_scanner_status() -> dict[str, Any]:
    from runtime_continuous_core import run_continuous_runtime_core

    result = run_continuous_runtime_core(refresh_market=True, refresh_universe=False)
    if not isinstance(result, dict):
        return {"status": "UPDATED", "source_owner": "runtime_continuous_core"}
    result["compatibility_entrypoint"] = "tools.refresh_mode_scanner_status"
    result["source_owner"] = "runtime_continuous_core"
    return result


def main() -> None:
    print(json.dumps(refresh_mode_scanner_status(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
