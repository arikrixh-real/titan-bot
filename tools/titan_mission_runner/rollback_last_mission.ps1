[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ApprovedForRollback,

    [Parameter(Mandatory = $false)]
    [string]$ApprovalToken
)

$ErrorActionPreference = "Stop"

$RequiredApprovalToken = "I_APPROVE_TITAN_ROLLBACK"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

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

Push-Location $RepoRoot
try {
    Write-Section "Rollback Last TITAN Mission"
    Write-Host "Mode: REVERT ONLY"
    Write-Host "Repo: $RepoRoot"

    Write-Section "Current Branch"
    $branch = (Invoke-GitCapture -Arguments @("branch", "--show-current")).Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw "Unable to determine current git branch."
    }
    Write-Host $branch

    Write-Section "Latest Commit"
    Invoke-Git -Arguments @("log", "-1", "--decorate", "--stat")

    if (-not $ApprovedForRollback -or $ApprovalToken -ne $RequiredApprovalToken) {
        throw "Rollback blocked. Re-run with -ApprovedForRollback and exact -ApprovalToken '$RequiredApprovalToken'."
    }

    Write-Section "Reverting Latest Commit"
    Write-Host "Command: git revert --no-edit HEAD"
    Invoke-Git -Arguments @("revert", "--no-edit", "HEAD")
    Write-Host "Rollback complete. No reset --hard, deployment, daemon restart, or push was performed."
}
finally {
    Pop-Location
}
