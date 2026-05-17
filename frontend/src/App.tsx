import { Activity, Cpu, Gauge, MemoryStick, Thermometer, Wifi, WifiOff } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { age, bytes, clock, gbPair, number1, percent, throughput } from './format';
import { Sparkline } from './Sparkline';
import type { MetricPayload, StatusEnvelope } from './types';

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
  const values = [metric?.cpu?.temperatureC, metric?.gpu?.temperatureC].filter((item): item is number => typeof item === 'number');
  return values.length ? Math.max(...values) : null;
}

function processLabel(name: string): string {
  return name.replace(/\.exe$/i, '');
}

function processShare(processBytes: number, topBytes: number): number {
  if (!topBytes) return 0;
  return Math.max(8, Math.min(100, (processBytes / topBytes) * 100));
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
  children: ReactNode;
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
      <Sparkline values={sparkValues} color={tone} max={sparkMax} />
      <div className="details">{children}</div>
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
  const tempSeries = useMemo(() => series(history, maxTemp), [history]);
  const cpuSeries = useMemo(() => series(history, (item) => item.cpu?.usagePercent), [history]);
  const ramSeries = useMemo(() => series(history, (item) => item.memory?.usagePercent), [history]);
  const gpuSeries = useMemo(() => series(history, (item) => item.gpu?.usagePercent), [history]);
  const networkSeries = useMemo(() => series(history, (item) => (item.network?.rxBytesPerSecond ?? 0) / 1024 / 1024), [history]);
  const perCore = latest?.cpu?.perCoreUsagePercent ?? [];

  return (
    <main className={`dashboard state-${displayStatus}`}>
      <div className="dashboard-shell">
        <StatCard
          tone="#20c7ff"
          icon={<Cpu size={28} />}
          label="CPU"
          value={percent(latest?.cpu?.usagePercent)}
          sub={latest?.host ?? 'waiting for metrics'}
          sparkValues={cpuSeries}
        >
          <span>Temp {number1(latest?.cpu?.temperatureC, 'C')}</span>
          <span>Clock {latest?.cpu?.clockMhz ? `${Math.round(latest.cpu.clockMhz)} MHz` : '--'}</span>
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
              latest?.memory?.topProcesses?.slice(0, 3).map((process, index, processes) => {
                const topBytes = processes[0]?.rssBytes ?? 0;
                return (
                  <div className="ram-process" key={`${process.pid}-${process.name}`}>
                    <span className="process-rank">{index + 1}</span>
                    <div className="process-main">
                      <div className="process-row">
                        <span className="process-name">{processLabel(process.name)}</span>
                        <span className="process-memory">{bytes(process.rssBytes)}</span>
                      </div>
                      <div className="process-track">
                        <i style={{ width: `${processShare(process.rssBytes, topBytes)}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })
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
        >
          <span>VRAM {gbPair(latest?.gpu?.memoryUsedBytes, latest?.gpu?.memoryTotalBytes)}</span>
          <span>Temp {number1(latest?.gpu?.temperatureC, 'C')}</span>
        </StatCard>

        <StatCard
          tone="#ff8b3d"
          icon={<Thermometer size={28} />}
          label="Thermals"
          value={number1(maxTemp(latest), 'C')}
          sub={maxTemp(latest) != null && maxTemp(latest)! >= 82 ? 'high temperature' : 'thermal headroom'}
          sparkValues={tempSeries}
          sparkMax={100}
        >
          <span>CPU {number1(latest?.cpu?.temperatureC, 'C')}</span>
          <span>GPU {number1(latest?.gpu?.temperatureC, 'C')}</span>
          <span>Disk {percent(latest?.disk?.usagePercent)}</span>
        </StatCard>

        <StatCard
          tone="#d7dde7"
          icon={connected ? <Wifi size={28} /> : <WifiOff size={28} />}
          label="Network"
          value={clock(now)}
          sub={displayStatus.toUpperCase()}
          sparkValues={networkSeries}
          sparkMax={8}
        >
          <span>Down {throughput(latest?.network?.rxBytesPerSecond)}</span>
          <span>Up {throughput(latest?.network?.txBytesPerSecond)}</span>
          <span>Last {age(envelope.ageSeconds)}</span>
          <span className="status-pill">
            <Activity size={14} /> {connected ? envelope.status : 'disconnected'}
          </span>
        </StatCard>
      </div>
    </main>
  );
}
