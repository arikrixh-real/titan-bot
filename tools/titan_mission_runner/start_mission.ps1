[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForPromptWrite,

    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForSetup,

    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForTests,

    [Parameter(Mandatory = $false)]
    [string]$ApprovalToken,

    [Parameter(Mandatory = $false)]
    [string]$RunMissionApprovalToken,

    [Parameter(Mandatory = $false)]
    [string]$Phase,

    [Parameter(Mandatory = $false)]
    [string]$MissionDescription,

    [Parameter(Mandatory = $false)]
    [switch]$InteractiveStart
)

$ErrorActionPreference = "Stop"

$RequiredPromptWriteToken = "I_APPROVE_TITAN_MISSION_PROMPT_WRITE"
$RequiredStartToken = "I_APPROVE_TITAN_MISSION_START"
$RunMissionToken = "I_APPROVE_TITAN_TEST_MODE_MISSION"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PromptPath = Join-Path $PSScriptRoot "mission_prompt.txt"
$RunMissionPath = Join-Path $PSScriptRoot "run_mission.ps1"
$PushAfterApprovalPath = Join-Path $PSScriptRoot "push_after_approval.ps1"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Assert-PromptWriteApproval {
    if ($InteractiveStart) {
        if ($ApprovalToken -ne $RequiredStartToken) {
            throw "Approval required before starting the TITAN mission. Re-run and enter exact token '$RequiredStartToken'."
        }
        return
    }

    if (-not $ApprovedForPromptWrite -or $ApprovalToken -ne $RequiredPromptWriteToken) {
        throw "Approval required before writing mission_prompt.txt. Re-run with -ApprovedForPromptWrite and -ApprovalToken '$RequiredPromptWriteToken'."
    }
}

function New-MissionSlug {
    param([Parameter(Mandatory = $true)][string]$Value)

    $slug = ($Value.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim("-")
    if ([string]::IsNullOrWhiteSpace($slug)) {
        return "mission"
    }

    return $slug
}

function Get-CurrentCommit {
    $commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read current git commit."
    }

    return $commit
}

function Show-PostMissionCommit {
    param([Parameter(Mandatory = $true)][string]$BaseCommit)

    $headCommit = Get-CurrentCommit
    Write-Section "Mission Completion"
    if ($headCommit -ne $BaseCommit) {
        Write-Host "Commit created: $headCommit"
    }
    else {
        Write-Host "Commit created: none"
    }

    Write-Host "Review the final diff, then run this only after approval:"
    Write-Host $PushAfterApprovalPath
}

function Read-MultilinePrompt {
    Write-Host "Enter mission description/prompt. Type END on a new line when finished."
    $lines = New-Object System.Collections.Generic.List[string]
    while ($true) {
        $line = Read-Host
        if ($line -eq "END") {
            break
        }
        $lines.Add($line)
    }

    return ($lines -join [Environment]::NewLine).Trim()
}

function New-GeneratedMissionPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $createdAt = (Get-Date).ToUniversalTime().ToString("o")
    return @"
TITAN Mission Automation System

Generated Mission
- Created at UTC: $createdAt
- Mission title: $Title

Mission Prompt
$Description

Non-Negotiable Safety Rules
- NEVER touch live trading execution.
- NEVER modify .env or any .env.* file.
- NEVER change Supabase schema or migration files.
- NEVER auto-approve anything.
- Use workspace-write sandbox only.
- Require explicit human approval before edits or commands.
- Do not deploy automatically.
- Show all diffs before execution.
- Test mode only.
- Only one mission can run at a time.
- Use tools/titan_mission_runner/mission.lock as the runtime mission lock.
- If an active mission lock exists, abort safely.
- If a stale mission lock remains after a crashed process, remove it only when the recorded PID is dead.
- Remove the runtime mission lock after completion or failure.

Blocked Paths and Surfaces
- .env
- .env.*
- supabase/
- **/supabase/**
- **/migrations/**
- **/schema.sql
- **/*schema*.sql
- Any file or command related to live order placement, broker execution, production trading, production deployment, production secrets, or Telegram live alert sending behavior.

Mission Workflow
1. Read the mission request and classify risk.
2. Refuse any mission that touches blocked paths or live trading execution.
3. Acquire the runtime mission lock.
4. Show current git status before work.
5. Create a rollback-safe git branch only after explicit approval.
6. Run only read-only inspection commands until the human approves edits.
7. Make scoped edits only after explicit approval.
8. Show the complete diff after edits.
9. Run tests only after explicit approval.
10. Remove the runtime mission lock after completion or failure.
11. Do not commit, push, merge, deploy, or approve anything automatically.
12. Use push_after_approval.ps1 only after the human reviews the diff and explicitly approves push.

Approval Rules
- Approval must be explicit and mission-specific.
- Silence is not approval.
- Prior approval for one step does not approve later steps.
- Pushing requires a separate approval after diff review.
- Any command that modifies files, git history, remote state, dependencies, environment, infrastructure, database schema, or deployment state requires approval first.

Rollback-Safe Git Rules
- Start from a clean understanding of git status.
- Create a mission branch named mission/<timestamp>-<slug>.
- Before edits, record the base commit.
- Keep changes scoped to the mission.
- Show diff before tests, commit, or push.
- Never force-push.
- Never reset, checkout, clean, or remove user changes unless explicitly requested.
"@
}

Push-Location $RepoRoot
try {
    Write-Section "Start TITAN Mission"
    Write-Host "Mode: TEST ONLY"
    Write-Host "Repo: $RepoRoot"

    if (-not (Test-Path -LiteralPath $RunMissionPath)) {
        throw "Missing run_mission.ps1: $RunMissionPath"
    }

    $missionTitle = $Phase
    if ([string]::IsNullOrWhiteSpace($missionTitle)) {
        $missionTitle = Read-Host "Phase number/name"
    }
    $missionTitle = $missionTitle.Trim()
    if ([string]::IsNullOrWhiteSpace($missionTitle)) {
        throw "Phase number/name is required."
    }

    $missionDescription = $MissionDescription
    if ([string]::IsNullOrWhiteSpace($missionDescription)) {
        $missionDescription = Read-MultilinePrompt
    }
    $missionDescription = $missionDescription.Trim()
    if ([string]::IsNullOrWhiteSpace($missionDescription)) {
        throw "Mission description/prompt is required."
    }

    $branchSlug = New-MissionSlug -Value $missionTitle
    $generatedBranchPattern = "mission/<timestamp>-$branchSlug"

    Write-Section "Mission Summary"
    Write-Host "Phase: $missionTitle"
    Write-Host "Branch: $generatedBranchPattern"
    Write-Host "Prompt path: $PromptPath"
    Write-Host ""
    Write-Host $missionDescription

    Write-Section "Approval Required"
    if ($InteractiveStart -and [string]::IsNullOrWhiteSpace($ApprovalToken)) {
        $ApprovalToken = Read-Host "Type $RequiredStartToken to start"
    }
    Assert-PromptWriteApproval

    $generatedPrompt = New-GeneratedMissionPrompt -Title $missionTitle -Description $missionDescription
    Set-Content -LiteralPath $PromptPath -Value $generatedPrompt -Encoding UTF8

    Write-Section "Mission Prompt Written"
    Write-Host $PromptPath

    $baseCommit = Get-CurrentCommit

    $effectiveRunMissionApprovalToken = $RunMissionApprovalToken
    if ($InteractiveStart) {
        $effectiveRunMissionApprovalToken = $RunMissionToken
    }

    $runArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $RunMissionPath,
        "-MissionName", $missionTitle
    )

    if (-not [string]::IsNullOrWhiteSpace($effectiveRunMissionApprovalToken)) {
        $runArgs += "-ApprovalToken"
        $runArgs += $effectiveRunMissionApprovalToken
    }

    if ($InteractiveStart) {
        $runArgs += "-ApprovedForSetup"
    }

    if ($ApprovedForSetup) {
        $runArgs += "-ApprovedForSetup"
    }
    if ($ApprovedForTests) {
        $runArgs += "-ApprovedForTests"
    }

    Write-Section "Launching Mission Runner"
    & powershell @runArgs
    if ($LASTEXITCODE -ne 0) {
        throw "run_mission.ps1 failed with exit code $LASTEXITCODE."
    }

    Show-PostMissionCommit -BaseCommit $baseCommit
}
finally {
    Pop-Location
}
