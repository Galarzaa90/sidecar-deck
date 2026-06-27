from __future__ import annotations

import logging
import asyncio
import ctypes
import json
import os
import platform
import re
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import click
import psutil
import requests
import websockets
from dotenv import load_dotenv

from .models import (
    CpuMetrics,
    DiskMetrics,
    DiskVolumeMetrics,
    GpuMetrics,
    MemoryMetrics,
    MetricPayload,
    NetworkMetrics,
    PeripheralBatteryMetrics,
    ProcessCpuMetrics,
    ProcessMemoryMetrics,
    TemperatureMetrics,
)


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sidecar-deck-agent")
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

DEFAULT_DASHBOARD_BASE_URL = "http://homelab.local:8080"
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL") or os.getenv("DASHBOARD_URL", DEFAULT_DASHBOARD_BASE_URL)
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "change-me")
PUSH_INTERVAL_SECONDS = float(os.getenv("PUSH_INTERVAL_SECONDS", "1"))
HOSTNAME = os.getenv("HOSTNAME") or socket.gethostname()
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
CPU_TEMPERATURE_POLL_SECONDS = float(os.getenv("CPU_TEMPERATURE_POLL_SECONDS", "10"))
LIBRE_HARDWARE_MONITOR_API_URL = os.getenv("LIBRE_HARDWARE_MONITOR_API_URL") or os.getenv("LIBRE_HARDWARE_MONITOR_URL", "")
LIBRE_HARDWARE_MONITOR_TIMEOUT_SECONDS = float(os.getenv("LIBRE_HARDWARE_MONITOR_TIMEOUT_SECONDS", "0.75"))
TEMPERATURE_SENSOR_LIMIT = int(os.getenv("TEMPERATURE_SENSOR_LIMIT", "6"))
DIAGNOSTIC_HTTP_HOST = os.getenv("DIAGNOSTIC_HTTP_HOST", "127.0.0.1")
DIAGNOSTIC_HTTP_PORT = int(os.getenv("DIAGNOSTIC_HTTP_PORT", "8765"))
LOGITECH_BATTERY_POLL_SECONDS = float(os.getenv("LOGITECH_BATTERY_POLL_SECONDS", "30"))
BLUETOOTH_BATTERY_POLL_SECONDS = float(os.getenv("BLUETOOTH_BATTERY_POLL_SECONDS", "60"))
XINPUT_BATTERY_POLL_SECONDS = float(os.getenv("XINPUT_BATTERY_POLL_SECONDS", "30"))
_temperature_sensors_checked_at = 0.0
_temperature_sensors_cache: list[TemperatureMetrics] = []
_logitech_battery_checked_at = 0.0
_logitech_battery_cache: list[PeripheralBatteryMetrics] = []
_bluetooth_battery_checked_at = 0.0
_bluetooth_battery_cache: list[PeripheralBatteryMetrics] = []
_xinput_battery_checked_at = 0.0
_xinput_battery_cache: list[PeripheralBatteryMetrics] = []
_latest_payload_lock = threading.Lock()
_latest_payload_json: dict[str, Any] | None = None
IGNORED_TOP_MEMORY_PROCESS_NAMES = {"memcompression"}
IGNORED_TOP_CPU_PROCESS_NAMES = {"idle", "system idle process"}


def hidden_creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def should_ignore_top_memory_process(name: str) -> bool:
    return name.strip().lower() in IGNORED_TOP_MEMORY_PROCESS_NAMES


def should_ignore_top_cpu_process(name: str) -> bool:
    return name.strip().lower() in IGNORED_TOP_CPU_PROCESS_NAMES


def display_process_name(name: str) -> str:
    clean_name = name.strip() or "unknown"
    return re.sub(r"\.exe$", "", clean_name, flags=re.IGNORECASE)[:128]


def metrics_url(base_url: str) -> str:
    clean_url = base_url.rstrip("/")
    if clean_url.endswith("/api/metrics"):
        return clean_url
    return f"{clean_url}/api/metrics"


def record_latest_payload(payload: MetricPayload) -> None:
    global _latest_payload_json
    payload_json = payload.model_dump(mode="json", exclude_none=True)
    with _latest_payload_lock:
        _latest_payload_json = payload_json


def latest_payload_json() -> dict[str, Any] | None:
    with _latest_payload_lock:
        if _latest_payload_json is None:
            return None
        return dict(_latest_payload_json)


class DiagnosticHandler(BaseHTTPRequestHandler):
    server_version = "SidecarDeckAgentDiagnostic/1.0"

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send_diagnostic_page()
            return
        if self.path == "/metrics":
            self.send_metrics_json()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def send_diagnostic_page(self) -> None:
        body = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sidecar Deck Agent Metrics</title>
  <style>
    body { margin: 0; padding: 18px; color: #dfe6f2; background: #10141b; font: 14px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; }
    header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    h1 { margin: 0; font: 700 18px/1.2 system-ui, sans-serif; }
    span { color: #8995a8; font-family: system-ui, sans-serif; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body>
  <header><h1>Sidecar Deck Agent Metrics</h1><span id="status">loading</span></header>
  <pre id="payload"></pre>
  <script>
    async function refresh() {
      const status = document.getElementById('status');
      const payload = document.getElementById('payload');
      try {
        const response = await fetch('/metrics', { cache: 'no-store' });
        const data = await response.json();
        status.textContent = response.ok ? 'live' : 'waiting';
        payload.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        status.textContent = 'unavailable';
        payload.textContent = String(error);
      }
    }
    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_metrics_json(self) -> None:
        payload = latest_payload_json()
        if payload is None:
            status = HTTPStatus.SERVICE_UNAVAILABLE
            payload = {"status": "waiting", "message": "No metrics payload has been collected yet."}
        else:
            status = HTTPStatus.OK

        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("diagnostic http: " + format, *args)


def start_diagnostic_http_server() -> ThreadingHTTPServer | None:
    if DIAGNOSTIC_HTTP_PORT <= 0:
        return None

    try:
        server = ThreadingHTTPServer((DIAGNOSTIC_HTTP_HOST, DIAGNOSTIC_HTTP_PORT), DiagnosticHandler)
    except OSError as exc:
        logger.warning("diagnostic HTTP server failed to start on %s:%s: %s", DIAGNOSTIC_HTTP_HOST, DIAGNOSTIC_HTTP_PORT, exc)
        return None

    thread = threading.Thread(target=server.serve_forever, name="sidecar-deck-agent-diagnostic-http", daemon=True)
    thread.start()
    logger.info("diagnostic HTTP server listening at http://%s:%s", DIAGNOSTIC_HTTP_HOST, DIAGNOSTIC_HTTP_PORT)
    return server


class RateTracker:
    def __init__(self) -> None:
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        self.last_time = time.monotonic()
        self.last_process_cpu: dict[tuple[int, float], float] = {}
        self.last_process_cpu_time = self.last_time

    def sample(self) -> tuple[NetworkMetrics, dict[str, int]]:
        now = time.monotonic()
        elapsed = max(0.001, now - self.last_time)
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()

        network = NetworkMetrics(
            rxBytesPerSecond=max(0, int((net.bytes_recv - self.last_net.bytes_recv) / elapsed)),
            txBytesPerSecond=max(0, int((net.bytes_sent - self.last_net.bytes_sent) / elapsed)),
        )
        if disk and self.last_disk:
            disk_rates = {
                "readBytesPerSecond": max(0, int((disk.read_bytes - self.last_disk.read_bytes) / elapsed)),
                "writeBytesPerSecond": max(0, int((disk.write_bytes - self.last_disk.write_bytes) / elapsed)),
            }
        else:
            disk_rates = {"readBytesPerSecond": 0, "writeBytesPerSecond": 0}

        self.last_net = net
        self.last_disk = disk
        self.last_time = now
        return network, disk_rates

    def process_cpu_percentages(self) -> dict[tuple[int, float], float]:
        now = time.monotonic()
        elapsed = max(0.001, now - self.last_process_cpu_time)
        cpu_count = max(1, psutil.cpu_count() or 1)
        current: dict[tuple[int, float], float] = {}
        percentages: dict[tuple[int, float], float] = {}

        for process in psutil.process_iter(["pid", "cpu_times", "create_time"]):
            try:
                info = process.info
                cpu_times = info.get("cpu_times")
                if cpu_times is None:
                    continue

                key = (int(info["pid"]), float(info.get("create_time") or 0))
                process_cpu_time = float(getattr(cpu_times, "user", 0)) + float(getattr(cpu_times, "system", 0))
                current[key] = process_cpu_time

                previous_cpu_time = self.last_process_cpu.get(key)
                if previous_cpu_time is None:
                    continue

                usage_percent = ((process_cpu_time - previous_cpu_time) / elapsed / cpu_count) * 100
                if usage_percent > 0:
                    percentages[key] = min(100, max(0, usage_percent))
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, TypeError, ValueError):
                continue

        self.last_process_cpu = current
        self.last_process_cpu_time = now
        return percentages


def temperature_sensors() -> list[TemperatureMetrics]:
    global _temperature_sensors_cache, _temperature_sensors_checked_at

    now = time.monotonic()
    if now - _temperature_sensors_checked_at < CPU_TEMPERATURE_POLL_SECONDS:
        return _temperature_sensors_cache
    _temperature_sensors_checked_at = now

    sensors = psutil_temperature_sensors()
    if os.name == "nt":
        sensors.extend(windows_temperature_sensors())
    _temperature_sensors_cache = dedupe_temperature_sensors(sensors)
    return _temperature_sensors_cache


def psutil_temperature_sensors() -> list[TemperatureMetrics]:
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return []

    sensors: list[TemperatureMetrics] = []
    for key, readings in temps.items():
        for index, reading in enumerate(readings):
            current = getattr(reading, "current", None)
            sensor = make_temperature_sensor(
                f"psutil-{key}-{index}",
                str(getattr(reading, "label", "") or key),
                current,
                source="psutil",
            )
            if sensor is not None:
                sensors.append(sensor)
    return sensors


def windows_temperature_sensors() -> list[TemperatureMetrics]:
    if LIBRE_HARDWARE_MONITOR_API_URL:
        return libre_hardware_monitor_api_temperature_sensors()

    sensors: list[TemperatureMetrics] = []
    for namespace in ("root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor"):
        sensors.extend(hardware_monitor_temperature_sensors(namespace))

    acpi_value = acpi_thermal_zone_temperature()
    if acpi_value is not None:
        sensors.append(TemperatureMetrics(id="acpi-thermal-zone", label="ACPI Thermal Zone", temperatureC=acpi_value, source="acpi"))
    return sensors


def libre_hardware_monitor_api_temperature_sensors() -> list[TemperatureMetrics]:
    if not LIBRE_HARDWARE_MONITOR_API_URL:
        return []

    try:
        response = requests.get(LIBRE_HARDWARE_MONITOR_API_URL, timeout=LIBRE_HARDWARE_MONITOR_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.debug("libre hardware monitor API lookup failed: %s", exc)
        return []
    except ValueError as exc:
        logger.debug("libre hardware monitor API returned invalid JSON: %s", exc)
        return []

    return libre_hardware_monitor_temperature_nodes(data)


def libre_hardware_monitor_temperature_nodes(node: Any, path: str = "") -> list[TemperatureMetrics]:
    if not isinstance(node, dict):
        return []

    label = str(node.get("Text") or node.get("Name") or "").strip()
    node_path = f"{path}/{label}" if label else path
    sensors: list[TemperatureMetrics] = []
    value = node.get("RawValue") or node.get("Value")

    if is_temperature_node(node) and value is not None:
        sensor_id = str(node.get("SensorId") or node_path or label or "temperature")
        sensor = make_temperature_sensor(sensor_id, label or node_path or "Temperature", parse_sensor_value(value), source="lhm-api")
        if sensor is not None:
            sensors.append(sensor)

    for child in node.get("Children") or []:
        sensors.extend(libre_hardware_monitor_temperature_nodes(child, node_path))

    return sensors


def is_temperature_node(node: dict[str, Any]) -> bool:
    sensor_type = str(node.get("SensorType") or node.get("Type") or "").lower()
    image_url = str(node.get("ImageURL") or "").lower()
    return sensor_type == "temperature" or "temperature" in image_url


def parse_sensor_value(value: Any) -> Any:
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        return match.group(0) if match else value
    return value


def hardware_monitor_temperature_sensors(namespace: str) -> list[TemperatureMetrics]:
    command = (
        "$sensors = Get-CimInstance -Namespace '"
        + namespace
        + "' -ClassName Sensor -ErrorAction Stop | "
        + "Where-Object { $_.SensorType -eq 'Temperature' } | "
        + "Select-Object Name,Identifier,Value; $sensors | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=False,
            capture_output=True,
            creationflags=hidden_creation_flags(),
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("hardware monitor WMI lookup failed for namespace=%s", namespace)
        return []

    if result.returncode != 0:
        logger.debug("hardware monitor WMI lookup failed for namespace=%s: %s", namespace, result.stderr.strip() or result.stdout.strip())
        return []

    output = result.stdout.strip()
    if not output:
        logger.debug("hardware monitor WMI returned no temperature sensors for namespace=%s", namespace)
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        logger.debug("hardware monitor WMI returned invalid JSON for namespace=%s: %s", namespace, output)
        return []

    sensors: list[TemperatureMetrics] = []
    for index, sensor in enumerate(data if isinstance(data, list) else [data]):
        try:
            sensor_id = str(sensor.get("Identifier") or f"{namespace}-{index}")
            label = str(sensor.get("Name") or sensor_id)
            value = sensor.get("Value")
        except AttributeError:
            continue
        normalized = make_temperature_sensor(sensor_id, label, value, source=namespace.rsplit("\\", 1)[-1])
        if normalized is not None:
            sensors.append(normalized)
    return sensors


def make_temperature_sensor(sensor_id: str, label: str, value: Any, *, source: str | None = None) -> TemperatureMetrics | None:
    try:
        temperature = round(float(value), 1)
    except (TypeError, ValueError):
        return None
    if not 0 < temperature < 130:
        return None

    clean_id = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", sensor_id.strip().lower()).strip("-")[:128]
    clean_label = label.strip()[:96] or clean_id
    if is_fixed_temperature_sensor(clean_id, clean_label):
        return None
    return TemperatureMetrics(id=clean_id or "temperature", label=clean_label, temperatureC=temperature, source=source)


def is_fixed_temperature_sensor(sensor_id: str, label: str) -> bool:
    combined = f"{sensor_id} {label}".lower()
    return any(marker in combined for marker in ("critical", "warning", "threshold", "limit"))


def dedupe_temperature_sensors(sensors: list[TemperatureMetrics]) -> list[TemperatureMetrics]:
    deduped: list[TemperatureMetrics] = []
    seen: set[str] = set()
    for sensor in sensors:
        sensor_id = sensor.id
        if sensor_id in seen:
            continue
        seen.add(sensor_id)
        deduped.append(sensor)
    return deduped


def relevant_temperature_sensors(sensors: list[TemperatureMetrics]) -> list[TemperatureMetrics]:
    return [sensor for sensor in dedupe_temperature_sensors(sensors) if temperature_category(sensor) is not None]


def prioritized_temperature_sensors(sensors: list[TemperatureMetrics], limit: int = TEMPERATURE_SENSOR_LIMIT) -> list[TemperatureMetrics]:
    relevant = relevant_temperature_sensors(sensors)
    if limit <= 0 or len(relevant) <= limit:
        return relevant

    selected: list[TemperatureMetrics] = []
    for category in ("cpu", "gpu-core", "gpu-hotspot", "gpu-memory", "storage"):
        candidate = best_temperature_sensor(relevant, category)
        if candidate is not None and candidate not in selected:
            selected.append(candidate)

    remaining = [sensor for sensor in relevant if sensor not in selected]
    remaining.sort(key=lambda sensor: sensor.temperatureC, reverse=True)
    return (selected + remaining)[:limit]


def best_temperature_sensor(sensors: list[TemperatureMetrics], category: str) -> TemperatureMetrics | None:
    candidates = [sensor for sensor in sensors if temperature_category(sensor) == category]
    if not candidates:
        return None
    candidates.sort(key=lambda sensor: sensor.temperatureC, reverse=True)
    return candidates[0]


def temperature_category(sensor: TemperatureMetrics) -> str | None:
    label = sensor.label.lower()
    sensor_id = sensor.id.lower()
    combined = f"{sensor_id} {label}"

    if "tctl" in combined or "tdie" in combined or "cpu package" in combined or "core temperature" in combined:
        return "cpu"
    if "gpu-core" in combined or "gpu core" in combined:
        return "gpu-core"
    if "hot spot" in combined or "hotspot" in combined:
        return "gpu-hotspot"
    if "memory junction" in combined:
        return "gpu-memory"
    if "composite" in combined:
        return "storage"
    if "hdd-" in sensor_id or "nvme-" in sensor_id or "drive" in label or "temperature" == label:
        return "storage"
    return None


def acpi_thermal_zone_temperature() -> float | None:
    command = (
        "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
        "-ErrorAction SilentlyContinue | Select-Object -First 1 CurrentTemperature | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=False,
            capture_output=True,
            creationflags=hidden_creation_flags(),
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    output = result.stdout.strip()
    if not output:
        return None

    try:
        data = json.loads(output)
        raw_value = float(data["CurrentTemperature"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None

    celsius = (raw_value / 10) - 273.15
    return celsius if 0 < celsius < 130 else None


def cpu_clock_mhz() -> float | None:
    try:
        frequency = psutil.cpu_freq()
    except (AttributeError, OSError):
        return None
    if frequency is None or frequency.current <= 0:
        return None
    return float(frequency.current)


def cpu_name() -> str | None:
    name = windows_cpu_name() if os.name == "nt" else None
    if not name:
        name = platform.processor().strip()
    return name[:128] if name else None


def windows_cpu_name() -> str | None:
    command = "Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=False,
            capture_output=True,
            creationflags=hidden_creation_flags(),
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    name = result.stdout.strip()
    return name or None


def disk_usage_metrics() -> DiskMetrics:
    volumes: list[DiskVolumeMetrics] = []
    for partition in psutil.disk_partitions(all=False):
        if os.name == "nt" and "fixed" not in partition.opts.lower():
            continue
        try:
            volume_usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue

        label = partition.mountpoint.rstrip("\\/") or partition.mountpoint
        volumes.append(
            DiskVolumeMetrics(
                name=label,
                mountpoint=partition.mountpoint,
                usagePercent=float(volume_usage.percent),
                usedBytes=int(volume_usage.used),
                freeBytes=int(volume_usage.free),
                totalBytes=int(volume_usage.total),
            )
        )

    try:
        usage = psutil.disk_usage(os.getenv("DISK_PATH", "C:\\" if os.name == "nt" else "/"))
    except OSError:
        return DiskMetrics(volumes=volumes)
    return DiskMetrics(
        usagePercent=float(usage.percent),
        usedBytes=int(usage.used),
        freeBytes=int(usage.free),
        totalBytes=int(usage.total),
        volumes=volumes,
    )


def top_memory_processes(total_memory: int, limit: int = 10) -> list[ProcessMemoryMetrics]:
    grouped: dict[str, dict[str, Any]] = {}
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            memory_info = info.get("memory_info")
            rss_bytes = getattr(memory_info, "rss", 0)
            if rss_bytes <= 0:
                continue

            raw_name = str(info.get("name") or f"pid {info.get('pid')}")
            name = display_process_name(raw_name)
            if should_ignore_top_memory_process(raw_name) or should_ignore_top_memory_process(name):
                continue

            key = name.casefold()
            group = grouped.setdefault(key, {"name": name, "pids": [], "rssBytes": 0})
            group["pids"].append(int(info["pid"]))
            group["rssBytes"] += int(rss_bytes)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    processes = [
        ProcessMemoryMetrics(
            name=str(group["name"]),
            pids=sorted(group["pids"]),
            processCount=len(group["pids"]),
            rssBytes=int(group["rssBytes"]),
            usagePercent=round((int(group["rssBytes"]) / total_memory) * 100, 1) if total_memory > 0 else None,
        )
        for group in grouped.values()
    ]
    processes.sort(key=lambda item: item.rssBytes, reverse=True)
    return processes[:limit]


def top_cpu_processes(tracker: RateTracker, limit: int = 10) -> list[ProcessCpuMetrics]:
    cpu_percentages = tracker.process_cpu_percentages()
    if not cpu_percentages:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            info = process.info
            key = (int(info["pid"]), float(info.get("create_time") or 0))
            usage_percent = cpu_percentages.get(key)
            if usage_percent is None or usage_percent <= 0:
                continue

            raw_name = str(info.get("name") or f"pid {info.get('pid')}")
            name = display_process_name(raw_name)
            if (
                should_ignore_top_memory_process(raw_name)
                or should_ignore_top_memory_process(name)
                or should_ignore_top_cpu_process(raw_name)
                or should_ignore_top_cpu_process(name)
            ):
                continue

            group_key = name.casefold()
            group = grouped.setdefault(group_key, {"name": name, "pids": [], "usagePercent": 0.0})
            group["pids"].append(int(info["pid"]))
            group["usagePercent"] += float(usage_percent)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, TypeError, ValueError):
            continue

    processes = [
        ProcessCpuMetrics(
            name=str(group["name"]),
            pids=sorted(group["pids"]),
            processCount=len(group["pids"]),
            usagePercent=round(min(100, float(group["usagePercent"])), 1),
        )
        for group in grouped.values()
    ]
    processes.sort(key=lambda item: item.usagePercent, reverse=True)
    return processes[:limit]


def nvidia_gpu_metrics() -> GpuMetrics | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            creationflags=hidden_creation_flags(),
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    parts = [part.strip() for part in first_line.split(",")]
    if len(parts) != 5:
        return None

    try:
        name, usage, temperature, memory_used_mib, memory_total_mib = parts
        return GpuMetrics(
            name=name,
            usagePercent=float(usage),
            temperatureC=float(temperature),
            memoryUsedBytes=int(float(memory_used_mib) * 1024 * 1024),
            memoryTotalBytes=int(float(memory_total_mib) * 1024 * 1024),
        )
    except ValueError:
        return None


def logitech_battery_devices() -> list[PeripheralBatteryMetrics]:
    global _logitech_battery_cache, _logitech_battery_checked_at

    now = time.monotonic()
    if now - _logitech_battery_checked_at < LOGITECH_BATTERY_POLL_SECONDS:
        return _logitech_battery_cache
    _logitech_battery_checked_at = now

    try:
        _logitech_battery_cache = asyncio.run(fetch_logitech_battery_devices())
    except Exception as exc:
        logger.debug("logitech battery lookup failed: %s", exc)
        _logitech_battery_cache = []
    return _logitech_battery_cache


def bluetooth_battery_devices() -> list[PeripheralBatteryMetrics]:
    global _bluetooth_battery_cache, _bluetooth_battery_checked_at

    if os.name != "nt":
        return []

    now = time.monotonic()
    if now - _bluetooth_battery_checked_at < BLUETOOTH_BATTERY_POLL_SECONDS:
        return _bluetooth_battery_cache
    _bluetooth_battery_checked_at = now

    try:
        _bluetooth_battery_cache = asyncio.run(fetch_bluetooth_battery_devices())
    except Exception as exc:
        logger.debug("bluetooth battery lookup failed: %s", exc)
        _bluetooth_battery_cache = []
    return _bluetooth_battery_cache


def xinput_battery_devices() -> list[PeripheralBatteryMetrics]:
    global _xinput_battery_cache, _xinput_battery_checked_at

    if os.name != "nt":
        return []

    now = time.monotonic()
    if now - _xinput_battery_checked_at < XINPUT_BATTERY_POLL_SECONDS:
        return _xinput_battery_cache
    _xinput_battery_checked_at = now

    try:
        _xinput_battery_cache = fetch_xinput_battery_devices()
    except Exception as exc:
        logger.debug("xinput battery lookup failed: %s", exc)
        _xinput_battery_cache = []
    return _xinput_battery_cache


async def fetch_logitech_battery_devices() -> list[PeripheralBatteryMetrics]:
    headers = {
        "Origin": "file://",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
        "Sec-WebSocket-Protocol": "json",
    }
    async with websockets.connect("ws://127.0.0.1:9010", additional_headers=headers, subprotocols=["json"]) as websocket:
        await websocket.send(json.dumps({"msgId": "", "verb": "GET", "path": "/devices/list"}))
        devices_message = await receive_logitech_message(websocket, "/devices/list")
        devices = devices_message.get("payload", {}).get("deviceInfos", [])
        battery_devices: list[PeripheralBatteryMetrics] = []

        for device in devices:
            if not device.get("capabilities", {}).get("hasBatteryStatus"):
                continue

            device_id = str(device.get("id", ""))
            if not device_id:
                continue

            path = f"/battery/{device_id}/state"
            await websocket.send(json.dumps({"msgId": "", "verb": "GET", "path": path}))
            battery_message = await receive_logitech_message(websocket, path)
            payload = battery_message.get("payload", {})
            percentage = payload.get("percentage")
            try:
                battery_percent = round(float(percentage))
            except (TypeError, ValueError):
                continue

            battery_devices.append(
                PeripheralBatteryMetrics(
                    id=device_id,
                    name=str(device.get("displayName") or device.get("extendedDisplayName") or device_id)[:96],
                    batteryPercent=max(0, min(100, battery_percent)),
                    charging=bool(payload.get("charging")),
                    source="logitech",
                )
            )

        return battery_devices


async def receive_logitech_message(websocket: Any, path: str) -> dict[str, Any]:
    for _ in range(10):
        message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
        if message.get("path") == path:
            return message
    raise TimeoutError(f"logitech websocket did not return {path}")


async def fetch_bluetooth_battery_devices() -> list[PeripheralBatteryMetrics]:
    from uuid import UUID

    from winrt.windows.devices.bluetooth.genericattributeprofile import GattDeviceService, GattSessionStatus
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.storage.streams import DataReader

    battery_level_uuid = UUID("00002a19-0000-1000-8000-00805f9b34fb")
    device_infos = await DeviceInformation.find_all_async()
    devices: dict[str, PeripheralBatteryMetrics] = {}

    for device_info in device_infos:
        device_id = str(device_info.id)
        if "0000180f" not in device_id.lower():
            continue

        service = await GattDeviceService.from_id_async(device_id)
        if service is None:
            continue
        if service.session.session_status != GattSessionStatus.ACTIVE:
            logger.debug("bluetooth battery skipped inactive session: name=%s status=%s", device_info.name, service.session.session_status)
            continue

        result = await service.get_characteristics_for_uuid_async(battery_level_uuid)
        for characteristic in result.characteristics:
            value_result = await characteristic.read_value_async()
            reader = DataReader.from_buffer(value_result.value)
            if reader.unconsumed_buffer_length < 1:
                continue

            battery_percent = int(reader.read_byte())
            address_match = re.search(r"_([0-9a-fA-F]{12})#", device_id)
            address_candidates = [
                item.lower()
                for item in re.findall(r"(?<![0-9a-fA-F])([0-9a-fA-F]{12})(?![0-9a-fA-F])", device_id)
                if item.lower() != "00805f9b34fb"
            ]
            stable_id = address_match.group(1).lower() if address_match else address_candidates[-1] if address_candidates else device_id
            devices[stable_id] = PeripheralBatteryMetrics(
                id=f"bluetooth-{stable_id}",
                name=str(device_info.name or "Bluetooth device")[:96],
                batteryPercent=max(0, min(100, battery_percent)),
                charging=False,
                source="bluetooth",
            )

    return list(devices.values())


def fetch_xinput_battery_devices() -> list[PeripheralBatteryMetrics]:
    xinput = load_xinput()
    if xinput is None:
        return []

    class XInputBatteryInformation(ctypes.Structure):
        _fields_ = [
            ("battery_type", ctypes.c_ubyte),
            ("battery_level", ctypes.c_ubyte),
        ]

    get_battery_information = xinput.XInputGetBatteryInformation
    get_battery_information.argtypes = [ctypes.c_uint, ctypes.c_ubyte, ctypes.POINTER(XInputBatteryInformation)]
    get_battery_information.restype = ctypes.c_uint

    battery_type_disconnected = 0x00
    battery_type_wired = 0x01
    battery_type_unknown = 0xFF
    battery_level_to_percent = {
        0x00: 0,
        0x01: 25,
        0x02: 60,
        0x03: 100,
    }
    devices: list[PeripheralBatteryMetrics] = []

    for user_index in range(4):
        battery = XInputBatteryInformation()
        result = get_battery_information(user_index, 0, ctypes.byref(battery))
        if result != 0 or battery.battery_type == battery_type_disconnected:
            continue

        if battery.battery_type == battery_type_wired:
            devices.append(
                PeripheralBatteryMetrics(
                    id=f"xinput-controller-{user_index + 1}",
                    name=f"Xbox Controller {user_index + 1}",
                    batteryPercent=100,
                    charging=True,
                    source="xinput",
                )
            )
            continue

        battery_percent = battery_level_to_percent.get(int(battery.battery_level))
        if battery_percent is None and battery.battery_type == battery_type_unknown:
            continue
        if battery_percent is None:
            battery_percent = 0

        devices.append(
            PeripheralBatteryMetrics(
                id=f"xinput-controller-{user_index + 1}",
                name=f"Xbox Controller {user_index + 1}",
                batteryPercent=battery_percent,
                charging=False,
                source="xinput",
            )
        )

    return devices


def dedupe_peripheral_batteries(devices: list[PeripheralBatteryMetrics]) -> list[PeripheralBatteryMetrics]:
    deduped: list[PeripheralBatteryMetrics] = []
    seen: set[str] = set()
    for device in devices:
        keys = {device.id.casefold()}
        name_key = re.sub(r"\s+", " ", device.name.strip().casefold())
        if name_key:
            keys.add(f"name:{name_key}")
        if seen.intersection(keys):
            continue
        seen.update(keys)
        deduped.append(device)
    return deduped


def log_peripheral_batteries(devices: list[PeripheralBatteryMetrics]) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return

    if not devices:
        logger.debug("peripheral batteries: none detected")
        return

    summary = ", ".join(
        f"{device.name}={device.batteryPercent:g}%"
        f"{' charging' if device.charging else ''}"
        f"{f' source={device.source}' if device.source else ''}"
        for device in devices
    )
    logger.debug("peripheral batteries: %s", summary)


def load_xinput() -> Any | None:
    for dll_name in ("xinput1_4.dll", "xinput9_1_0.dll", "xinput1_3.dll"):
        try:
            return ctypes.WinDLL(dll_name)
        except OSError:
            continue
    return None


def collect_metrics(tracker: RateTracker) -> MetricPayload:
    memory = psutil.virtual_memory()
    network, disk_rates = tracker.sample()
    thermal_sensors = temperature_sensors()
    cpu_clock = cpu_clock_mhz()
    disk_metrics = disk_usage_metrics()

    cpu = CpuMetrics(
        name=cpu_name(),
        usagePercent=psutil.cpu_percent(interval=None),
        clockMhz=cpu_clock,
        perCoreUsagePercent=psutil.cpu_percent(interval=None, percpu=True),
        topProcesses=top_cpu_processes(tracker),
    )
    disk = disk_metrics.model_copy(update=disk_rates)

    gpu = nvidia_gpu_metrics()
    if gpu is not None:
        gpu_sensor = make_temperature_sensor("nvidia-gpu", "GPU Core", gpu.temperatureC, source="nvidia-smi")
        if gpu_sensor is not None:
            thermal_sensors.append(gpu_sensor)

    batteries = dedupe_peripheral_batteries(xinput_battery_devices() + logitech_battery_devices() + bluetooth_battery_devices())
    log_peripheral_batteries(batteries)

    return MetricPayload(
        host=HOSTNAME,
        timestamp=datetime.now(timezone.utc),
        cpu=cpu,
        memory=MemoryMetrics(
            usagePercent=memory.percent,
            usedBytes=memory.used,
            totalBytes=memory.total,
            topProcesses=top_memory_processes(memory.total),
        ),
        network=network,
        disk=disk,
        gpu=gpu,
        temperatures=prioritized_temperature_sensors(thermal_sensors) or None,
        peripheralBatteries=batteries or None,
        uptimeSeconds=max(0, time.time() - psutil.boot_time()),
    )


def push_metrics(session: requests.Session, payload: MetricPayload) -> None:
    response = session.post(
        metrics_url(DASHBOARD_BASE_URL),
        json=payload.model_dump(mode="json", exclude_none=True),
        headers={"Authorization": f"Bearer {METRICS_TOKEN}"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


AREA_ALIASES = {
    "all": "all",
    "battery": "battery",
    "batteries": "battery",
    "cpu": "cpu",
    "cpus": "cpu",
    "processor": "cpu",
    "thermal": "temperatures",
    "thermals": "temperatures",
    "temperature": "temperatures",
    "temperatures": "temperatures",
    "gpu": "gpu",
    "disk": "disk",
}


def run_agent() -> None:
    logger.info(
        "starting agent for host=%s base_url=%s metrics_url=%s interval=%ss",
        HOSTNAME,
        DASHBOARD_BASE_URL,
        metrics_url(DASHBOARD_BASE_URL),
        PUSH_INTERVAL_SECONDS,
    )
    start_diagnostic_http_server()
    session = requests.Session()
    tracker = RateTracker()
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None, percpu=True)

    while True:
        started = time.monotonic()
        try:
            payload = collect_metrics(tracker)
            record_latest_payload(payload)
            push_metrics(session, payload)
            logger.debug("pushed metrics")
        except Exception as exc:
            logger.warning("metrics push failed: %s", exc)

        elapsed = time.monotonic() - started
        time.sleep(max(0.1, PUSH_INTERVAL_SECONDS - elapsed))


def normalize_cli_area(area: str) -> str:
    normalized = AREA_ALIASES.get(area.strip().lower())
    if normalized is None:
        allowed = ", ".join(sorted(AREA_ALIASES))
        raise click.BadParameter(f"unknown area {area!r}; expected one of: {allowed}")
    return normalized


def print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))


def quiet_probe_logging() -> None:
    logger.setLevel(logging.WARNING)


def models_json(items: list[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json", exclude_none=True) for item in items]


def collect_batteries_once() -> list[PeripheralBatteryMetrics]:
    return dedupe_peripheral_batteries(xinput_battery_devices() + logitech_battery_devices() + bluetooth_battery_devices())


def debug_battery_sources() -> dict[str, Any]:
    sources = [
        ("xinput", fetch_xinput_battery_devices),
        ("logitech", lambda: asyncio.run(fetch_logitech_battery_devices())),
        ("bluetooth", lambda: asyncio.run(fetch_bluetooth_battery_devices())),
    ]
    source_results: list[dict[str, Any]] = []
    combined: list[PeripheralBatteryMetrics] = []

    for source, callback in sources:
        started = time.perf_counter()
        try:
            devices = callback()
            combined.extend(devices)
            source_results.append({"source": source, "elapsedSeconds": round(time.perf_counter() - started, 3), "devices": models_json(devices)})
        except Exception as exc:
            source_results.append({"source": source, "elapsedSeconds": round(time.perf_counter() - started, 3), "devices": [], "error": str(exc)})

    return {
        "sources": source_results,
        "combined": models_json(dedupe_peripheral_batteries(combined)),
    }


def collect_cpu_once() -> CpuMetrics:
    tracker = RateTracker()
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None, percpu=True)
    tracker.process_cpu_percentages()
    time.sleep(max(0.1, min(2.0, PUSH_INTERVAL_SECONDS)))

    return CpuMetrics(
        name=cpu_name(),
        usagePercent=psutil.cpu_percent(interval=None),
        clockMhz=cpu_clock_mhz(),
        perCoreUsagePercent=psutil.cpu_percent(interval=None, percpu=True),
        topProcesses=top_cpu_processes(tracker),
    )


def one_shot_payload(area: str) -> Any:
    normalized_area = normalize_cli_area(area)
    if normalized_area == "all":
        tracker = RateTracker()
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        return collect_metrics(tracker).model_dump(mode="json", exclude_none=True)
    if normalized_area == "cpu":
        return {"cpu": collect_cpu_once().model_dump(mode="json", exclude_none=True)}
    if normalized_area == "battery":
        return {"peripheralBatteries": models_json(collect_batteries_once())}
    if normalized_area == "temperatures":
        sensors = prioritized_temperature_sensors(temperature_sensors())
        return {"temperatures": models_json(sensors)}
    if normalized_area == "gpu":
        gpu = nvidia_gpu_metrics()
        return {"gpu": gpu.model_dump(mode="json", exclude_none=True) if gpu is not None else None}
    if normalized_area == "disk":
        return {"disk": disk_usage_metrics().model_dump(mode="json", exclude_none=True)}
    raise click.BadParameter(f"unsupported area {area!r}")


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Collect and push Sidecar Deck PC metrics."""
    if ctx.invoked_subcommand is None:
        run_agent()


@main.command("run")
def run_command() -> None:
    """Run the continuous metrics agent."""
    run_agent()


@main.command("one-shot")
@click.argument("area", required=False, default="all")
def one_shot_command(area: str) -> None:
    """Collect one payload or subarea and print JSON."""
    quiet_probe_logging()
    print_json(one_shot_payload(area))


@main.command("debug")
@click.argument("area", required=False, default="all")
def debug_command(area: str) -> None:
    """Print focused debugging details for a subarea."""
    quiet_probe_logging()
    normalized_area = normalize_cli_area(area)
    if normalized_area == "battery":
        print_json(debug_battery_sources())
        return
    print_json(one_shot_payload(normalized_area))


if __name__ == "__main__":
    main()
