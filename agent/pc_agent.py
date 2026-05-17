from __future__ import annotations

import logging
import asyncio
import json
import os
import platform
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import psutil
import requests
import websockets
from dotenv import load_dotenv


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sidecar-deck-agent")

DEFAULT_DASHBOARD_BASE_URL = "http://homelab.local:8080"
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL") or os.getenv("DASHBOARD_URL", DEFAULT_DASHBOARD_BASE_URL)
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "change-me")
PUSH_INTERVAL_SECONDS = float(os.getenv("PUSH_INTERVAL_SECONDS", "1"))
HOSTNAME = os.getenv("HOSTNAME") or socket.gethostname()
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
CPU_TEMPERATURE_POLL_SECONDS = float(os.getenv("CPU_TEMPERATURE_POLL_SECONDS", "10"))
LOGITECH_BATTERY_POLL_SECONDS = float(os.getenv("LOGITECH_BATTERY_POLL_SECONDS", "30"))
BLUETOOTH_BATTERY_POLL_SECONDS = float(os.getenv("BLUETOOTH_BATTERY_POLL_SECONDS", "60"))
_cpu_temperature_checked_at = 0.0
_cpu_temperature_cache: float | None = None
_logitech_battery_checked_at = 0.0
_logitech_battery_cache: list[dict[str, Any]] = []
_bluetooth_battery_checked_at = 0.0
_bluetooth_battery_cache: list[dict[str, Any]] = []


def hidden_creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def metrics_url(base_url: str) -> str:
    clean_url = base_url.rstrip("/")
    if clean_url.endswith("/api/metrics"):
        return clean_url
    return f"{clean_url}/api/metrics"


class RateTracker:
    def __init__(self) -> None:
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        self.last_time = time.monotonic()

    def sample(self) -> tuple[dict[str, int], dict[str, int]]:
        now = time.monotonic()
        elapsed = max(0.001, now - self.last_time)
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()

        network = {
            "rxBytesPerSecond": max(0, int((net.bytes_recv - self.last_net.bytes_recv) / elapsed)),
            "txBytesPerSecond": max(0, int((net.bytes_sent - self.last_net.bytes_sent) / elapsed)),
        }
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


def first_temperature() -> float | None:
    global _cpu_temperature_cache, _cpu_temperature_checked_at

    now = time.monotonic()
    if now - _cpu_temperature_checked_at < CPU_TEMPERATURE_POLL_SECONDS:
        return _cpu_temperature_cache
    _cpu_temperature_checked_at = now

    _cpu_temperature_cache = psutil_cpu_temperature() or windows_cpu_temperature()
    return _cpu_temperature_cache


def psutil_cpu_temperature() -> float | None:
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return None

    preferred_keys = ["coretemp", "k10temp", "cpu_thermal", "acpitz"]
    cpu_terms = ("cpu", "package", "core", "tctl", "tdie", "ccd", "soc")
    readings: list[tuple[int, float]] = []

    for key in preferred_keys + [item for item in temps if item not in preferred_keys]:
        for reading in temps.get(key, []):
            current = getattr(reading, "current", None)
            if current is None:
                continue
            try:
                value = float(current)
            except (TypeError, ValueError):
                continue
            if not 0 < value < 130:
                continue

            label = str(getattr(reading, "label", "") or "").lower()
            key_name = key.lower()
            sensor_name = f"{key_name} {label}".strip()
            if not any(term in sensor_name for term in cpu_terms):
                continue

            key_rank = preferred_keys.index(key) if key in preferred_keys else len(preferred_keys)
            term_rank = next((index for index, term in enumerate(cpu_terms) if term in sensor_name), len(cpu_terms))
            readings.append((key_rank * 10 + term_rank, value))

    if not readings:
        return None
    readings.sort(key=lambda item: item[0])
    return readings[0][1]


def windows_cpu_temperature() -> float | None:
    if os.name != "nt":
        return None

    for namespace in ("root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor"):
        value = hardware_monitor_temperature(namespace)
        if value is not None:
            return value

    return acpi_thermal_zone_temperature()


def hardware_monitor_temperature(namespace: str) -> float | None:
    command = (
        "$sensors = Get-CimInstance -Namespace '"
        + namespace
        + "' -ClassName Sensor -ErrorAction SilentlyContinue | "
        + "Where-Object { $_.SensorType -eq 'Temperature' -and "
        + "($_.Name -match 'CPU|Package|Tctl|Tdie|Core' -or $_.Identifier -match '/(amd|intel)cpu/') } | "
        + "Select-Object Name,Value; $sensors | ConvertTo-Json -Compress"
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
    except json.JSONDecodeError:
        return None

    sensors = data if isinstance(data, list) else [data]
    preferred_names = ["package", "tctl", "tdie", "cpu"]
    readings: list[tuple[int, float]] = []
    for sensor in sensors:
        try:
            name = str(sensor.get("Name", "")).lower()
            value = float(sensor["Value"])
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if 0 < value < 130:
            rank = next((index for index, item in enumerate(preferred_names) if item in name), len(preferred_names))
            readings.append((rank, value))

    if not readings:
        return None
    readings.sort(key=lambda item: item[0])
    return readings[0][1]


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


def disk_usage_metrics() -> dict[str, Any]:
    volumes: list[dict[str, Any]] = []
    for partition in psutil.disk_partitions(all=False):
        if os.name == "nt" and "fixed" not in partition.opts.lower():
            continue
        try:
            volume_usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue

        label = partition.mountpoint.rstrip("\\/") or partition.mountpoint
        volumes.append(
            {
                "name": label,
                "mountpoint": partition.mountpoint,
                "usagePercent": float(volume_usage.percent),
                "usedBytes": int(volume_usage.used),
                "freeBytes": int(volume_usage.free),
                "totalBytes": int(volume_usage.total),
            }
        )

    try:
        usage = psutil.disk_usage(os.getenv("DISK_PATH", "C:\\" if os.name == "nt" else "/"))
    except OSError:
        return {"volumes": volumes}
    return {
        "usagePercent": float(usage.percent),
        "usedBytes": int(usage.used),
        "freeBytes": int(usage.free),
        "totalBytes": int(usage.total),
        "volumes": volumes,
    }


def top_memory_processes(total_memory: int, limit: int = 3) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            memory_info = info.get("memory_info")
            rss_bytes = getattr(memory_info, "rss", 0)
            if rss_bytes <= 0:
                continue

            name = info.get("name") or f"pid {info.get('pid')}"
            processes.append(
                {
                    "name": str(name)[:128],
                    "pid": int(info["pid"]),
                    "rssBytes": int(rss_bytes),
                    "usagePercent": round((rss_bytes / total_memory) * 100, 1) if total_memory > 0 else None,
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    processes.sort(key=lambda item: item["rssBytes"], reverse=True)
    return processes[:limit]


def nvidia_gpu_metrics() -> dict[str, Any] | None:
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
        return {
            "name": name,
            "usagePercent": float(usage),
            "temperatureC": float(temperature),
            "memoryUsedBytes": int(float(memory_used_mib) * 1024 * 1024),
            "memoryTotalBytes": int(float(memory_total_mib) * 1024 * 1024),
        }
    except ValueError:
        return None


def logitech_battery_devices() -> list[dict[str, Any]]:
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


def bluetooth_battery_devices() -> list[dict[str, Any]]:
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


async def fetch_logitech_battery_devices() -> list[dict[str, Any]]:
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
        battery_devices: list[dict[str, Any]] = []

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
                {
                    "id": device_id,
                    "name": str(device.get("displayName") or device.get("extendedDisplayName") or device_id)[:96],
                    "batteryPercent": max(0, min(100, battery_percent)),
                    "charging": bool(payload.get("charging")),
                }
            )

        return battery_devices


async def receive_logitech_message(websocket: Any, path: str) -> dict[str, Any]:
    for _ in range(10):
        message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
        if message.get("path") == path:
            return message
    raise TimeoutError(f"logitech websocket did not return {path}")


async def fetch_bluetooth_battery_devices() -> list[dict[str, Any]]:
    from uuid import UUID

    from winrt.windows.devices.bluetooth.genericattributeprofile import GattDeviceService
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.storage.streams import DataReader

    battery_level_uuid = UUID("00002a19-0000-1000-8000-00805f9b34fb")
    device_infos = await DeviceInformation.find_all_async()
    devices: dict[str, dict[str, Any]] = {}

    for device_info in device_infos:
        device_id = str(device_info.id)
        if "0000180f" not in device_id.lower():
            continue

        service = await GattDeviceService.from_id_async(device_id)
        if service is None:
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
            devices[stable_id] = {
                "id": f"bluetooth-{stable_id}",
                "name": str(device_info.name or "Bluetooth device")[:96],
                "batteryPercent": max(0, min(100, battery_percent)),
                "charging": False,
            }

    return list(devices.values())


def collect_metrics(tracker: RateTracker) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    network, disk_rates = tracker.sample()
    cpu_temp = first_temperature()
    cpu_clock = cpu_clock_mhz()
    disk_metrics = disk_usage_metrics()

    payload: dict[str, Any] = {
        "host": HOSTNAME,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cpu": {
            "name": cpu_name(),
            "usagePercent": psutil.cpu_percent(interval=None),
            "perCoreUsagePercent": psutil.cpu_percent(interval=None, percpu=True),
        },
        "memory": {
            "usagePercent": memory.percent,
            "usedBytes": memory.used,
            "totalBytes": memory.total,
            "topProcesses": top_memory_processes(memory.total),
        },
        "network": network,
        "disk": {
            **disk_metrics,
            **disk_rates,
        },
        "uptimeSeconds": max(0, time.time() - psutil.boot_time()),
    }

    if cpu_temp is not None:
        payload["cpu"]["temperatureC"] = cpu_temp
    if cpu_clock is not None:
        payload["cpu"]["clockMhz"] = cpu_clock

    gpu = nvidia_gpu_metrics()
    if gpu is not None:
        payload["gpu"] = gpu

    batteries = logitech_battery_devices() + bluetooth_battery_devices()
    if batteries:
        payload["peripheralBatteries"] = batteries

    return payload


def push_metrics(session: requests.Session, payload: dict[str, Any]) -> None:
    response = session.post(
        metrics_url(DASHBOARD_BASE_URL),
        json=payload,
        headers={"Authorization": f"Bearer {METRICS_TOKEN}"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def main() -> None:
    logger.info(
        "starting agent for host=%s base_url=%s metrics_url=%s interval=%ss",
        HOSTNAME,
        DASHBOARD_BASE_URL,
        metrics_url(DASHBOARD_BASE_URL),
        PUSH_INTERVAL_SECONDS,
    )
    session = requests.Session()
    tracker = RateTracker()
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None, percpu=True)

    while True:
        started = time.monotonic()
        try:
            payload = collect_metrics(tracker)
            push_metrics(session, payload)
            logger.debug("pushed metrics")
        except Exception as exc:
            logger.warning("metrics push failed: %s", exc)

        elapsed = time.monotonic() - started
        time.sleep(max(0.1, PUSH_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
