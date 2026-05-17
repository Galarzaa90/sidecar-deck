# Windows Agent Startup Guide

This guide configures the Sidecar Deck PC agent to start automatically on Windows and keep running in the background. The agent is a Python process that reads a `.env` file from its working directory, collects local metrics, and pushes them to the backend.

Target setup:

```text
Windows gaming PC
  -> Python virtual environment with sidecar-deck-agent installed
  -> .env with dashboard URL and token
  -> Windows Task Scheduler background task
  -> starts at user sign-in
```

## 1. Install Python

Install Python 3.11 or newer from:

```text
https://www.python.org/downloads/windows/
```

During installation, enable:

```text
Add python.exe to PATH
```

Open PowerShell and confirm Python works:

```powershell
py --version
```

## 2. Install the Agent

Install the agent directly from Git. This keeps only the agent virtual environment and local config on the Windows PC.

```powershell
mkdir C:\SidecarDeckAgent
cd C:\SidecarDeckAgent
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install "git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=agent"
notepad .env
```

For a private repository, use a GitHub authentication method supported by your Git installation, such as Git Credential Manager or an SSH URL:

```powershell
.\.venv\Scripts\python.exe -m pip install "git+ssh://git@github.com/Galarzaa90/sidecar-deck#subdirectory=agent"
```

To upgrade later:

```powershell
cd C:\SidecarDeckAgent
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall "git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=agent"
```

## 3. Configure the Agent

Set these values in `C:\SidecarDeckAgent\.env`.

```env
DASHBOARD_BASE_URL=http://homelab.local:8080
METRICS_TOKEN=change-me
PUSH_INTERVAL_SECONDS=1
HOSTNAME=gaming-pc
LOG_LEVEL=INFO
```

Use the same `METRICS_TOKEN` configured for the backend. If `homelab.local` does not resolve from Windows, use the server IP address:

```env
DASHBOARD_BASE_URL=http://192.168.1.50:8080
```

## 4. Test the Agent Manually

From the directory that contains `.env`:

```powershell
.\.venv\Scripts\sidecar-deck-agent.exe
```

Expected startup output looks like:

```text
INFO starting agent for host=gaming-pc base_url=http://homelab.local:8080 metrics_url=http://homelab.local:8080/api/metrics interval=1.0s
```

Leave it running for a few seconds and confirm the dashboard switches from demo metrics to the PC host. Stop the manual run with `Ctrl+C`.

If you see `metrics push failed`, check:

- The backend is running.
- Windows can open `http://homelab.local:8080/health` in a browser.
- `METRICS_TOKEN` matches the backend token.
- Windows Firewall or the network is not blocking access to the backend.

## 5. Create a Background Startup Task

Use Task Scheduler so the agent starts automatically when you sign in.

Open PowerShell as your normal Windows user, not as Administrator.

Run the whole block in one PowerShell session. The `$Action` variable is created near the top and then passed to `Register-ScheduledTask`; if you only run the registration lines later, PowerShell will report that the `Action` argument is null.

```powershell
Stop-ScheduledTask -TaskName "Sidecar Deck Agent" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "Sidecar Deck Agent" -Confirm:$false -ErrorAction SilentlyContinue

cd C:\SidecarDeckAgent

$InstallDir = (Get-Location).Path
$AgentExe = Join-Path $InstallDir ".venv\Scripts\sidecar-deck-agentw.exe"

if (-not (Test-Path $AgentExe)) {
  throw "Agent executable was not found at $AgentExe. Re-run the install step first."
}

$Action = New-ScheduledTaskAction `
  -Execute $AgentExe `
  -WorkingDirectory $InstallDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal `
  -UserId $CurrentUser `
  -LogonType Interactive `
  -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -StartWhenAvailable

Register-ScheduledTask `
  -TaskName "Sidecar Deck Agent" `
  -Description "Pushes Windows PC metrics to the Sidecar Deck dashboard." `
  -Action $Action `
  -Trigger $Trigger `
  -Principal $Principal `
  -Settings $Settings
```

The task uses `sidecar-deck-agentw.exe`, which runs without opening a console window. The task's working directory is set to the directory containing `.env`, so the installed agent can load its configuration.

Confirm the registered task is using the windowless executable:

```powershell
(Get-ScheduledTask -TaskName "Sidecar Deck Agent").Actions |
  Format-List Execute,Arguments,WorkingDirectory
```

The `Execute` value should end with:

```text
C:\SidecarDeckAgent\.venv\Scripts\sidecar-deck-agentw.exe
```

If it ends with `sidecar-deck-agent.exe`, recreate the task with the block above.

## 6. Start and Verify the Task

Start the task immediately:

```powershell
Start-ScheduledTask -TaskName "Sidecar Deck Agent"
```

Check task state:

```powershell
Get-ScheduledTask -TaskName "Sidecar Deck Agent" | Get-ScheduledTaskInfo
```

Useful fields:

- `LastRunTime` should update after starting the task.
- `LastTaskResult` should be `0` for a successful launch.
- `NumberOfMissedRuns` should normally stay at `0`.

You can also check for the hidden Python process:

```powershell
Get-Process sidecar-deck-agentw, pythonw -ErrorAction SilentlyContinue
```

Then confirm the dashboard is receiving current metrics from the configured host name.

## 7. Stop, Restart, or Remove the Task

Stop the background agent:

```powershell
Stop-ScheduledTask -TaskName "Sidecar Deck Agent"
```

Restart it:

```powershell
Stop-ScheduledTask -TaskName "Sidecar Deck Agent"
Start-ScheduledTask -TaskName "Sidecar Deck Agent"
```

Remove it:

```powershell
Unregister-ScheduledTask -TaskName "Sidecar Deck Agent" -Confirm:$false
```

## 8. Troubleshooting

### The task starts but no metrics appear

Run the agent in a visible console to see errors:

```powershell
cd C:\SidecarDeckAgent
.\.venv\Scripts\sidecar-deck-agent.exe
```

Common causes are a wrong dashboard URL, wrong token, missing virtual environment packages, or a `.env` file that was not created in the task's working directory.

### A terminal window opens repeatedly

Stop the restart loop first:

```powershell
Stop-ScheduledTask -TaskName "Sidecar Deck Agent"
```

Then inspect the task action:

```powershell
(Get-ScheduledTask -TaskName "Sidecar Deck Agent").Actions |
  Format-List Execute,Arguments,WorkingDirectory
```

If `Execute` ends with `sidecar-deck-agent.exe`, the task is using the console entry point. Recreate the task with the block in step 5 so it uses `sidecar-deck-agentw.exe`.

If metrics are still appearing on the dashboard and you have an NVIDIA GPU, the agent is probably working but `nvidia-smi` is opening a short-lived console window during GPU polling. Upgrade to the latest agent build:

```powershell
Stop-ScheduledTask -TaskName "Sidecar Deck Agent"
cd C:\SidecarDeckAgent
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall "git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=agent"
Start-ScheduledTask -TaskName "Sidecar Deck Agent"
```

If `Execute` already ends with `sidecar-deck-agentw.exe` and metrics are not appearing, run the visible agent manually from `C:\SidecarDeckAgent` to see the startup error:

```powershell
cd C:\SidecarDeckAgent
.\.venv\Scripts\sidecar-deck-agent.exe
```

Fix the visible error, then start the task again.

### The task does not start at sign-in

Open Task Scheduler and check:

```text
Task Scheduler Library -> Sidecar Deck Agent -> History
```

If history is disabled, enable it from:

```text
Task Scheduler -> Enable All Tasks History
```

Also confirm the task was registered for your current user:

```powershell
Get-ScheduledTask -TaskName "Sidecar Deck Agent"
```

### GPU metrics are missing

The agent can read NVIDIA GPU metrics when `nvidia-smi` is available on `PATH`. Install or update the NVIDIA driver, then test:

```powershell
nvidia-smi
```

CPU, memory, network, disk, uptime, and hostname metrics work without NVIDIA tooling.
