[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$RequestPath,

    [Parameter(Mandatory = $false)]
    [string]$CodexCommand = "codex"
)

$ErrorActionPreference = "Stop"

$RequiredApprovalToken = "I_APPROVE_TITAN_MISSION_START"
$StartMissionPath = Join-Path $PSScriptRoot "start_mission.ps1"
$InboxDir = Join-Path $PSScriptRoot "inbox"
$ArchiveDir = Join-Path $PSScriptRoot "archive"
$FailedDir = Join-Path $PSScriptRoot "failed"
$LogDir = Join-Path $PSScriptRoot "logs"
$BridgeStartedAt = Get-Date
$BridgeTimestamp = $BridgeStartedAt.ToString("yyyyMMdd-HHmmss")
$BridgeLogPath = Join-Path $LogDir "local-bridge-$BridgeTimestamp.log"
$RunnerLogPath = Join-Path $LogDir "local-bridge-runner-$BridgeTimestamp.log"

if ([string]::IsNullOrWhiteSpace($RequestPath)) {
    $RequestPath = Join-Path $InboxDir "mission_request.json"
}

function Initialize-BridgeDirectories {
    foreach ($dir in @($InboxDir, $ArchiveDir, $FailedDir, $LogDir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Write-BridgeLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $line = "[{0}] {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message
    Add-Content -LiteralPath $BridgeLogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function New-RequestDestinationPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DestinationDir,

        [Parameter(Mandatory = $true)]
        [string]$SourcePath
    )

    $sourceName = [System.IO.Path]::GetFileNameWithoutExtension($SourcePath)
    $sourceExtension = [System.IO.Path]::GetExtension($SourcePath)
    if ([string]::IsNullOrWhiteSpace($sourceName)) {
        $sourceName = "mission_request"
    }
    if ([string]::IsNullOrWhiteSpace($sourceExtension)) {
        $sourceExtension = ".json"
    }

    $destination = Join-Path $DestinationDir ("{0}-{1}{2}" -f $sourceName, $BridgeTimestamp, $sourceExtension)
    if (-not (Test-Path -LiteralPath $destination)) {
        return $destination
    }

    return (Join-Path $DestinationDir ("{0}-{1}-{2}{3}" -f $sourceName, $BridgeTimestamp, [guid]::NewGuid().ToString("N"), $sourceExtension))
}

function Move-RequestFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DestinationDir,

        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    if (-not (Test-Path -LiteralPath $RequestPath)) {
        Write-BridgeLog "Request file already absent; cannot move to $DestinationDir. Reason: $Reason"
        return
    }

    $destination = New-RequestDestinationPath -DestinationDir $DestinationDir -SourcePath $RequestPath
    Move-Item -LiteralPath $RequestPath -Destination $destination
    Write-BridgeLog "Moved request to $destination. Reason: $Reason"
}

function Read-MissionRequest {
    if (-not (Test-Path -LiteralPath $RequestPath)) {
        throw "Mission request not found: $RequestPath"
    }

    try {
        return Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Mission request is not valid JSON: $($_.Exception.Message)"
    }
}

function Assert-MissionRequest {
    param(
        [Parameter(Mandatory = $true)]
        $Request
    )

    if ([string]::IsNullOrWhiteSpace($Request.phase)) {
        throw "Mission request field 'phase' is required."
    }
    if ([string]::IsNullOrWhiteSpace($Request.mission)) {
        throw "Mission request field 'mission' is required."
    }
    if ($Request.approval_token -ne $RequiredApprovalToken) {
        throw "Mission request approval_token is missing or incorrect. Expected exact token '$RequiredApprovalToken'."
    }
}

function Invoke-StartMission {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Phase,

        [Parameter(Mandatory = $true)]
        [string]$Mission
    )

    if (-not (Test-Path -LiteralPath $StartMissionPath)) {
        throw "Missing start_mission.ps1: $StartMissionPath"
    }

    $startArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $StartMissionPath,
        "-InteractiveStart",
        "-Phase", $Phase,
        "-MissionDescription", $Mission,
        "-ApprovalToken", $RequiredApprovalToken,
        "-CodexCommand", $CodexCommand
    )

    Write-BridgeLog "Launching existing mission flow: $StartMissionPath"
    Write-BridgeLog "Runner output log: $RunnerLogPath"
    Write-BridgeLog "Auto-push: not performed by local bridge."

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & powershell @startArgs *> $RunnerLogPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if (Test-Path -LiteralPath $RunnerLogPath) {
        Add-Content -LiteralPath $BridgeLogPath -Value "----- start_mission.ps1 output -----" -Encoding UTF8
        Get-Content -LiteralPath $RunnerLogPath | Add-Content -LiteralPath $BridgeLogPath -Encoding UTF8
        Add-Content -LiteralPath $BridgeLogPath -Value "----- end start_mission.ps1 output -----" -Encoding UTF8
    }

    if ($exitCode -ne 0) {
        throw "start_mission.ps1 failed with exit code $exitCode. Review $RunnerLogPath"
    }

    Write-BridgeLog "Existing mission flow completed successfully."
}

Initialize-BridgeDirectories
Write-BridgeLog "TITAN local mission bridge started."
Write-BridgeLog "Request path: $RequestPath"
Write-BridgeLog "Network server: disabled. Public port: none. Webhook: none."

try {
    $request = Read-MissionRequest
    Write-BridgeLog "Mission request JSON parsed."

    Assert-MissionRequest -Request $request
    $phase = ([string]$request.phase).Trim()
    $mission = ([string]$request.mission).Trim()
    Write-BridgeLog "Approval token accepted."
    Write-BridgeLog "Phase: $phase"

    Invoke-StartMission -Phase $phase -Mission $mission
    Move-RequestFile -DestinationDir $ArchiveDir -Reason "mission completed"
    Write-BridgeLog "TITAN local mission bridge completed."
}
catch {
    Write-BridgeLog "Bridge failed: $($_.Exception.Message)"
    try {
        Move-RequestFile -DestinationDir $FailedDir -Reason "bridge failure"
    }
    catch {
        Write-BridgeLog "Failed to move request after bridge failure: $($_.Exception.Message)"
    }

    throw
}
