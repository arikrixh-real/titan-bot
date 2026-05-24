[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$StartMissionPath = Join-Path $PSScriptRoot "start_mission.ps1"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Read-MultilineMissionDescription {
    Write-Host "Mission description. Type END on a new line when finished."
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

Write-Section "Start TITAN Phase"

if (-not (Test-Path -LiteralPath $StartMissionPath)) {
    throw "Missing start_mission.ps1: $StartMissionPath"
}

$phase = (Read-Host "Phase number/name").Trim()
if ([string]::IsNullOrWhiteSpace($phase)) {
    throw "Phase number/name is required."
}

$missionDescription = Read-MultilineMissionDescription
if ([string]::IsNullOrWhiteSpace($missionDescription)) {
    throw "Mission description is required."
}

& $StartMissionPath `
    -InteractiveStart `
    -Phase $phase `
    -MissionDescription $missionDescription
