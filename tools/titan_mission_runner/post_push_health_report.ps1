[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

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

Push-Location $RepoRoot
try {
    Write-Section "Post Push Health Report"
    Write-Host "Mode: READ ONLY"
    Write-Host "Repo: $RepoRoot"
    Write-Host "No daemon restart, deploy, push, or file modification is performed."

    Write-Section "Branch"
    Invoke-Git -Arguments @("branch", "--show-current")

    Write-Section "Latest Commit"
    Invoke-Git -Arguments @("log", "-1", "--decorate", "--stat")

    Write-Section "Git Status"
    Invoke-Git -Arguments @("status", "--short", "--branch")
}
finally {
    Pop-Location
}
