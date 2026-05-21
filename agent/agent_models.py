from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CpuMetrics(AgentModel):
    name: str | None = Field(default=None, max_length=128)
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    temperatureC: float | None = None
    clockMhz: float | None = Field(default=None, ge=0)
    perCoreUsagePercent: list[float] | None = None
    topProcesses: list["ProcessCpuMetrics"] | None = None

    @field_validator("perCoreUsagePercent")
    @classmethod
    def validate_per_core(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        for item in value:
            if item < 0 or item > 100:
                raise ValueError("per-core CPU usage must be between 0 and 100")
        return value


class ProcessCpuMetrics(AgentModel):
    name: str = Field(min_length=1, max_length=128)
    pid: int | None = Field(default=None, ge=0, deprecated=True)
    pids: list[int] = Field(min_length=1)
    processCount: int = Field(default=1, ge=1)
    usagePercent: float = Field(ge=0, le=100)

    @field_validator("pids")
    @classmethod
    def validate_pids(cls, value: list[int]) -> list[int]:
        for pid in value:
            if pid < 0:
                raise ValueError("process IDs must be greater than or equal to 0")
        return value


class ProcessMemoryMetrics(AgentModel):
    name: str = Field(min_length=1, max_length=128)
    pid: int | None = Field(default=None, ge=0, deprecated=True)
    pids: list[int] = Field(min_length=1)
    processCount: int = Field(default=1, ge=1)
    rssBytes: int = Field(ge=0)
    usagePercent: float | None = Field(default=None, ge=0, le=100)

    @field_validator("pids")
    @classmethod
    def validate_pids(cls, value: list[int]) -> list[int]:
        for pid in value:
            if pid < 0:
                raise ValueError("process IDs must be greater than or equal to 0")
        return value


class MemoryMetrics(AgentModel):
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    usedBytes: int | None = Field(default=None, ge=0)
    totalBytes: int | None = Field(default=None, ge=0)
    topProcesses: list[ProcessMemoryMetrics] | None = None


class GpuMetrics(AgentModel):
    name: str | None = None
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    temperatureC: float | None = None
    memoryUsedBytes: int | None = Field(default=None, ge=0)
    memoryTotalBytes: int | None = Field(default=None, ge=0)


class TemperatureMetrics(AgentModel):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=96)
    temperatureC: float = Field(ge=0, le=130)
    source: str | None = Field(default=None, max_length=64)


class NetworkMetrics(AgentModel):
    rxBytesPerSecond: int | None = Field(default=None, ge=0)
    txBytesPerSecond: int | None = Field(default=None, ge=0)


class DiskVolumeMetrics(AgentModel):
    name: str = Field(min_length=1, max_length=32)
    mountpoint: str = Field(min_length=1, max_length=256)
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    usedBytes: int | None = Field(default=None, ge=0)
    freeBytes: int | None = Field(default=None, ge=0)
    totalBytes: int | None = Field(default=None, ge=0)


class DiskMetrics(AgentModel):
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    usedBytes: int | None = Field(default=None, ge=0)
    freeBytes: int | None = Field(default=None, ge=0)
    totalBytes: int | None = Field(default=None, ge=0)
    volumes: list[DiskVolumeMetrics] | None = None
    readBytesPerSecond: int | None = Field(default=None, ge=0)
    writeBytesPerSecond: int | None = Field(default=None, ge=0)


class PeripheralBatteryMetrics(AgentModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=96)
    batteryPercent: float = Field(ge=0, le=100)
    charging: bool = False
    source: str | None = Field(default=None, max_length=64)


class MetricPayload(AgentModel):
    host: str = Field(default="unknown", min_length=1, max_length=128)
    timestamp: datetime | None = None
    cpu: CpuMetrics | None = None
    memory: MemoryMetrics | None = None
    gpu: GpuMetrics | None = None
    temperatures: list[TemperatureMetrics] | None = None
    network: NetworkMetrics | None = None
    disk: DiskMetrics | None = None
    peripheralBatteries: list[PeripheralBatteryMetrics] | None = None
    uptimeSeconds: float | None = Field(default=None, ge=0)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: Any) -> Any:
        if isinstance(value, str) and value.endswith("Z"):
            return f"{value[:-1]}+00:00"
        return value
