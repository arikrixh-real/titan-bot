# ECHO ChatGPT-Codex bridge plan

Plan only. This document does not add endpoints, start services, run Codex,
push GitHub, pull on VPS, deploy, restart, or rollback.

## Read Endpoints

| Method | Path | Purpose | Gate |
|---|---|---|---|
| GET | `/health` | Public health only; no secrets, no runtime actions. | READ_ONLY |
| GET | `/status` | Protected read-only ECHO/TITAN status from evidence files. | READ_ONLY |
| GET | `/answer` | Protected read-only current ECHO answer. | READ_ONLY |
| GET | `/query` | Protected read-only intent query from ECHO evidence. | READ_ONLY |
| GET | `/approval/pending` | Protected read-only pending approval records. | READ_ONLY |
| GET | `/mission/current` | Protected read-only current mission plan/status. | READ_ONLY |
| GET | `/verification/latest` | Protected read-only latest verification result. | READ_ONLY |

## Approval-Gated Endpoints

| Method | Path | Purpose | Gate |
|---|---|---|---|
| POST | `/mission/prepare` | Create a mission plan record only; no execution. | APPROVAL_GATED |
| POST | `/approval/approve` | Create signed Ari approval record for a prepared action. | APPROVAL_GATED |
| POST | `/approval/reject` | Create rejection record for a prepared action. | APPROVAL_GATED |
| POST | `/codex/run-approved` | Run only an approved Codex mission; never raw ChatGPT execution. | APPROVAL_GATED |
| POST | `/git/push-approved` | Push only selected staged files after explicit approval. | APPROVAL_GATED |
| POST | `/vps/pull-approved` | VPS pull only after approved push workflow. | APPROVAL_GATED |
| POST | `/verify/run-approved` | Run approved verification after pull/deploy step. | APPROVAL_GATED |
| POST | `/deploy/approved` | Deploy/start/restart only under separate explicit approval. | APPROVAL_GATED |
| POST | `/rollback/approved` | Rollback only under separate explicit approval. | APPROVAL_GATED |

## Approval Workflow

1. **read_context**: Read evidence only.
2. **prepare_mission**: Writes mission plan and approval request only; no Codex/git/VPS/deploy action.
3. **ari_decision**: Creates signed approval/rejection record in data/runtime/echo.
4. **run_codex_if_approved**: Runs only the exact approved mission. No raw shell prompt.
5. **push_if_approved**: Pushes only selected staged files named in the approval record.
6. **vps_pull_if_approved**: Pulls only after push approval and records result.
7. **verify_if_approved**: Runs approved verification commands and records output summary.
8. **deploy_or_rollback_separate_gate**: Requires separate explicit approval; never implied by code/test approval.

## Safety Model

- Mission prepare writes a mission plan only.
- Approval creates a signed approval record.
- Codex only runs an approved mission.
- Git push only uses selected staged files after approval.
- VPS pull only follows push approval.
- Verification runs after pull and records results.
- Deploy/restart requires separate approval.
- Rollback requires separate approval.
- All action records are logged under `data/runtime/echo/`.

## Forbidden Actions

- No public unauthenticated API.
- No raw shell endpoint.
- ChatGPT cannot directly run Codex.
- ChatGPT cannot directly run git push.
- ChatGPT cannot directly run git pull.
- ChatGPT cannot directly deploy, restart, rollback, or verify.
- No broker/risk/execution endpoint.
- No live trade or broker control.
- No secrets committed.
- No approval bypass.

## Next Implementation Mission

Implement read-only bridge endpoints first: GET /approval/pending, GET /mission/current, and GET /verification/latest, with auth and no action execution.
