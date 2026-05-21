# Sidecar Deck Agent

Python application focused on Windows that collects local metrics and pushes them to the [backend app](../backend/).

## Available Data

- System Metrics via [psutil](https://pypi.org/project/psutil/)
- Temperatures via [LibreHardwareMonitor](https://github.com/LibreHardwaRemonitor/LibreHardwareMonitor)
- Logitech G Hub devices battery levels
- Bluetooth devices battery levels
- Windows device and Phone Link battery levels
- NVIDIA cards via `nvidia-smi`


## Development

```sh
pip install -e .
sidecar-deck-agent
```

Useful CLI probes:

```sh
sidecar-deck-agent one-shot
sidecar-deck-agent one-shot cpu
sidecar-deck-agent one-shot battery
sidecar-deck-agent debug cpu
sidecar-deck-agent debug battery
python pc_agent.py debug battery
```

## Environment

See [.env.example](.env.example) for the available configuration options.


## Hardware Temperatures

On Windows, set `LIBRE_HARDWARE_MONITOR_API_URL` to read temperatures from LibreHardwareMonitor's web API. If the API URL is not set, the agent falls back to LibreHardwareMonitor/OpenHardwareMonitor WMI.

If temperatures are missing, run the agent with `LOG_LEVEL=DEBUG`. These messages are useful:

- `libre hardware monitor API lookup failed` means the LibreHardwareMonitor web server is not reachable.
- `Invalid namespace` means the fallback WMI namespace is unavailable.

Enable LibreHardwareMonitor's remote web server and set `LIBRE_HARDWARE_MONITOR_API_URL=http://127.0.0.1:8085/data.json`.


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
.\SidecarDeckAgent.ps1 install -DashboardUrl http://homelab.local:8080
```

Or from Command Prompt:

```bat
SidecarDeckAgent.bat install -DashboardUrl http://homelab.local:8080
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
