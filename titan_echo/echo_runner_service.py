"""Thin service entry point for the local ECHO runner."""

from __future__ import annotations

import argparse
import json

from titan_echo.echo_local_runner import run_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ECHO local runner service mode")
    parser.add_argument("--client-host", default="127.0.0.1")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--service-mode", action="store_true", default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_service(
        dry_run=True if args.dry_run or not args.execute else False,
        client_host=args.client_host,
        service_mode=bool(args.service_mode),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
