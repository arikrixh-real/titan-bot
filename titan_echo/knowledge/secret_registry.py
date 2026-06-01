"""Build metadata-only sensitive location registry for ECHO."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import iter_files, now_utc, output_path, secret_metadata, write_json


OUTPUT_PATH = output_path("secret_registry.json")


def build_secret_registry() -> dict[str, Any]:
    locations = []
    for path in iter_files():
        meta = secret_metadata(path)
        if meta is not None:
            locations.append(meta)
    return {
        "schema": "titan_echo.knowledge.secret_registry.v1",
        "generated_at_utc": now_utc(),
        "mode": "metadata_only_no_secret_values",
        "summary": {"sensitive_locations": len(locations)},
        "safety": {
            "actual_secret_values_stored": False,
            "redaction_required_for_display": True,
            "public_exposure_allowed": False,
        },
        "locations": locations,
    }


def write_secret_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = payload or build_secret_registry()
    write_json(OUTPUT_PATH, registry)
    return registry


def main() -> int:
    registry = write_secret_registry()
    print("ECHO secret registry: PASSED")
    print(f"Sensitive locations: {registry['summary']['sensitive_locations']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
