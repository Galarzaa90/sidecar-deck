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
        return $RequestedSource
    }

    if (Test-Path $SourceFile) {
        $saved = (Get-Content $SourceFile -Raw).Trim()
        if ($saved) {
            return $saved
        }
    }

    return $DefaultSource
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
    $values = [ordered]@{
        DASHBOARD_BASE_URL = $DashboardUrl
        METRICS_TOKEN = $MetricsToken
        PUSH_INTERVAL_SECONDS = $Interval
        LOG_LEVEL = $LogLevel
    }

    if ($Hostname) {
        $values.HOSTNAME = $Hostname
    }

    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) {
            if (-not $line.Trim() -or $line.Trim().StartsWith("#") -or -not $line.Contains("=")) {
                continue
            }

            $key, $value = $line.Split("=", 2)
            if (-not $values.Contains($key.Trim())) {
                $values[$key.Trim()] = $value.Trim()
            }
        }
    }

    $content = foreach ($key in $values.Keys) {
        "$key=$($values[$key])"
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
  install      Create .venv, install the package, write .env, register and start the task.
  update       Reinstall the package from the saved or supplied source and recreate the task.
  start        Start the Scheduled Task.
  stop         Stop the Scheduled Task.
  restart      Stop and start the Scheduled Task.
  status       Show Scheduled Task status and action details.
  run          Run the agent in the foreground for troubleshooting.
  uninstall    Remove the Scheduled Task. Agent files are left in place.
  help         Show this help.

Install options:
  -DashboardUrl <url>     Backend URL. Default: http://homelab.local:8080
  -MetricsToken <token>   Bearer token expected by the backend. Default: change-me
  -Interval <seconds>     Metrics push interval. Default: 1
  -Hostname <name>        Dashboard host label. Defaults to the machine hostname if omitted.
  -LogLevel <level>       Agent log level. Default: INFO
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
