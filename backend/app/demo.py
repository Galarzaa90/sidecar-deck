from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timezone

from .models import CpuMetrics, DiskMetrics, GpuMetrics, MemoryMetrics, MetricPayload, NetworkMetrics, PeripheralBatteryMetrics
from .state import MetricsState


async def run_demo_metrics(state: MetricsState) -> None:
    tick = 0
    rng = random.Random(4070)
    while True:
        if state.settings.demo_mode and not state.real_metrics_received:
            await state.set_metrics(_make_demo_payload(tick, rng), source="demo")
            tick += 1
        await asyncio.sleep(1)


def _wave(tick: int, period: float, low: float, high: float, phase: float = 0) -> float:
    normalized = (math.sin((tick / period) + phase) + 1) / 2
    return low + normalized * (high - low)


def _make_demo_payload(tick: int, rng: random.Random) -> MetricPayload:
    cpu = min(98, max(4, _wave(tick, 5.5, 22, 72) + rng.uniform(-5, 5)))
    gpu = min(99, max(0, _wave(tick, 6.8, 34, 88, phase=1.8) + rng.uniform(-4, 4)))
    memory = min(96, max(18, _wave(tick, 16, 52, 78, phase=0.6) + rng.uniform(-1.5, 1.5)))
    gpu_mem_total = 12 * 1024**3
    gpu_mem_used = int(gpu_mem_total * min(0.95, max(0.08, (gpu / 100) * 0.78 + 0.12)))
    ram_total = 32 * 1024**3
    ram_used = int(ram_total * memory / 100)
    per_core = [
        min(100, max(1, cpu + rng.uniform(-24, 24) + math.sin((tick + idx) / 3) * 10))
        for idx in range(12)
    ]

    return MetricPayload(
        host="demo-gaming-pc",
        timestamp=datetime.now(timezone.utc),
        cpu=CpuMetrics(
            name="Demo Ryzen 5 5600X",
            usagePercent=round(cpu, 1),
            temperatureC=round(38 + cpu * 0.42 + rng.uniform(-1.5, 1.5), 1),
            clockMhz=round(3600 + cpu * 9),
            perCoreUsagePercent=[round(value, 1) for value in per_core],
        ),
        memory=MemoryMetrics(
            usagePercent=round(memory, 1),
            usedBytes=ram_used,
            totalBytes=ram_total,
            topProcesses=[
                {"name": "chrome.exe", "pid": 8424, "rssBytes": int(ram_total * 0.092), "usagePercent": 9.2},
                {"name": "Code.exe", "pid": 10112, "rssBytes": int(ram_total * 0.061), "usagePercent": 6.1},
                {"name": "python.exe", "pid": 4020, "rssBytes": int(ram_total * 0.034), "usagePercent": 3.4},
            ],
        ),
        gpu=GpuMetrics(
            name="Demo GeForce RTX 4070",
            usagePercent=round(gpu, 1),
            temperatureC=round(40 + gpu * 0.36 + rng.uniform(-1.2, 1.2), 1),
            memoryUsedBytes=gpu_mem_used,
            memoryTotalBytes=gpu_mem_total,
        ),
        network=NetworkMetrics(
            rxBytesPerSecond=int(_wave(tick, 4, 180_000, 4_800_000, phase=2.4)),
            txBytesPerSecond=int(_wave(tick, 4.8, 65_000, 1_250_000, phase=0.8)),
        ),
        disk=DiskMetrics(
            usagePercent=72.0,
            readBytesPerSecond=int(_wave(tick, 7, 0, 2_000_000, phase=2)),
            writeBytesPerSecond=int(_wave(tick, 6.5, 0, 900_000, phase=1)),
        ),
        peripheralBatteries=[
            PeripheralBatteryMetrics(id="demo-keyboard", name="G915 X", batteryPercent=45, charging=False),
            PeripheralBatteryMetrics(id="demo-headset", name="G733", batteryPercent=43, charging=True),
        ],
        uptimeSeconds=86400 * 3 + tick,
    )
