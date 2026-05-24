[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MissionName,

    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForSetup,

    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForTests,

    [Parameter(Mandatory = $false)]
    [string]$ApprovalToken
)

$ErrorActionPreference = "Stop"

$RequiredApprovalToken = "I_APPROVE_TITAN_TEST_MODE_MISSION"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PromptPath = Join-Path $PSScriptRoot "mission_prompt.txt"
$LockPath = Join-Path $PSScriptRoot "mission.lock"
$LockAcquired = $false
$MissionCompleted = $false

$BlockedPathPatterns = @(
    "\.env$",
    "\.env\.",
    "(^|[\\/])supabase([\\/]|$)",
    "(^|[\\/])migrations([\\/]|$)",
    "schema\.sql$",
    "schema.*\.sql$"
)

$BlockedContentPatterns = @(
    "live trading",
    "place order",
    "submit order",
    "broker execution",
    "production deploy",
    "supabase migration",
    "supabase db push"
)

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Assert-Approval {
    param(
        [Parameter(Mandatory = $true)][string]$Action,
        [Parameter(Mandatory = $true)][bool]$Approved
    )

    if (-not $Approved -or $ApprovalToken -ne $RequiredApprovalToken) {
        throw "Approval required before $Action. Re-run with the relevant approval switch and -ApprovalToken '$RequiredApprovalToken'."
    }
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Test-BlockedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $normalized = $Path -replace "\\", "/"
    foreach ($pattern in $BlockedPathPatterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }

    return $false
}

function Assert-NoBlockedDiff {
    $changedFiles = & git diff --name-only
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect git diff."
    }

    foreach ($file in $changedFiles) {
        if (Test-BlockedPath -Path $file) {
            throw "Blocked diff path detected: $file"
        }
    }

    $diffText = & git diff --no-ext-diff
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect git diff content."
    }

    foreach ($pattern in $BlockedContentPatterns) {
        if ($diffText -match [regex]::Escape($pattern)) {
            throw "Blocked diff content detected: $pattern"
        }
    }
}

function Test-ProcessAlive {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $null = Get-Process -Id $ProcessId -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Read-MissionLock {
    if (-not (Test-Path -LiteralPath $LockPath)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Mission lock exists but cannot be parsed: $LockPath. Inspect it manually before running another mission."
    }
}

function Remove-StaleMissionLock {
    param([Parameter(Mandatory = $true)]$Lock)

    if ($null -eq $Lock.pid) {
        throw "Mission lock has no PID and cannot be classified as stale: $LockPath"
    }

    $lockPid = [int]$Lock.pid
    if (Test-ProcessAlive -ProcessId $lockPid) {
        throw "Another TITAN mission is already running with PID $lockPid. Aborting safely."
    }

    Write-Section "Stale Mission Lock"
    Write-Host "Removing stale lock from crashed process PID $lockPid."
    Remove-Item -LiteralPath $LockPath -Force
}

function New-MissionLock {
    $existingLock = Read-MissionLock
    if ($null -ne $existingLock) {
        Remove-StaleMissionLock -Lock $existingLock
    }

    $lock = [ordered]@{
        pid = $PID
        mission = $MissionName
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        repo = $RepoRoot
        mode = "test-only"
    }

    $json = $lock | ConvertTo-Json

    try {
        $stream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
            $writer = New-Object System.IO.StreamWriter($stream)
            try {
                $writer.Write($json)
            }
            finally {
                $writer.Dispose()
            }
        }
        finally {
            $stream.Dispose()
        }
    }
    catch [System.IO.IOException] {
        throw "Another TITAN mission created a lock first. Aborting safely."
    }

    $script:LockAcquired = $true
}

function Remove-MissionLock {
    if (-not $script:LockAcquired -or -not (Test-Path -LiteralPath $LockPath)) {
        return
    }

    $lock = Read-MissionLock
    if ($null -ne $lock -and [int]$lock.pid -eq $PID) {
        Remove-Item -LiteralPath $LockPath -Force
        Write-Section "Mission Lock"
        Write-Host "Mission lock removed after successful completion."
    }
}

Push-Location $RepoRoot
try {
    Write-Section "TITAN Mission Runner"
    Write-Host "Mode: TEST ONLY"
    Write-Host "Mission: $MissionName"
    Write-Host "Repo: $RepoRoot"
    Write-Host "Prompt: $PromptPath"

    if (-not (Test-Path $PromptPath)) {
        throw "Missing mission prompt: $PromptPath"
    }

    Write-Section "Mission Lock"
    New-MissionLock
    Write-Host "Mission lock acquired: $LockPath"

    Write-Section "Guardrails"
    Write-Host "Live trading execution: blocked"
    Write-Host ".env changes: blocked"
    Write-Host "Supabase schema changes: blocked"
    Write-Host "Auto approval: blocked"
    Write-Host "Deployment: blocked"

    Write-Section "Git Status Before Execution"
    Invoke-Git -Arguments @("status", "--short", "--branch")

    Assert-Approval -Action "creating a rollback-safe mission branch" -Approved ([bool]$ApprovedForSetup)

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $slug = ($MissionName.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim("-")
    if ([string]::IsNullOrWhiteSpace($slug)) {
        $slug = "mission"
    }

    $branchName = "mission/$timestamp-$slug"
    $baseCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read base commit."
    }

    Write-Section "Rollback Base"
    Write-Host "Base commit: $baseCommit"
    Write-Host "Mission branch: $branchName"

    Invoke-Git -Arguments @("switch", "-c", $branchName)

    Write-Section "Diff Before Mission Work"
    Invoke-Git -Arguments @("diff", "--stat")
    Invoke-Git -Arguments @("diff", "--")

    Write-Section "Human Action Required"
    Write-Host "Review the mission prompt and current diff before making edits."
    Write-Host "This runner does not edit files, deploy, push, change .env, change Supabase schema, or touch live trading execution."

    if ($ApprovedForTests) {
        Assert-Approval -Action "running tests" -Approved ([bool]$ApprovedForTests)
        Assert-NoBlockedDiff

        Write-Section "Test Mode Validation"
        Write-Host "Guardrail validation passed."
        Write-Host "No project test command is hard-coded. Run approved tests explicitly after reviewing the diff."
    }
    else {
        Write-Section "Tests Skipped"
        Write-Host "Tests require separate explicit approval."
    }

    $script:MissionCompleted = $true
}
finally {
    Remove-MissionLock
    if (-not $script:MissionCompleted) {
        Write-Section "Mission Ended"
        Write-Host "Mission ended before successful completion. Runtime lock cleanup was attempted."
    }
    Pop-Location
}
