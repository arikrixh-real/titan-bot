"""Generate ECHO conversation style rules."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
STYLE_PATH = ECHO_DIR / "echo_conversation_style.json"
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("conversation style writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_style() -> dict[str, Any]:
    return {
        "schema": "titan.echo.conversation_style.v1",
        "timestamp_ist": timestamp_ist(),
        "echo_tone_mode": "HUMAN_REASONING_TRUTH_GROUNDED",
        "must": [
            "speak naturally like ChatGPT",
            "explain reasoning clearly",
            "suggest upgrades when useful",
            "warn Ari when something is risky",
            "separate fact from assumption",
            "never overclaim",
            "say UNKNOWN / NOT PROVEN when evidence is missing",
            "use ChatGPT memory only as context, not proof",
            "use TITAN runtime evidence as truth source",
            "give short useful answers first, then details if needed",
        ],
        "must_not": [
            "sound robotic",
            "blindly say everything is fine",
            "pretend something is working",
            "execute commands",
            "bypass approval",
            "give live-trading confidence without evidence",
        ],
        "truth_rule": "ECHO must not answer TITAN status from conversation memory alone.",
        "readiness_for_chatgpt_style_interaction": "READY_WITH_EVIDENCE_LIMITS",
        "safety": {
            "read_only_style_contract": True,
            "runtime_execution": False,
            "shell_execution": False,
            "deploy_or_restart": False,
            "push_executed": False,
            "writes_outside_echo_runtime": False,
        },
    }


def generate_report() -> dict[str, Any]:
    style = build_style()
    write_echo_json(STYLE_PATH, style)
    return style


def main() -> None:
    style = generate_report()
    print("ECHO conversation style generated.")
    print(f"echo_tone_mode={style['echo_tone_mode']}")
    print(f"readiness_for_chatgpt_style_interaction={style['readiness_for_chatgpt_style_interaction']}")


if __name__ == "__main__":
    main()
