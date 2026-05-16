from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import psutil
import requests
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
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return None

    preferred = ["coretemp", "k10temp", "cpu_thermal", "acpitz"]
    for key in preferred + list(temps):
        readings = temps.get(key)
        if readings:
            current = readings[0].current
            if current is not None:
                return float(current)
    return None


def disk_usage_percent() -> float | None:
    try:
        return float(psutil.disk_usage(os.getenv("DISK_PATH", "C:\\" if os.name == "nt" else "/")).percent)
    except OSError:
        return None


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


def collect_metrics(tracker: RateTracker) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    network, disk_rates = tracker.sample()
    cpu_temp = first_temperature()
    disk_percent = disk_usage_percent()

    payload: dict[str, Any] = {
        "host": HOSTNAME,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cpu": {
            "usagePercent": psutil.cpu_percent(interval=None),
            "perCoreUsagePercent": psutil.cpu_percent(interval=None, percpu=True),
        },
        "memory": {
            "usagePercent": memory.percent,
            "usedBytes": memory.used,
            "totalBytes": memory.total,
        },
        "network": network,
        "disk": {
            "usagePercent": disk_percent,
            **disk_rates,
        },
        "uptimeSeconds": max(0, time.time() - psutil.boot_time()),
    }

    if cpu_temp is not None:
        payload["cpu"]["temperatureC"] = cpu_temp

    gpu = nvidia_gpu_metrics()
    if gpu is not None:
        payload["gpu"] = gpu

    # LibreHardwareMonitor/OpenHardwareMonitor can be added here later without
    # changing the backend contract.
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
