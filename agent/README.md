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
LOGITECH_BATTERY_POLL_SECONDS=30
BLUETOOTH_BATTERY_POLL_SECONDS=60
XINPUT_BATTERY_POLL_SECONDS=30
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

## Peripheral Batteries

The agent reports supported peripheral batteries through `peripheralBatteries`. Logitech devices are read through the local Logitech G Hub WebSocket, Bluetooth Low Energy devices are read through the GATT Battery Service, and Xbox controllers are read through Windows XInput.

If an Xbox controller battery is missing, run the agent interactively with `LOG_LEVEL=DEBUG` and confirm the controller is connected to Windows before the agent polls. The XInput battery level is reported in coarse Windows levels, so the dashboard may show values like `25`, `60`, or `100` rather than an exact percentage.

## Local Diagnostics

The agent starts a local-only diagnostic HTTP server by default at `http://127.0.0.1:8765`.

- `/` shows the latest collected payload in a small auto-refreshing browser page.
- `/metrics` returns the latest collected payload as JSON.

Set `DIAGNOSTIC_HTTP_PORT=0` to disable it, or change `DIAGNOSTIC_HTTP_HOST` and `DIAGNOSTIC_HTTP_PORT` if the default port is already in use.

## Windows Agent Control

`SidecarDeckAgent.ps1` is the Windows installer and control script. `SidecarDeckAgent.bat` is a small Command Prompt wrapper around the same PowerShell script.

Copy both files into the directory where the agent should live, such as `C:\SidecarDeckAgent`. That directory becomes the base directory for:

- `.venv`
- `.env`
- `.install-source`
- the Scheduled Task working directory

Example setup from a checkout of this repo:

```powershell
mkdir C:\SidecarDeckAgent
copy .\agent\SidecarDeckAgent.ps1 C:\SidecarDeckAgent\
copy .\agent\SidecarDeckAgent.bat C:\SidecarDeckAgent\
cd C:\SidecarDeckAgent
```

Install and start the background agent:

```powershell
.\SidecarDeckAgent.ps1 install -DashboardUrl http://homelab.local:8080 -MetricsToken change-me -Hostname gaming-pc
```

Or from Command Prompt:

```bat
SidecarDeckAgent.bat install -DashboardUrl http://homelab.local:8080 -MetricsToken change-me -Hostname gaming-pc
```

If LibreHardwareMonitor is running as Administrator, install the agent task with highest privileges too:

```powershell
.\SidecarDeckAgent.ps1 install -RunElevated -DashboardUrl http://homelab.local:8080 -MetricsToken change-me -Hostname gaming-pc
```

By default, the script installs the package from `git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=agent`. Use `-Source` to install from a different Git URL, wheel, or local package directory.

Run interactively to see logs in the terminal:

```powershell
.\SidecarDeckAgent.ps1 run
```

Stop the interactive run with `Ctrl+C`. For more detailed logs, set `LOG_LEVEL=DEBUG` in `.env`.

Common commands:

```powershell
.\SidecarDeckAgent.ps1 status
.\SidecarDeckAgent.ps1 start
.\SidecarDeckAgent.ps1 stop
.\SidecarDeckAgent.ps1 restart
.\SidecarDeckAgent.ps1 update
.\SidecarDeckAgent.ps1 uninstall
.\SidecarDeckAgent.ps1 run
.\SidecarDeckAgent.ps1 help
```

For background startup on Windows, see [../docs/windows-agent-startup.md](../docs/windows-agent-startup.md).
