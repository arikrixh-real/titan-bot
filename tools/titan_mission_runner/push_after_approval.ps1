[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForPush,

    [Parameter(Mandatory = $false)]
    [string]$ApprovalToken
)

$ErrorActionPreference = "Stop"

$RequiredApprovalToken = "I_APPROVE_TITAN_PUSH"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LockPath = Join-Path $PSScriptRoot "mission.lock"

$BlockedPathPatterns = @(
    "\.env$",
    "\.env\.",
    "(^|[\\/])supabase([\\/]|$)",
    "(^|[\\/])migrations([\\/]|$)",
    "schema\.sql$",
    "schema.*\.sql$"
)

$MainBranchDirtyPathPatterns = @(
    "^data/",
    "^reports/",
    "^runtime_",
    "^logs/",
    "heartbeat",
    "status"
)

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Invoke-GitCapture {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }

    return $output
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

function Test-MainBranchDirtyPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $normalized = $Path -replace "\\", "/"
    foreach ($pattern in $MainBranchDirtyPathPatterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }

    return $false
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

function Assert-NoActiveMissionLock {
    if (-not (Test-Path -LiteralPath $LockPath)) {
        return
    }

    try {
        $lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Mission lock exists but cannot be parsed: $LockPath. Refusing to push."
    }

    if ($null -eq $lock.pid) {
        throw "Mission lock exists without a PID: $LockPath. Refusing to push."
    }

    $lockPid = [int]$lock.pid
    if (Test-ProcessAlive -ProcessId $lockPid) {
        throw "Active mission.lock detected for PID $lockPid. Refusing to push while a mission is running."
    }

    Write-Host "Stale mission.lock detected for inactive PID $lockPid; continuing without modifying it."
}

function Assert-NoStagedChanges {
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        throw "Staged changes exist. Commit or unstage them before push approval."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect staged changes."
    }
}

function Assert-NoBlockedWorkingDiff {
    $changedFiles = & git diff --name-only
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect unstaged changed files."
    }

    foreach ($file in $changedFiles) {
        if (Test-BlockedPath -Path $file) {
            throw "Blocked path detected in unstaged diff: $file"
        }
    }
}

function Assert-NoMainBranchRuntimeDataReportChanges {
    param([Parameter(Mandatory = $true)][string]$Branch)

    if ($Branch -ne "main") {
        return
    }

    $statusLines = & git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect git status."
    }

    foreach ($line in $statusLines) {
        if ($line.Length -lt 4) {
            continue
        }

        $indexStatus = $line.Substring(0, 1)
        $worktreeStatus = $line.Substring(1, 1)
        $path = $line.Substring(3)
        if ($path -match " -> ") {
            $path = ($path -split " -> ", 2)[1]
        }

        $hasUnstagedChange = $worktreeStatus -ne " "
        $isUntracked = $indexStatus -eq "?" -and $worktreeStatus -eq "?"
        if (($hasUnstagedChange -or $isUntracked) -and (Test-MainBranchDirtyPath -Path $path)) {
            throw "Refusing to push main with unstaged runtime/data/report change: $path"
        }
    }
}

Push-Location $RepoRoot
try {
    Write-Section "Push After Approval"
    Write-Host "Mode: REVIEWED PUSH ONLY"
    Write-Host "Repo: $RepoRoot"

    Write-Section "Current Branch"
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
        throw "Unable to determine current git branch."
    }
    Write-Host $branch

    Write-Section "Latest Commit"
    $latestCommitHash = (Invoke-GitCapture -Arguments @("rev-parse", "HEAD")).Trim()
    if ([string]::IsNullOrWhiteSpace($latestCommitHash)) {
        throw "Latest commit is missing. Refusing to push."
    }
    $latestCommitMessage = (Invoke-GitCapture -Arguments @("log", "-1", "--pretty=%s")).Trim()
    if ([string]::IsNullOrWhiteSpace($latestCommitMessage)) {
        throw "Latest commit message is missing. Refusing to push."
    }
    Write-Host "Hash: $latestCommitHash"
    Write-Host "Message: $latestCommitMessage"

    Write-Section "Git Status"
    Invoke-Git -Arguments @("status", "--short")

    Write-Section "Origin Main Diff Stat"
    & git rev-parse --verify "origin/main" *> $null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Git -Arguments @("diff", "--stat", "origin/main..HEAD")
    }
    else {
        Write-Host "origin/main is not available; skipping origin/main..HEAD diff stat."
    }

    Write-Section "Safety Checks"
    Assert-NoActiveMissionLock
    Assert-NoStagedChanges
    Assert-NoBlockedWorkingDiff
    Assert-NoMainBranchRuntimeDataReportChanges -Branch $branch
    Write-Host "No active mission lock, staged changes, or blocked working diff detected."

    if (-not $ApprovedForPush -or $ApprovalToken -ne $RequiredApprovalToken) {
        throw "Push blocked. Re-run with -ApprovedForPush and exact -ApprovalToken '$RequiredApprovalToken'."
    }

    Write-Section "Pushing"
    Write-Host "Command: git push -u origin $branch"
    Invoke-Git -Arguments @("push", "-u", "origin", $branch)
    Write-Host "Push complete. No deployment or daemon restart was performed."
}
finally {
    Pop-Location
}
