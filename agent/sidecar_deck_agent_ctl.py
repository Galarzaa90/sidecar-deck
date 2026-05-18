from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path


DEFAULT_TASK_NAME = "Sidecar Deck Agent"
DEFAULT_GIT_SOURCE = "git+https://github.com/Galarzaa90/sidecar-deck#subdirectory=agent"
class CommandError(RuntimeError):
    pass


def default_install_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "SidecarDeckAgent"
    return Path.home() / "AppData" / "Local" / "SidecarDeckAgent"


def ensure_windows() -> None:
    if platform.system() != "Windows":
        raise CommandError("this management tool is intended for Windows")


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def run_powershell(script: str, *args: str) -> None:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"& {{ {script} }}",
        *args,
    ]
    subprocess.run(command, check=True)


def query_powershell(script: str, *args: str) -> str:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"& {{ {script} }}",
        *args,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def python_exe(install_dir: Path) -> Path:
    return install_dir / ".venv" / "Scripts" / "python.exe"


def agent_windowless_exe(install_dir: Path) -> Path:
    return install_dir / ".venv" / "Scripts" / "sidecar-deck-agentw.exe"


def agent_console_exe(install_dir: Path) -> Path:
    return install_dir / ".venv" / "Scripts" / "sidecar-deck-agent.exe"


def current_source() -> str:
    source_dir = Path(__file__).resolve().parent
    if (source_dir / "pyproject.toml").exists():
        return str(source_dir)
    return DEFAULT_GIT_SOURCE


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(path: Path, updates: dict[str, str | None]) -> None:
    values = read_env(path)
    for key, value in updates.items():
        if value is not None:
            values[key] = str(value)

    ordered_keys = [
        "DASHBOARD_BASE_URL",
        "METRICS_TOKEN",
        "PUSH_INTERVAL_SECONDS",
        "HOSTNAME",
        "LOG_LEVEL",
    ]
    all_keys = ordered_keys + sorted(key for key in values if key not in ordered_keys)
    content = "\n".join(f"{key}={values[key]}" for key in all_keys if key in values) + "\n"
    path.write_text(content, encoding="utf-8")


def save_install_source(install_dir: Path, source: str) -> None:
    (install_dir / ".install-source").write_text(source + "\n", encoding="utf-8")


def load_install_source(install_dir: Path) -> str:
    source_file = install_dir / ".install-source"
    if source_file.exists():
        return source_file.read_text(encoding="utf-8").strip() or DEFAULT_GIT_SOURCE
    return DEFAULT_GIT_SOURCE


def create_venv(install_dir: Path) -> None:
    if python_exe(install_dir).exists():
        return
    run([sys.executable, "-m", "venv", str(install_dir / ".venv")])


def install_package(install_dir: Path, source: str, *, force_reinstall: bool = False) -> None:
    pip_command = [str(python_exe(install_dir)), "-m", "pip", "install", "--upgrade", "pip"]
    run(pip_command)

    package_command = [str(python_exe(install_dir)), "-m", "pip", "install", "--upgrade"]
    if force_reinstall:
        package_command.append("--force-reinstall")
    package_command.append(source)
    run(package_command)


def register_task(install_dir: Path, task_name: str, *, run_elevated: bool = False) -> None:
    agent_exe = agent_windowless_exe(install_dir)
    if not agent_exe.exists():
        raise CommandError(f"agent executable was not found at {agent_exe}")

    run_level = "Highest" if run_elevated else "Limited"
    script = r"""
param($TaskName, $InstallDir, $AgentExe, $RunLevel)
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$Action = New-ScheduledTaskAction -Execute $AgentExe -WorkingDirectory $InstallDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel $RunLevel
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Description "Pushes Windows PC metrics to the Sidecar Deck dashboard." -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings | Out-Null
"""
    run_powershell(script, task_name, str(install_dir), str(agent_exe), run_level)


def add_scripts_to_user_path(install_dir: Path) -> None:
    scripts_dir = install_dir / ".venv" / "Scripts"
    script = r"""
param($ScriptsDir)
$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")
$Parts = @()
if (-not [string]::IsNullOrWhiteSpace($CurrentPath)) {
  $Parts = $CurrentPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}
if ($Parts -notcontains $ScriptsDir) {
  $UpdatedPath = (@($Parts) + $ScriptsDir) -join ";"
  [Environment]::SetEnvironmentVariable("Path", $UpdatedPath, "User")
  Write-Output "added"
}
"""
    output = query_powershell(script, str(scripts_dir))
    if output.strip() == "added":
        print(f"Added {scripts_dir} to the current user's PATH. Open a new PowerShell to use sidecar-deck-agentctl directly.")


def install(args: argparse.Namespace) -> None:
    ensure_windows()
    install_dir = args.install_dir.resolve()
    install_dir.mkdir(parents=True, exist_ok=True)

    source = args.source or current_source()
    create_venv(install_dir)
    install_package(install_dir, source, force_reinstall=args.force_reinstall)
    save_install_source(install_dir, source)

    write_env(
        install_dir / ".env",
        {
            "DASHBOARD_BASE_URL": args.dashboard_url,
            "METRICS_TOKEN": args.metrics_token,
            "PUSH_INTERVAL_SECONDS": args.interval,
            "HOSTNAME": args.hostname,
            "LOG_LEVEL": args.log_level,
        },
    )
    register_task(install_dir, args.task_name, run_elevated=args.run_elevated)
    if not args.no_path:
        add_scripts_to_user_path(install_dir)

    if not args.no_start:
        start(args)

    print(f"Installed Sidecar Deck agent in {install_dir}")
    print(f"Configuration: {install_dir / '.env'}")


def start(args: argparse.Namespace) -> None:
    ensure_windows()
    script = "param($TaskName) Start-ScheduledTask -TaskName $TaskName"
    run_powershell(script, args.task_name)
    print(f"Started {args.task_name}")


def stop(args: argparse.Namespace) -> None:
    ensure_windows()
    script = "param($TaskName) Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue"
    run_powershell(script, args.task_name)
    print(f"Stopped {args.task_name}")


def restart(args: argparse.Namespace) -> None:
    stop(args)
    start(args)


def update(args: argparse.Namespace) -> None:
    ensure_windows()
    install_dir = args.install_dir.resolve()
    if not python_exe(install_dir).exists():
        raise CommandError(f"no agent virtual environment found at {install_dir}")

    source = args.source or load_install_source(install_dir)
    stop(args)
    install_package(install_dir, source, force_reinstall=True)
    save_install_source(install_dir, source)
    register_task(install_dir, args.task_name, run_elevated=args.run_elevated)
    if not args.no_start:
        start(args)
    print(f"Updated Sidecar Deck agent from {source}")


def uninstall(args: argparse.Namespace) -> None:
    ensure_windows()
    stop(args)
    script = "param($TaskName) Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue"
    run_powershell(script, args.task_name)
    print(f"Uninstalled scheduled task {args.task_name}")
    print(f"Agent files were left in {args.install_dir.resolve()}")


def status(args: argparse.Namespace) -> None:
    ensure_windows()
    script = r"""
param($TaskName)
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $Task) {
  Write-Output "not installed"
  exit 0
}
$Info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output "state=$($Task.State)"
Write-Output "lastRunTime=$($Info.LastRunTime)"
Write-Output "lastTaskResult=$($Info.LastTaskResult)"
Write-Output "nextRunTime=$($Info.NextRunTime)"
Write-Output "runLevel=$($Task.Principal.RunLevel)"
$Task.Actions | ForEach-Object {
  Write-Output "execute=$($_.Execute)"
  Write-Output "workingDirectory=$($_.WorkingDirectory)"
}
"""
    print(query_powershell(script, args.task_name))


def run_foreground(args: argparse.Namespace) -> None:
    ensure_windows()
    agent_exe = agent_console_exe(args.install_dir.resolve())
    if not agent_exe.exists():
        raise CommandError(f"agent executable was not found at {agent_exe}")
    subprocess.run([str(agent_exe)], cwd=args.install_dir.resolve(), check=True)


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--install-dir", type=Path, default=default_install_dir(), help="agent installation directory")
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Windows Scheduled Task name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sidecar-deck-agentctl", description="Manage the Sidecar Deck Windows agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install the agent and register the startup task")
    add_common_options(install_parser)
    install_parser.add_argument("--dashboard-url", default="http://homelab.local:8080")
    install_parser.add_argument("--metrics-token", default="change-me")
    install_parser.add_argument("--interval", default="1")
    install_parser.add_argument("--hostname")
    install_parser.add_argument("--log-level", default="INFO")
    install_parser.add_argument("--source", help="pip install source, such as a git URL or local agent directory")
    install_parser.add_argument("--force-reinstall", action="store_true")
    install_parser.add_argument("--run-elevated", action="store_true", help="register the scheduled task with highest privileges")
    install_parser.add_argument("--no-path", action="store_true", help="do not add the agent Scripts directory to user PATH")
    install_parser.add_argument("--no-start", action="store_true", help="install without starting the scheduled task")
    install_parser.set_defaults(func=install)

    for name, func, help_text in [
        ("start", start, "start the scheduled task"),
        ("stop", stop, "stop the scheduled task"),
        ("restart", restart, "restart the scheduled task"),
        ("status", status, "show scheduled task status"),
        ("uninstall", uninstall, "remove the scheduled task"),
        ("run", run_foreground, "run the agent in the foreground for troubleshooting"),
    ]:
        command_parser = subparsers.add_parser(name, help=help_text)
        add_common_options(command_parser)
        command_parser.set_defaults(func=func)

    update_parser = subparsers.add_parser("update", help="upgrade the installed agent package")
    add_common_options(update_parser)
    update_parser.add_argument("--source", help="pip install source; defaults to the source used during install")
    update_parser.add_argument("--run-elevated", action="store_true", help="re-register the scheduled task with highest privileges")
    update_parser.add_argument("--no-start", action="store_true", help="update without starting the scheduled task")
    update_parser.set_defaults(func=update)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
    except CommandError as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
