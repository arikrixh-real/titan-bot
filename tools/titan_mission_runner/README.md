# TITAN Local Mission Bridge

`local_bridge.ps1` is a local-only one-shot bridge for starting the existing TITAN mission runner from a JSON request file.

It does not start an internet server, open a public port, register a webhook, deploy, or push. It validates the request, requires the exact mission start approval token, logs bridge actions under `tools/titan_mission_runner/logs/`, and delegates to the existing `start_mission.ps1` / `run_mission.ps1` safety flow.

## Safe-read auto-approval

Mission runner Codex launches use an explicit prompt whitelist for safe read-only inspection commands. Codex may run only the listed safe reads without stopping for human approval: `git status`, `git diff --stat`, `git branch --show-current`, `Test-Path tools/titan_mission_runner/mission.lock`, and `Get-Content` of mission prompt or log files under `tools/titan_mission_runner/`.

Everything outside that whitelist still requires explicit mission-specific human approval, including edits, tests, commits, pushes, deletes, installs, dependency changes, runtime execution, deployment, `.env`, Supabase, broker, Telegram, and live trading changes. Push approval remains separate through `push_after_approval.ps1`; the bridge and runner do not auto-push.

## Request file

Place one request at:

```text
tools/titan_mission_runner/inbox/mission_request.json
```

Use this format:

```json
{
  "phase": "Experience Mega-Batch B",
  "mission": "Replay Realism: add advisory-only signal aging, holding-time, session context, and replay timing realism without live mutation",
  "approval_token": "I_APPROVE_TITAN_MISSION_START"
}
```

The approval token must be exactly:

```text
I_APPROVE_TITAN_MISSION_START
```

If the token is missing or wrong, the request is rejected and moved to `failed/`.

## Run

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/titan_mission_runner/local_bridge.ps1
```

The bridge reads `inbox/mission_request.json` by default. To use a different local request path:

```powershell
powershell -ExecutionPolicy Bypass -File tools/titan_mission_runner/local_bridge.ps1 -RequestPath tools/titan_mission_runner/inbox/mission_request.json
```

## Outcomes

Successful requests move to:

```text
tools/titan_mission_runner/archive/
```

Failed or rejected requests move to:

```text
tools/titan_mission_runner/failed/
```

Bridge logs are written as `local-bridge-*.log`; captured mission runner output is written as `local-bridge-runner-*.log`.

The mission lock remains owned by `run_mission.ps1`. The bridge does not create, bypass, or remove `mission.lock`.
