from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CpuMetrics(FlexibleModel):
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


class ProcessCpuMetrics(FlexibleModel):
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


class MemoryMetrics(FlexibleModel):
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    usedBytes: int | None = Field(default=None, ge=0)
    totalBytes: int | None = Field(default=None, ge=0)
    topProcesses: list["ProcessMemoryMetrics"] | None = None


class ProcessMemoryMetrics(FlexibleModel):
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


class GpuMetrics(FlexibleModel):
    name: str | None = None
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    temperatureC: float | None = None
    memoryUsedBytes: int | None = Field(default=None, ge=0)
    memoryTotalBytes: int | None = Field(default=None, ge=0)


class TemperatureMetrics(FlexibleModel):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=96)
    temperatureC: float = Field(ge=0, le=130)
    source: str | None = Field(default=None, max_length=64)


class NetworkMetrics(FlexibleModel):
    rxBytesPerSecond: int | None = Field(default=None, ge=0)
    txBytesPerSecond: int | None = Field(default=None, ge=0)


class DiskMetrics(FlexibleModel):
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    usedBytes: int | None = Field(default=None, ge=0)
    freeBytes: int | None = Field(default=None, ge=0)
    totalBytes: int | None = Field(default=None, ge=0)
    volumes: list["DiskVolumeMetrics"] | None = None
    readBytesPerSecond: int | None = Field(default=None, ge=0)
    writeBytesPerSecond: int | None = Field(default=None, ge=0)


class DiskVolumeMetrics(FlexibleModel):
    name: str = Field(min_length=1, max_length=32)
    mountpoint: str = Field(min_length=1, max_length=256)
    usagePercent: float | None = Field(default=None, ge=0, le=100)
    usedBytes: int | None = Field(default=None, ge=0)
    freeBytes: int | None = Field(default=None, ge=0)
    totalBytes: int | None = Field(default=None, ge=0)


class PeripheralBatteryMetrics(FlexibleModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=96)
    batteryPercent: float = Field(ge=0, le=100)
    charging: bool = False
    source: str | None = Field(default=None, max_length=64)


class MetricPayload(FlexibleModel):
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

    def with_timestamp(self) -> "MetricPayload":
        if self.timestamp is not None:
            return self
        data = self.model_dump()
        data["timestamp"] = datetime.now(timezone.utc)
        return MetricPayload.model_validate(data)


class StatusEnvelope(FlexibleModel):
    status: str
    serverTime: datetime
    ageSeconds: float | None
    staleAfterSeconds: int
    offlineAfterSeconds: int
    latest: MetricPayload | None
    history: list[MetricPayload]


class CurrentWeather(FlexibleModel):
    temperatureC: float | None = None
    apparentTemperatureC: float | None = None
    weatherCode: int | None = None
    condition: str
    windKph: float | None = Field(default=None, ge=0)


class ForecastDay(FlexibleModel):
    date: str
    condition: str
    weatherCode: int | None = None
    temperatureMinC: float | None = None
    temperatureMaxC: float | None = None
    precipitationChancePercent: int | None = Field(default=None, ge=0, le=100)


class WeatherEnvelope(FlexibleModel):
    status: str
    locationLabel: str | None = None
    updatedAt: datetime
    current: CurrentWeather | None = None
    forecast: list[ForecastDay] = Field(default_factory=list)
