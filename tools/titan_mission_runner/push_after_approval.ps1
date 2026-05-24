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
    $changedFiles = @(& git diff --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect unstaged changed files."
    }

    $untrackedFiles = @(& git ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect untracked files."
    }

    $allWorkingFiles = @($changedFiles + $untrackedFiles) | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    } | Sort-Object -Unique

    foreach ($file in $allWorkingFiles) {
        if (Test-BlockedPath -Path $file) {
            throw "Blocked path detected in working tree: $file"
        }
    }
}

function Get-GitStatusLines {
    $statusLines = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect git status."
    }

    return $statusLines
}

function Write-DirtyFiles {
    param([Parameter(Mandatory = $true)][string[]]$StatusLines)

    Write-Section "Dirty Files Before Push"
    if ($StatusLines.Count -eq 0) {
        Write-Host "Working tree is clean."
        return
    }

    foreach ($line in $StatusLines) {
        Write-Host $line
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
    Invoke-Git -Arguments @("cat-file", "-e", "HEAD^{commit}")
    $latestCommitMessage = (Invoke-GitCapture -Arguments @("log", "-1", "--pretty=%s")).Trim()
    Write-Host "Hash: $latestCommitHash"
    Write-Host "Message: $latestCommitMessage"

    Write-Section "Git Status"
    $statusLines = @(Get-GitStatusLines)
    if ($statusLines.Count -eq 0) {
        Write-Host "Working tree is clean."
    }
    else {
        foreach ($line in $statusLines) {
            Write-Host $line
        }
    }
    Write-DirtyFiles -StatusLines $statusLines

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
    Write-Host "No active mission lock, staged changes, or blocked working tree paths detected."

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
