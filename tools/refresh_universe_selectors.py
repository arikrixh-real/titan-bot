"""Refresh TITAN common/HFT/Classic universe selector artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.universe_selectors import refresh_all_universes


def refresh_once() -> dict:
    return refresh_all_universes()


def main() -> int:
    payload = refresh_once()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
