import { Activity, ArrowDown, ArrowUp, BatteryCharging, BatteryFull, Cpu, Gauge, HardDrive, MemoryStick, Network, Thermometer, Wifi, WifiOff } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { age, bytes, clock, gbPair, number1, percent, throughput } from './format';
import { RankedMeterList } from './RankedMeterList';
import { Sparkline } from './Sparkline';
import type { MetricPayload, StatusEnvelope, TemperatureMetrics } from './types';

interface CompactPanel {
  key: string;
  priority: number;
  content: ReactNode;
}

const emptyEnvelope: StatusEnvelope = {
  status: 'waiting',
  serverTime: new Date().toISOString(),
  ageSeconds: null,
  staleAfterSeconds: 5,
  offlineAfterSeconds: 15,
  latest: null,
  history: [],
};

function wsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

function useMetrics() {
  const [envelope, setEnvelope] = useState<StatusEnvelope>(emptyEnvelope);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let stopped = false;

    const connect = () => {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => setEnvelope(JSON.parse(event.data));
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) retry = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      if (retry) window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return { envelope, connected };
}

function series(history: MetricPayload[], selector: (item: MetricPayload) => number | null | undefined) {
  return history.slice(-120).map(selector);
}

function maxTemp(metric?: MetricPayload | null): number | null {
  const values = temperatureItems(metric).map((item) => item.temperatureC);
  return values.length ? Math.max(...values) : null;
}

function temperatureItems(metric?: MetricPayload | null): TemperatureMetrics[] {
  if (metric?.temperatures?.length) return metric.temperatures;

  const fallback: TemperatureMetrics[] = [];
  if (metric?.cpu?.temperatureC != null) {
    fallback.push({ id: 'cpu', label: 'CPU', temperatureC: metric.cpu.temperatureC, source: 'payload' });
  }
  if (metric?.gpu?.temperatureC != null) {
    fallback.push({ id: 'gpu', label: 'GPU', temperatureC: metric.gpu.temperatureC, source: 'payload' });
  }
  return fallback;
}

function pagedTemperatureItems(
  sensors: TemperatureMetrics[],
  date: Date,
  pageSize = 3,
  pageMs = 8000,
): { items: TemperatureMetrics[]; page: number; pageCount: number } {
  const ordered = [...sensors].sort((a, b) => b.temperatureC - a.temperatureC);
  if (ordered.length <= pageSize) return { items: ordered, page: 0, pageCount: 1 };

  const pageCount = Math.ceil(ordered.length / pageSize);
  const page = Math.floor(date.getTime() / pageMs) % pageCount;
  return {
    items: ordered.slice(page * pageSize, page * pageSize + pageSize),
    page,
    pageCount,
  };
}

function processLabel(name: string): string {
  return name.replace(/\.exe$/i, '');
}

function processDisplayLabel(name: string, processCount?: number | null): string {
  const label = processLabel(name);
  return processCount != null && processCount > 1 ? `${label} (${processCount})` : label;
}

function processShare(processBytes: number, topBytes: number): number {
  if (!topBytes) return 0;
  return Math.max(8, Math.min(100, (processBytes / topBytes) * 100));
}

function diskUsedShare(usedBytes?: number | null, freeBytes?: number | null, totalBytes?: number | null, usagePercent?: number | null): number {
  if (usedBytes != null && totalBytes) return (usedBytes / totalBytes) * 100;
  if (freeBytes != null && totalBytes) return 100 - (freeBytes / totalBytes) * 100;
  if (usagePercent != null) return usagePercent;
  return 0;
}

function vramPair(used?: number | null, total?: number | null): string {
  if (used == null || total == null || total === 0) return '--';
  return `${(used / 1024 ** 3).toFixed(1)}/${(total / 1024 ** 3).toFixed(0)} GB`;
}

function uptime(seconds?: number | null): string {
  if (seconds == null) return '--';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function visibleCompactPanels(panels: CompactPanel[], date: Date): CompactPanel[] {
  const ordered = [...panels].sort((a, b) => a.priority - b.priority);
  if (ordered.length <= 5) return ordered.slice(0, 4);

  const start = Math.floor(date.getTime() / 8000) % ordered.length;
  return Array.from({ length: 4 }, (_, index) => ordered[(start + index) % ordered.length]);
}

function StatCard({
  tone,
  icon,
  label,
  value,
  unit,
  sub,
  sparkValues,
  sparkMax = 100,
  graphic,
  children,
}: {
  tone: string;
  icon: ReactNode;
  label: string;
  value: string;
  unit?: string;
  sub: string;
  sparkValues: Array<number | null | undefined>;
  sparkMax?: number;
  graphic?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="card" style={{ '--tone': tone } as CSSProperties}>
      <div className="card-top">
        <div className="icon-wrap">{icon}</div>
        <div>
          <p className="label">{label}</p>
          <p className="subtle">{sub}</p>
        </div>
      </div>
      <div className="metric-line">
        <span className="metric-value">{value}</span>
        {unit ? <span className="metric-unit">{unit}</span> : null}
      </div>
      {graphic ?? <Sparkline values={sparkValues} color={tone} max={sparkMax} />}
      {children ? <div className="details">{children}</div> : null}
    </section>
  );
}

function metricShare(value?: number | null, max?: number | null): number {
  if (value == null || max == null || max <= 0) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}

function GpuGraphic({
  usageValues,
  memoryUsedBytes,
  memoryTotalBytes,
  memoryValues,
}: {
  usageValues: Array<number | null | undefined>;
  memoryUsedBytes?: number | null;
  memoryTotalBytes?: number | null;
  memoryValues: Array<number | null | undefined>;
}) {
  return (
    <div className="gpu-graphic">
      <Sparkline values={usageValues} color="#35df87" />
      <div className="gpu-vram-line">
        <span className="gpu-vram-label">VRAM</span>
        <span className="gpu-vram-value">{vramPair(memoryUsedBytes, memoryTotalBytes)}</span>
      </div>
      <Sparkline values={memoryValues} color="#35df87" />
    </div>
  );
}

function CompactCard({
  tone,
  icon,
  label,
  value,
  sub,
  sparkValues,
  sparkMax = 100,
  children,
}: {
  tone: string;
  icon: ReactNode;
  label: string;
    value?: string;
  sub: string;
  sparkValues?: Array<number | null | undefined>;
  sparkMax?: number;
  children: ReactNode;
}) {
  return (
    <section className="compact-card" style={{ '--tone': tone } as CSSProperties}>
      <div className="compact-top">
        <div className="compact-icon-wrap">{icon}</div>
        <div className="compact-copy">
          <p className="label">{label}</p>
          <p className="subtle">{sub}</p>
        </div>
      </div>
      {value || sparkValues ? (
        <div className="compact-main">
          {value ? <span className="compact-value">{value}</span> : null}
          {sparkValues ? <Sparkline values={sparkValues} color={tone} max={sparkMax} /> : null}
        </div>
      ) : null}
      <div className="compact-details">{children}</div>
    </section>
  );
}

export default function App() {
  const { envelope, connected } = useMetrics();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const latest = envelope.latest;
  const displayStatus = connected ? envelope.status : 'disconnected';
  const history = envelope.history;
  const cpuSeries = useMemo(() => series(history, (item) => item.cpu?.usagePercent), [history]);
  const ramSeries = useMemo(() => series(history, (item) => item.memory?.usagePercent), [history]);
  const gpuSeries = useMemo(() => series(history, (item) => item.gpu?.usagePercent), [history]);
  const gpuMemorySeries = useMemo(
    () => series(history, (item) => metricShare(item.gpu?.memoryUsedBytes, item.gpu?.memoryTotalBytes)),
    [history],
  );
  const networkDownSeries = useMemo(() => series(history, (item) => (item.network?.rxBytesPerSecond ?? 0) / 1024 / 1024), [history]);
  const networkUpSeries = useMemo(() => series(history, (item) => (item.network?.txBytesPerSecond ?? 0) / 1024 / 1024), [history]);
  const perCore = latest?.cpu?.perCoreUsagePercent ?? [];
  const batteries = latest?.peripheralBatteries ?? [];
  const lowestBattery = batteries.length
    ? [...batteries].sort((a, b) => a.batteryPercent - b.batteryPercent)[0]
    : null;
  const batteryList = batteries.length ? [...batteries].sort((a, b) => a.batteryPercent - b.batteryPercent).slice(0, 4) : [];
  const thermals = temperatureItems(latest);
  const visibleThermals = pagedTemperatureItems(thermals, now);
  const diskVolumes = latest?.disk?.volumes?.length
    ? latest.disk.volumes
    : latest?.disk
      ? [{
        name: 'Free',
        mountpoint: 'disk',
        usagePercent: latest.disk.usagePercent,
        usedBytes: latest.disk.usedBytes,
        freeBytes: latest.disk.freeBytes,
        totalBytes: latest.disk.totalBytes,
      }]
      : [];
  const compactPanels = visibleCompactPanels(
    [
      {
        key: 'thermals',
        priority: 10,
        content: (
          <CompactCard
            tone="#ff8b3d"
            icon={<Thermometer size={22} />}
            label="Thermals"
            sub={maxTemp(latest) != null && maxTemp(latest)! >= 82 ? 'High Temperature' : 'Thermal Headroom'}
          >
            {thermals.length > 0 ? (
              <>
                <RankedMeterList
                  items={visibleThermals.items.map((sensor) => ({
                    id: sensor.id,
                    label: sensor.label,
                    value: number1(sensor.temperatureC, 'C'),
                    percent: sensor.temperatureC,
                  }))}
                  showRank={false}
                />
                {visibleThermals.pageCount > 1 ? (
                  <div className="thermal-page-dots" aria-label={`Temperature page ${visibleThermals.page + 1} of ${visibleThermals.pageCount}`}>
                    {Array.from({ length: visibleThermals.pageCount }, (_, index) => (
                      <i key={index} className={index === visibleThermals.page ? 'active' : undefined} />
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <span className="empty-detail">Temperature sensors unavailable</span>
            )}
          </CompactCard>
        ),
      },
      {
        key: 'disk',
        priority: 20,
        content: (
          <CompactCard
            tone="#f4d35e"
            icon={<HardDrive size={22} />}
            label="Disk"
            sub="Storage"
          >
            <RankedMeterList
              items={diskVolumes.slice(0, 4).map((volume) => ({
                id: volume.mountpoint,
                label: volume.name,
                value: `${bytes(volume.freeBytes)} left`,
                percent: diskUsedShare(volume.usedBytes, volume.freeBytes, volume.totalBytes, volume.usagePercent),
              }))}
              showRank={false}
            />
          </CompactCard>
        ),
      },
      {
        key: 'network',
        priority: 30,
        content: (
          <CompactCard
            tone="#d7dde7"
            icon={<Network size={22} />}
            label="Network"
            sub="Throughput"
          >
            <div className="network-meters">
              <div className="network-meter">
                <span className="network-rate">
                  <ArrowUp size={18} /> {throughput(latest?.network?.txBytesPerSecond)}
                </span>
                <Sparkline values={networkUpSeries} color="#d7dde7" max={8} />
              </div>
              <div className="network-meter">
                <span className="network-rate">
                  <ArrowDown size={18} /> {throughput(latest?.network?.rxBytesPerSecond)}
                </span>
                <Sparkline values={networkDownSeries} color="#d7dde7" max={8} />
              </div>
            </div>
          </CompactCard>
        ),
      },
      ...(lowestBattery
        ? [
          {
            key: 'battery',
            priority: 40,
            content: (
              <CompactCard
                tone={lowestBattery.batteryPercent <= 20 ? '#ff6b6b' : '#35df87'}
                icon={lowestBattery.charging ? <BatteryCharging size={22} /> : <BatteryFull size={22} />}
                label="Battery"
                sub="Connected Devices"
              >
                <RankedMeterList
                  items={batteryList.map((battery) => ({
                    id: battery.id,
                    label: battery.name,
                    value: `${percent(battery.batteryPercent)}${battery.charging ? ' +' : ''}`,
                    percent: battery.batteryPercent,
                  }))}
                  showRank={false}
                />
              </CompactCard>
            ),
          },
        ]
        : []),
      {
        key: 'status',
        priority: 50,
        content: (
          <CompactCard
            tone="#78a6ff"
            icon={connected ? <Wifi size={22} /> : <WifiOff size={22} />}
            label="Status"
            value={clock(now)}
            sub={displayStatus.toUpperCase()}
          >
            <span>Uptime {uptime(latest?.uptimeSeconds)}</span>
            <span className="status-pill">
              <Activity size={14} /> {connected ? envelope.status : 'disconnected'}
            </span>
          </CompactCard>
        ),
      },
    ],
    now,
  );

  return (
    <main className={`dashboard state-${displayStatus}`}>
      <div className="dashboard-shell">
        <StatCard
          tone="#20c7ff"
          icon={<Cpu size={28} />}
          label="CPU"
          value={percent(latest?.cpu?.usagePercent)}
          sub={latest?.cpu?.name ?? latest?.host ?? 'waiting for metrics'}
          sparkValues={cpuSeries}
        >
          <div className="core-bars">
            {perCore.slice(0, 16).map((core, index) => (
              <i key={index} style={{ height: `${Math.max(8, core)}%` }} />
            ))}
          </div>
        </StatCard>

        <StatCard
          tone="#ad7dff"
          icon={<MemoryStick size={28} />}
          label="RAM"
          value={percent(latest?.memory?.usagePercent)}
          sub={gbPair(latest?.memory?.usedBytes, latest?.memory?.totalBytes)}
          sparkValues={ramSeries}
        >
          <div className="ram-processes">
            {(latest?.memory?.topProcesses ?? []).length > 0 ? (
              <RankedMeterList
                items={latest?.memory?.topProcesses?.slice(0, 3).map((process, _index, processes) => {
                  const topBytes = processes[0]?.rssBytes ?? 0;
                  return {
                    id: `${process.pids.join('-')}-${process.name}`,
                    label: processDisplayLabel(process.name, process.processCount ?? process.pids?.length),
                    value: bytes(process.rssBytes),
                    percent: processShare(process.rssBytes, topBytes),
                  };
                }) ?? []}
              />
            ) : (
              <span className="empty-detail">Top processes unavailable</span>
            )}
          </div>
        </StatCard>

        <StatCard
          tone="#35df87"
          icon={<Gauge size={28} />}
          label="GPU"
          value={percent(latest?.gpu?.usagePercent)}
          sub={latest?.gpu?.name ?? 'GPU unavailable'}
          sparkValues={gpuSeries}
          graphic={
            <GpuGraphic
              usageValues={gpuSeries}
              memoryUsedBytes={latest?.gpu?.memoryUsedBytes}
              memoryTotalBytes={latest?.gpu?.memoryTotalBytes}
              memoryValues={gpuMemorySeries}
            />
          }
        />

        <div className="compact-grid">
          {compactPanels.map((panel) => (
            <div className="compact-slot" key={panel.key}>
              {panel.content}
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
