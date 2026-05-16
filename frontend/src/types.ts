export interface CpuMetrics {
  usagePercent?: number | null;
  temperatureC?: number | null;
  clockMhz?: number | null;
  perCoreUsagePercent?: number[] | null;
}

export interface MemoryMetrics {
  usagePercent?: number | null;
  usedBytes?: number | null;
  totalBytes?: number | null;
}

export interface GpuMetrics {
  name?: string | null;
  usagePercent?: number | null;
  temperatureC?: number | null;
  memoryUsedBytes?: number | null;
  memoryTotalBytes?: number | null;
}

export interface NetworkMetrics {
  rxBytesPerSecond?: number | null;
  txBytesPerSecond?: number | null;
}

export interface DiskMetrics {
  usagePercent?: number | null;
  readBytesPerSecond?: number | null;
  writeBytesPerSecond?: number | null;
}

export interface MetricPayload {
  host: string;
  timestamp?: string | null;
  cpu?: CpuMetrics | null;
  memory?: MemoryMetrics | null;
  gpu?: GpuMetrics | null;
  network?: NetworkMetrics | null;
  disk?: DiskMetrics | null;
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
