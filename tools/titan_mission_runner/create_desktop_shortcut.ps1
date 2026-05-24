[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$StartPhasePath = Join-Path $PSScriptRoot "start_phase.ps1"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "Start TITAN Phase.lnk"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

Write-Section "Create TITAN Phase Shortcut"

if (-not (Test-Path -LiteralPath $StartPhasePath)) {
    throw "Missing start_phase.ps1: $StartPhasePath"
}

if ([string]::IsNullOrWhiteSpace($DesktopPath) -or -not (Test-Path -LiteralPath $DesktopPath)) {
    throw "Unable to locate the current user's Desktop folder."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$StartPhasePath`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "powershell.exe,0"
$shortcut.Description = "Start TITAN phase mission runner"
$shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath"
Write-Host "Target: $StartPhasePath"
Write-Host "No admin permissions were required."
