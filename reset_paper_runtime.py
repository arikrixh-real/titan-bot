import json
from pathlib import Path


PAPER_TRADE_REGISTRY_PATH = Path("data") / "runtime" / "paper_trade_registry.json"
PAPER_ENGINE_STATUS_PATH = Path("data") / "runtime" / "paper_engine_status.json"


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def reset_paper_runtime():
    registry = {
        "open_positions": [],
        "closed_positions": [],
        "seen_keys": [],
    }
    status = {
        "status": "PAPER_RUNTIME_RESET",
        "open_positions_count": 0,
        "closed_positions_count": 0,
        "new_paper_positions": 0,
        "paper_trade_creation": False,
        "trade_creation": False,
        "reason": "Local paper runtime reset only",
    }

    _write_json(PAPER_TRADE_REGISTRY_PATH, registry)
    _write_json(PAPER_ENGINE_STATUS_PATH, status)
    return {
        "reset_files": [
            str(PAPER_TRADE_REGISTRY_PATH),
            str(PAPER_ENGINE_STATUS_PATH),
        ],
        "status": status["status"],
    }


if __name__ == "__main__":
    print(json.dumps(reset_paper_runtime(), indent=2, sort_keys=True))
