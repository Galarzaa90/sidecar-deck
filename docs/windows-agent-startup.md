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

Install the package into a small temporary virtual environment, then let `sidecar-deck-agentctl` create the real agent installation and startup task.

```powershell
py -m venv $env:TEMP\sidecar-deck-bootstrap
& $env:TEMP\sidecar-deck-bootstrap\Scripts\python.exe -m pip install --upgrade pip
& $env:TEMP\sidecar-deck-bootstrap\Scripts\python.exe -m pip install "git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=agent"
& $env:TEMP\sidecar-deck-bootstrap\Scripts\sidecar-deck-agentctl.exe install `
  --dashboard-url http://homelab.local:8080 `
  --metrics-token change-me `
  --hostname gaming-pc
```

If LibreHardwareMonitor is running as Administrator and you want WMI temperatures, add `--run-elevated` to the install command so the agent task can query the same elevated WMI provider.

For a private repository, use a GitHub authentication method supported by your Git installation, such as Git Credential Manager or an SSH URL:

```powershell
& $env:TEMP\sidecar-deck-bootstrap\Scripts\sidecar-deck-agentctl.exe install `
  --source "git+ssh://git@github.com/Galarzaa90/sidecar-deck#subdirectory=agent" `
  --dashboard-url http://homelab.local:8080 `
  --metrics-token change-me `
  --hostname gaming-pc
```

To upgrade later:

```powershell
sidecar-deck-agentctl update
```

The install command adds `%LOCALAPPDATA%\SidecarDeckAgent\.venv\Scripts` to your user PATH. Open a new PowerShell window before running the short `sidecar-deck-agentctl ...` commands below.

## 3. Configure the Agent

The install command writes these values to `%LOCALAPPDATA%\SidecarDeckAgent\.env`.

```env
DASHBOARD_BASE_URL=http://homelab.local:8080
METRICS_TOKEN=change-me
PUSH_INTERVAL_SECONDS=1
HOSTNAME=gaming-pc
LOG_LEVEL=INFO
LIBRE_HARDWARE_MONITOR_API_URL=
LIBRE_HARDWARE_MONITOR_TIMEOUT_SECONDS=0.75
TEMPERATURE_SENSOR_LIMIT=0
```

Use the same `METRICS_TOKEN` configured for the backend. If `homelab.local` does not resolve from Windows, use the server IP address:

```env
DASHBOARD_BASE_URL=http://192.168.1.50:8080
```

To change settings later, edit the `.env` file and restart the task:

```powershell
notepad $env:LOCALAPPDATA\SidecarDeckAgent\.env
sidecar-deck-agentctl restart
```

## 4. Test the Agent Manually

```powershell
sidecar-deck-agentctl run
```

Expected startup output looks like:

```text
INFO starting agent for host=gaming-pc base_url=http://homelab.local:8080 metrics_url=http://homelab.local:8080/api/metrics interval=1.0s
```

Leave it running for a few seconds and confirm the dashboard shows the PC host. Stop the manual run with `Ctrl+C`.

If you see `metrics push failed`, check:

- The backend is running.
- Windows can open `http://homelab.local:8080/health` in a browser.
- `METRICS_TOKEN` matches the backend token.
- Windows Firewall or the network is not blocking access to the backend.

## 5. Verify the Startup Task

Confirm the registered task is using the windowless executable:

```powershell
(Get-ScheduledTask -TaskName "Sidecar Deck Agent").Actions |
  Format-List Execute,Arguments,WorkingDirectory
```

The `Execute` value should end with:

```text
%LOCALAPPDATA%\SidecarDeckAgent\.venv\Scripts\sidecar-deck-agentw.exe
```

If it ends with `sidecar-deck-agent.exe`, run `sidecar-deck-agentctl install` again so the task is recreated with the windowless executable.

## 6. Start and Verify the Task

Start the task immediately:

```powershell
sidecar-deck-agentctl start
```

Check task state:

```powershell
sidecar-deck-agentctl status
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
sidecar-deck-agentctl stop
```

Restart it:

```powershell
sidecar-deck-agentctl restart
```

Remove it:

```powershell
sidecar-deck-agentctl uninstall
```

## 8. Troubleshooting

### The task starts but no metrics appear

Run the agent in a visible console to see errors:

```powershell
sidecar-deck-agentctl run
```

Common causes are a wrong dashboard URL, wrong token, missing virtual environment packages, or a `.env` file that was not created in the task's working directory.

### Temperatures are missing

Run the agent visibly with debug logs:

```powershell
notepad $env:LOCALAPPDATA\SidecarDeckAgent\.env
sidecar-deck-agentctl run
```

Set:

```env
LOG_LEVEL=DEBUG
```

Enable LibreHardwareMonitor's remote web server and set:

```env
LIBRE_HARDWARE_MONITOR_API_URL=http://127.0.0.1:8085/data.json
```

When this URL is set, the agent uses the LibreHardwareMonitor API for temperatures instead of WMI.

### A terminal window opens repeatedly

Stop the restart loop first:

```powershell
sidecar-deck-agentctl stop
```

Then inspect the task action:

```powershell
(Get-ScheduledTask -TaskName "Sidecar Deck Agent").Actions |
  Format-List Execute,Arguments,WorkingDirectory
```

If `Execute` ends with `sidecar-deck-agent.exe`, the task is using the console entry point. Run `sidecar-deck-agentctl install` again so it uses `sidecar-deck-agentw.exe`.

If metrics are still appearing on the dashboard and you have an NVIDIA GPU, the agent is probably working but `nvidia-smi` is opening a short-lived console window during GPU polling. Upgrade to the latest agent build:

```powershell
sidecar-deck-agentctl update
```

If `Execute` already ends with `sidecar-deck-agentw.exe` and metrics are not appearing, run the visible agent manually to see the startup error:

```powershell
sidecar-deck-agentctl run
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
