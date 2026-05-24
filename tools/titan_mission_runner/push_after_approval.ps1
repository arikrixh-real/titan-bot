[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForPush,

    [Parameter(Mandatory = $false)]
    [string]$ApprovalToken
)

$ErrorActionPreference = "Stop"

$RequiredApprovalToken = "I_APPROVE_TITAN_PUSH_AFTER_DIFF_REVIEW"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

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

    if ($branch -notmatch "^mission/") {
        throw "Refusing to push from non-mission branch: $branch"
    }

    Write-Section "Git Status"
    Invoke-Git -Arguments @("status", "--short", "--branch")

    Write-Section "Diff Stat"
    Invoke-Git -Arguments @("diff", "--stat")

    Write-Section "Full Diff"
    Invoke-Git -Arguments @("diff", "--")

    $changedFiles = & git diff --name-only
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect changed files."
    }

    foreach ($file in $changedFiles) {
        if (Test-BlockedPath -Path $file) {
            throw "Blocked path detected in diff: $file"
        }
    }

    if (-not $ApprovedForPush -or $ApprovalToken -ne $RequiredApprovalToken) {
        throw "Push blocked. Review the full diff, then re-run with -ApprovedForPush and -ApprovalToken '$RequiredApprovalToken'."
    }

    Write-Section "Pushing"
    Invoke-Git -Arguments @("push", "-u", "origin", $branch)
    Write-Host "Push complete. No deployment was performed."
}
finally {
    Pop-Location
}
