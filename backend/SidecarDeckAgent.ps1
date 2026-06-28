[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "update", "uninstall", "start", "stop", "restart", "status", "run", "help")]
    [string]$Command = "install",

    [string]$DashboardUrl = "http://homelab.local:8080",
    [string]$MetricsToken = "change-me",
    [string]$Interval = "1",
    [string]$Hostname,
    [string]$LogLevel = "INFO",
    [string]$Source,
    [string]$TaskName = "Sidecar Deck Agent",
    [switch]$RunElevated,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $BaseDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$AgentExe = Join-Path $VenvDir "Scripts\sidecar-deck-agent.exe"
$AgentWindowlessExe = Join-Path $VenvDir "Scripts\sidecar-deck-agentw.exe"
$EnvFile = Join-Path $BaseDir ".env"
$SourceFile = Join-Path $BaseDir ".install-source"
$DefaultSource = "sidecar-deck[agent] @ git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=backend"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$ExplicitDashboardUrl = $PSBoundParameters.ContainsKey("DashboardUrl")
$ExplicitMetricsToken = $PSBoundParameters.ContainsKey("MetricsToken")
$ExplicitInterval = $PSBoundParameters.ContainsKey("Interval")
$ExplicitHostname = $PSBoundParameters.ContainsKey("Hostname")
$ExplicitLogLevel = $PSBoundParameters.ContainsKey("LogLevel")

function Invoke-LoggedCommand {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    Write-Host ("+ " + ($Args -join " "))
    $executable = $Args[0]
    $remainingArgs = @()
    if ($Args.Count -gt 1) {
        $remainingArgs = $Args[1..($Args.Count - 1)]
    }
    & $executable @remainingArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Get-PythonLauncher {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source, "-3")
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    throw "Python was not found. Install Python 3.11 or newer and try again."
}

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Lines
    )

    [System.IO.File]::WriteAllLines($Path, $Lines, $Utf8NoBom)
}

function Ensure-Venv {
    if (Test-Path $PythonExe) {
        return
    }

    New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null
    $launcher = Get-PythonLauncher
    Invoke-LoggedCommand -Args ($launcher + @("-m", "venv", $VenvDir))
}

function Resolve-InstallSource {
    param([string]$RequestedSource)

    if ($RequestedSource) {
        return Convert-LegacyInstallSource -InstallSource $RequestedSource
    }

    if (Test-Path $SourceFile) {
        $saved = (Get-Content $SourceFile -Raw).Trim()
        if ($saved) {
            return Convert-LegacyInstallSource -InstallSource $saved
        }
    }

    return $DefaultSource
}

function Convert-LegacyInstallSource {
    param([Parameter(Mandatory = $true)][string]$InstallSource)

    $source = $InstallSource.Trim()
    if ($source -match "^(?:sidecar-deck-agent\s*@\s*)?(?<git>git\+.+)#subdirectory=agent$") {
        $migratedSource = "sidecar-deck[agent] @ $($Matches.git)#subdirectory=backend"
        Write-Host "Migrated legacy install source to $migratedSource"
        return $migratedSource
    }

    return $source
}

function Install-Package {
    param(
        [string]$InstallSource,
        [switch]$ForceReinstall
    )

    Ensure-Venv
    Invoke-LoggedCommand -Args @($PythonExe, "-m", "pip", "install", "--upgrade", "pip")

    $pipArgs = @($PythonExe, "-m", "pip", "install", "--upgrade")
    if ($ForceReinstall) {
        $pipArgs += "--force-reinstall"
    }
    $pipArgs += $InstallSource
    Invoke-LoggedCommand -Args $pipArgs
    Write-Utf8File -Path $SourceFile -Lines @($InstallSource)
}

function Write-AgentEnv {
    $requestedValues = [ordered]@{}

    if (Test-Path $EnvFile) {
        if (-not ($ExplicitDashboardUrl -or $ExplicitMetricsToken -or $ExplicitInterval -or $ExplicitHostname -or $ExplicitLogLevel)) {
            Write-Host "Preserved existing configuration: $EnvFile"
            return
        }
    }

    if ($ExplicitDashboardUrl -or -not (Test-Path $EnvFile)) {
        $requestedValues.DASHBOARD_BASE_URL = $DashboardUrl
    }

    if ($ExplicitMetricsToken -or -not (Test-Path $EnvFile)) {
        $requestedValues.METRICS_TOKEN = $MetricsToken
    }

    if ($ExplicitInterval -or -not (Test-Path $EnvFile)) {
        $requestedValues.PUSH_INTERVAL_SECONDS = $Interval
    }

    if ($ExplicitLogLevel -or -not (Test-Path $EnvFile)) {
        $requestedValues.LOG_LEVEL = $LogLevel
    }

    if ($ExplicitHostname) {
        $requestedValues.HOSTNAME = $Hostname
    } elseif ($Hostname -and -not (Test-Path $EnvFile)) {
        $requestedValues.HOSTNAME = $Hostname
    }

    if (-not (Test-Path $EnvFile)) {
        $content = foreach ($key in $requestedValues.Keys) {
            "$key=$($requestedValues[$key])"
        }
        Write-Utf8File -Path $EnvFile -Lines $content
        return
    }

    $seenKeys = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    $content = foreach ($line in Get-Content $EnvFile) {
        if (-not $line.Trim() -or $line.Trim().StartsWith("#") -or -not $line.Contains("=")) {
            $line
            continue
        }

        $key, $value = $line.Split("=", 2)
        $trimmedKey = $key.Trim()
        [void]$seenKeys.Add($trimmedKey)

        if ($requestedValues.Contains($trimmedKey)) {
            "$trimmedKey=$($requestedValues[$trimmedKey])"
        } else {
            $line
        }
    }

    foreach ($key in $requestedValues.Keys) {
        if (-not $seenKeys.Contains($key)) {
            $content += "$key=$($requestedValues[$key])"
        }
    }

    Write-Utf8File -Path $EnvFile -Lines $content
}

function Register-AgentTask {
    if (-not (Test-Path $AgentWindowlessExe)) {
        throw "Agent executable was not found at $AgentWindowlessExe"
    }

    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $runLevel = if ($RunElevated) { "Highest" } else { "Limited" }
    $action = New-ScheduledTaskAction -Execute $AgentWindowlessExe -WorkingDirectory $BaseDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel $runLevel
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable

    Register-ScheduledTask -TaskName $TaskName -Description "Pushes Windows PC metrics to the Sidecar Deck dashboard." -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
}

function Start-AgentTask {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started $TaskName"
}

function Stop-AgentTask {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "Stopped $TaskName"
}

function Show-AgentStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "not installed"
        return
    }

    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "state=$($task.State)"
    Write-Host "lastRunTime=$($info.LastRunTime)"
    Write-Host "lastTaskResult=$($info.LastTaskResult)"
    Write-Host "nextRunTime=$($info.NextRunTime)"
    Write-Host "runLevel=$($task.Principal.RunLevel)"
    $task.Actions | ForEach-Object {
        Write-Host "execute=$($_.Execute)"
        Write-Host "workingDirectory=$($_.WorkingDirectory)"
    }
}

function Show-Help {
    Write-Host @"
Sidecar Deck Agent

Usage:
  .\SidecarDeckAgent.ps1 <command> [options]
  SidecarDeckAgent.bat <command> [options]

Commands:
  install      Create .venv, install the package, preserve or create .env, register and start the task.
  update       Reinstall the package from the saved or supplied source and recreate the task.
  start        Start the Scheduled Task.
  stop         Stop the Scheduled Task.
  restart      Stop and start the Scheduled Task.
  status       Show Scheduled Task status and action details.
  run          Run the agent in the foreground for troubleshooting.
  uninstall    Remove the Scheduled Task. Agent files are left in place.
  help         Show this help.

Install options:
  -DashboardUrl <url>     Backend URL. Updates .env when supplied. Default for new .env: http://homelab.local:8080
  -MetricsToken <token>   Bearer token expected by the backend. Updates .env when supplied. Default for new .env: change-me
  -Interval <seconds>     Metrics push interval. Updates .env when supplied. Default for new .env: 1
  -Hostname <name>        Dashboard host label. Updates .env when supplied. Defaults to the machine hostname if omitted.
  -LogLevel <level>       Agent log level. Updates .env when supplied. Default for new .env: INFO
  -Source <source>        Git URL, wheel, or local package directory.
  -RunElevated            Register the task with highest privileges.
  -NoStart                Install or update without starting the task.
  -TaskName <name>        Scheduled Task name. Default: Sidecar Deck Agent

Base directory:
  $BaseDir

Default source:
  $DefaultSource
"@
}

switch ($Command) {
    "help" { Show-Help }
    "install" {
        $installSource = Resolve-InstallSource -RequestedSource $Source
        Install-Package -InstallSource $installSource
        Write-AgentEnv
        Register-AgentTask
        if (-not $NoStart) {
            Start-AgentTask
        }
        Write-Host "Installed Sidecar Deck agent in $BaseDir"
        Write-Host "Configuration: $EnvFile"
    }
    "update" {
        $installSource = Resolve-InstallSource -RequestedSource $Source
        Stop-AgentTask
        Install-Package -InstallSource $installSource -ForceReinstall
        Register-AgentTask
        if (-not $NoStart) {
            Start-AgentTask
        }
        Write-Host "Updated Sidecar Deck agent from $installSource"
    }
    "uninstall" {
        Stop-AgentTask
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Uninstalled scheduled task $TaskName"
        Write-Host "Agent files were left in $BaseDir"
    }
    "start" { Start-AgentTask }
    "stop" { Stop-AgentTask }
    "restart" {
        Stop-AgentTask
        Start-AgentTask
    }
    "status" { Show-AgentStatus }
    "run" {
        if (-not (Test-Path $AgentExe)) {
            throw "Agent executable was not found at $AgentExe"
        }
        & $AgentExe
    }
}
