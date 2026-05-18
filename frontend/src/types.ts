export interface CpuMetrics {
  name?: string | null;
  usagePercent?: number | null;
  temperatureC?: number | null;
  clockMhz?: number | null;
  perCoreUsagePercent?: number[] | null;
}

export interface MemoryMetrics {
  usagePercent?: number | null;
  usedBytes?: number | null;
  totalBytes?: number | null;
  topProcesses?: ProcessMemoryMetrics[] | null;
}

export interface ProcessMemoryMetrics {
  name: string;
  /** @deprecated Use pids instead. */
  pid?: number | null;
  pids: number[];
  processCount?: number | null;
  rssBytes: number;
  usagePercent?: number | null;
}

export interface GpuMetrics {
  name?: string | null;
  usagePercent?: number | null;
  temperatureC?: number | null;
  memoryUsedBytes?: number | null;
  memoryTotalBytes?: number | null;
}

export interface TemperatureMetrics {
  id: string;
  label: string;
  temperatureC: number;
  source?: string | null;
}

export interface NetworkMetrics {
  rxBytesPerSecond?: number | null;
  txBytesPerSecond?: number | null;
}

export interface DiskMetrics {
  usagePercent?: number | null;
  usedBytes?: number | null;
  freeBytes?: number | null;
  totalBytes?: number | null;
  volumes?: DiskVolumeMetrics[] | null;
  readBytesPerSecond?: number | null;
  writeBytesPerSecond?: number | null;
}

export interface DiskVolumeMetrics {
  name: string;
  mountpoint: string;
  usagePercent?: number | null;
  usedBytes?: number | null;
  freeBytes?: number | null;
  totalBytes?: number | null;
}

export interface PeripheralBatteryMetrics {
  id: string;
  name: string;
  batteryPercent: number;
  charging?: boolean | null;
}

export interface MetricPayload {
  host: string;
  timestamp?: string | null;
  cpu?: CpuMetrics | null;
  memory?: MemoryMetrics | null;
  gpu?: GpuMetrics | null;
  temperatures?: TemperatureMetrics[] | null;
  network?: NetworkMetrics | null;
  disk?: DiskMetrics | null;
  peripheralBatteries?: PeripheralBatteryMetrics[] | null;
  uptimeSeconds?: number | null;
}

export interface StatusEnvelope {
  status: 'waiting' | 'live' | 'stale' | 'offline';
  serverTime: string;
  ageSeconds?: number | null;
  staleAfterSeconds: number;
  offlineAfterSeconds: number;
  latest?: MetricPayload | null;
  history: MetricPayload[];
}
