# Sidecar Deck Agent

Windows Python process that collects local PC metrics and pushes them to the Sidecar Deck backend. It uses `psutil` for CPU, memory, network, disk, uptime, hostname, and process data. Temperature readings are reported through the top-level `temperatures` list, and GPU fields can be added through LibreHardwareMonitor, OpenHardwareMonitor, or vendor tooling without changing the backend API.

## Development

```sh
pip install -e .
sidecar-deck-agent
```

## Environment

```env
DASHBOARD_BASE_URL=http://homelab.local:8080
METRICS_TOKEN=change-me
PUSH_INTERVAL_SECONDS=1
HOSTNAME=gaming-pc
LOG_LEVEL=INFO
LIBRE_HARDWARE_MONITOR_API_URL=
LIBRE_HARDWARE_MONITOR_TIMEOUT_SECONDS=0.75
TEMPERATURE_SENSOR_LIMIT=6
DIAGNOSTIC_HTTP_HOST=127.0.0.1
DIAGNOSTIC_HTTP_PORT=8765
```

`METRICS_TOKEN` must match the backend token. `HOSTNAME` controls the label shown in the dashboard; omit or change it if you want the agent to use the local machine name.

## Hardware Temperatures

On Windows, set `LIBRE_HARDWARE_MONITOR_API_URL` to read temperatures from LibreHardwareMonitor's web API. If the API URL is not set, the agent falls back to LibreHardwareMonitor/OpenHardwareMonitor WMI.

If temperatures are missing, run the agent with `LOG_LEVEL=DEBUG`. These messages are useful:

- `libre hardware monitor API lookup failed` means the LibreHardwareMonitor web server is not reachable.
- `Invalid namespace` means the fallback WMI namespace is unavailable.

Enable LibreHardwareMonitor's remote web server and set `LIBRE_HARDWARE_MONITOR_API_URL=http://127.0.0.1:8085/data.json`.

Temperature readings include a `source` field such as `lhm-api`, `nvidia-smi`, `psutil`, or `acpi`. `TEMPERATURE_SENSOR_LIMIT` caps the payload before it reaches the dashboard; set it to `0` only when you want to send every temperature sensor.

## Local Diagnostics

The agent starts a local-only diagnostic HTTP server by default at `http://127.0.0.1:8765`.

- `/` shows the latest collected payload in a small auto-refreshing browser page.
- `/metrics` returns the latest collected payload as JSON.

Set `DIAGNOSTIC_HTTP_PORT=0` to disable it, or change `DIAGNOSTIC_HTTP_HOST` and `DIAGNOSTIC_HTTP_PORT` if the default port is already in use.

## Windows Agent Control

`sidecar-deck-agentctl` installs and manages the agent as a Windows Scheduled Task.

Install the control tool from Git once:

```powershell
py -m venv $env:TEMP\sidecar-deck-bootstrap
& $env:TEMP\sidecar-deck-bootstrap\Scripts\python.exe -m pip install --upgrade pip
& $env:TEMP\sidecar-deck-bootstrap\Scripts\python.exe -m pip install "git+https://github.com/<owner>/sidecar-deck.git#subdirectory=agent"
```

Install and start the background agent:

```powershell
& $env:TEMP\sidecar-deck-bootstrap\Scripts\sidecar-deck-agentctl.exe install --dashboard-url http://homelab.local:8080 --metrics-token change-me --hostname gaming-pc
```

If LibreHardwareMonitor is running as Administrator, install the agent task with highest privileges too:

```powershell
sidecar-deck-agentctl install --run-elevated --dashboard-url http://homelab.local:8080 --metrics-token change-me --hostname gaming-pc
```

The install command creates `%LOCALAPPDATA%\SidecarDeckAgent`, writes `.env`, registers the startup task, starts it, and adds the agent's `Scripts` directory to your user PATH. Open a new PowerShell window after installation.

Common commands:

```powershell
sidecar-deck-agentctl status
sidecar-deck-agentctl start
sidecar-deck-agentctl stop
sidecar-deck-agentctl restart
sidecar-deck-agentctl update
sidecar-deck-agentctl uninstall
sidecar-deck-agentctl run
```

Use `--install-dir C:\SidecarDeckAgent` if you want a fixed install location instead of `%LOCALAPPDATA%\SidecarDeckAgent`.

For background startup on Windows, see [../docs/windows-agent-startup.md](../docs/windows-agent-startup.md).
