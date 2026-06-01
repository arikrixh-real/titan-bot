#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

OPENAPI="docs/chatgpt_bridge/custom_gpt_openapi.yaml"
INSTALL_SCRIPT="tools/echo_relay/install_local_relay_service.sh"
UNINSTALL_SCRIPT="tools/echo_relay/uninstall_local_relay_service.sh"
ENV_EXAMPLE="tools/echo_relay/relay_env.example"

python3 -m py_compile \
  titan_echo/echo_relay_api.py \
  titan_echo/echo_relay_auth.py \
  titan_echo/echo_relay_config.py \
  titan_echo/echo_relay_check.py

python3 -m titan_echo.echo_relay_check

grep -q -- "--host 127.0.0.1" "${INSTALL_SCRIPT}"
grep -q -- "--port 8766" "${INSTALL_SCRIPT}"
grep -q "EnvironmentFile=" "${INSTALL_SCRIPT}"
grep -q "ECHO_RELAY_ENABLED=true" "${ENV_EXAMPLE}"
grep -q "X-ECHO-RELAY-KEY" "${OPENAPI}"

PUBLIC_BIND_PATTERN="0[.]0[.]0[.]0|--host [][:][:]|--host [*]"
if grep -R -n -E "${PUBLIC_BIND_PATTERN}" tools/echo_relay docs/chatgpt_bridge; then
  echo "FAIL: public bind pattern found"
  exit 1
fi

if grep -n -E "ECHO_RELAY_ENABLED=true" "${INSTALL_SCRIPT}"; then
  echo "FAIL: relay enablement must come from env file, not service script"
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import re

openapi = Path("docs/chatgpt_bridge/custom_gpt_openapi.yaml").read_text(encoding="utf-8")
paths = set(re.findall(r"^  (/relay/[^:]+):$", openapi, flags=re.MULTILINE))
expected = {
    "/relay/health",
    "/relay/jarvis/ask",
    "/relay/titan/status",
    "/relay/chatgpt/integration/status",
    "/relay/chatgpt/evidence/contract",
    "/relay/chatgpt/evidence/catalog",
}
forbidden_path_terms = ("mission", "approval", "execution", "codex", "deploy", "rollback")
bad_paths = sorted(path for path in paths if any(term in path.lower() for term in forbidden_path_terms))
if paths != expected:
    print("FAIL: OpenAPI path set mismatch")
    print("expected=" + ",".join(sorted(expected)))
    print("actual=" + ",".join(sorted(paths)))
    raise SystemExit(1)
if bad_paths:
    print("FAIL: forbidden OpenAPI path found: " + ",".join(bad_paths))
    raise SystemExit(1)
print("OpenAPI safe path check PASS")
PY

echo "PASS: relay package static checks passed"
