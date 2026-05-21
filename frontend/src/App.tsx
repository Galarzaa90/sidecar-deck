import { Activity, ArrowDown, ArrowUp, BatteryCharging, BatteryFull, CalendarDays, Cloud, CloudDrizzle, CloudFog, CloudHail, CloudLightning, CloudRain, CloudRainWind, CloudSnow, CloudSun, CloudSunRain, Cloudy, Cpu, Gauge, HardDrive, MemoryStick, MonitorOff, Network, Sun, Thermometer, Wifi, WifiOff } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { age, bytes, clock, coarseAge, gbPair, number1, percent, throughput } from './format';
import { RankedMeterList } from './RankedMeterList';
import { Sparkline } from './Sparkline';
import type { MetricPayload, StatusEnvelope, TemperatureMetrics, WeatherEnvelope } from './types';

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

const emptyWeather: WeatherEnvelope = {
  status: 'unconfigured',
  locationLabel: null,
  updatedAt: new Date().toISOString(),
  current: null,
  forecast: [],
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

function useWeather() {
  const [weather, setWeather] = useState<WeatherEnvelope>(emptyWeather);
  const [weatherError, setWeatherError] = useState(false);

  useEffect(() => {
    let stopped = false;

    const loadWeather = async () => {
      try {
        const response = await fetch('/api/weather', { cache: 'no-store' });
        if (!response.ok) throw new Error(`weather request failed: ${response.status}`);
        const nextWeather = await response.json();
        if (!stopped) {
          setWeather(nextWeather);
          setWeatherError(false);
        }
      } catch {
        if (!stopped) setWeatherError(true);
      }
    };

    loadWeather();
    const timer = window.setInterval(loadWeather, 10 * 60 * 1000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  return { weather, weatherError };
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

function processLabel(name: string): string {
  return name.replace(/\.exe$/i, '');
}

function processDisplayLabel(name: string, processCount?: number | null): ReactNode {
  const label = processLabel(name);
  return (
    <>
      {label}
      {processCount != null && processCount > 1 ? <span className="process-count">{processCount}</span> : null}
    </>
  );
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

function dateLabel(date: Date): string {
  return date.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
}

function forecastDayLabel(value: string): string {
  const date = new Date(`${value}T12:00:00`);
  return date.toLocaleDateString([], { weekday: 'short' });
}

function temperature(value?: number | null): string {
  return value == null || Number.isNaN(value) ? '--' : `${Math.round(value)}°C`;
}

function weatherIcon(code?: number | null): LucideIcon {
  switch (code) {
    case 0:
      return Sun;
    case 1:
    case 2:
      return CloudSun;
    case 3:
      return Cloudy;
    case 45:
    case 48:
      return CloudFog;
    case 51:
    case 53:
    case 55:
      return CloudDrizzle;
    case 56:
    case 57:
      return CloudHail;
    case 61:
    case 63:
      return CloudRain;
    case 65:
      return CloudRainWind;
    case 66:
    case 67:
      return CloudHail;
    case 71:
    case 73:
    case 75:
    case 77:
    case 85:
    case 86:
      return CloudSnow;
    case 80:
    case 81:
    case 82:
      return CloudSunRain;
    case 95:
    case 96:
    case 99:
      return CloudLightning;
    default:
      return Cloud;
  }
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

function StandbyDashboard({
  envelope,
  now,
  weather,
  weatherError,
}: {
  envelope: StatusEnvelope;
  now: Date;
  weather: WeatherEnvelope;
  weatherError: boolean;
}) {
  const hasSeenAgent = envelope.status === 'offline' && envelope.ageSeconds != null;
  const connectionValue = hasSeenAgent ? coarseAge(envelope.ageSeconds) : '--';
  const connectionSub = hasSeenAgent ? 'Last seen' : 'No metrics received yet';
  const weatherCurrent = weather.current;
  const WeatherCurrentIcon = weatherIcon(weatherCurrent?.weatherCode);

  return (
    <div className="standby-shell">
      <section className="standby-card standby-card-large" style={{ '--tone': '#ff6b6b' } as CSSProperties}>
        <div className="standby-top">
          <div className="icon-wrap"><MonitorOff size={30} /></div>
          <div>
            <p className="label">PC Standby</p>
            <p className="subtle">{connectionSub}</p>
          </div>
        </div>
        <div className="standby-metric">
          <span>{envelope.status === 'waiting' ? 'Waiting' : connectionValue}</span>
        </div>
        <p className="standby-note">
          {envelope.status === 'waiting'
            ? 'The dashboard is ready for the first agent update.'
            : 'The PC is off or the agent connection was lost.'}
        </p>
      </section>

      <section className="standby-card" style={{ '--tone': '#78a6ff' } as CSSProperties}>
        <div className="standby-top">
          <div className="icon-wrap"><CalendarDays size={30} /></div>
          <div>
            <p className="label">Clock</p>
            <p className="subtle">{dateLabel(now)}</p>
          </div>
        </div>
        <div className="standby-clock">{clock(now)}</div>
        <p className="standby-note">{now.toLocaleDateString([], { year: 'numeric', month: 'long', day: 'numeric' })}</p>
      </section>

      <section className="standby-card standby-weather" style={{ '--tone': '#35df87' } as CSSProperties}>
        <div className="standby-top">
          <div className="icon-wrap"><CloudSun size={30} /></div>
          <div>
            <p className="label">Weather</p>
            <p className="subtle">{weather.locationLabel ?? 'Set WEATHER_LOCATION'}</p>
          </div>
        </div>
        {weather.status === 'ok' && weatherCurrent ? (
          <>
            <div className="weather-current">
              <WeatherCurrentIcon className="weather-current-icon" size={50} strokeWidth={1.8} />
              <span className="weather-temp">{temperature(weatherCurrent.temperatureC)}</span>
              <span className="weather-condition">{weatherCurrent.condition}</span>
            </div>
            <div className="forecast-list">
              {weather.forecast.slice(0, 5).map((day) => {
                const ForecastIcon = weatherIcon(day.weatherCode);
                return (
                  <div className="forecast-row" key={day.date}>
                    <span>{forecastDayLabel(day.date)}</span>
                    <ForecastIcon size={17} strokeWidth={2.1} />
                    <span>{day.condition}</span>
                    <strong>{temperature(day.temperatureMaxC)} / {temperature(day.temperatureMinC)}</strong>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <p className="standby-note">
            {weatherError
              ? 'Weather is temporarily unavailable.'
              : weather.status === 'not_found'
                ? 'Weather location was not found.'
                : 'Weather location is not configured.'}
          </p>
        )}
      </section>
    </div>
  );
}

export default function App() {
  const { envelope, connected } = useMetrics();
  const { weather, weatherError } = useWeather();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const latest = envelope.latest;
  const displayStatus = connected ? envelope.status : 'disconnected';
  const isStandby = envelope.status === 'waiting' || envelope.status === 'offline';
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
  const batteryList = batteries.length ? [...batteries].sort((a, b) => a.batteryPercent - b.batteryPercent) : [];
  const thermals = temperatureItems(latest);
  const thermalList = [...thermals].sort((a, b) => b.temperatureC - a.temperatureC);
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
                  items={thermalList.map((sensor) => ({
                    id: sensor.id,
                    label: sensor.label,
                    value: number1(sensor.temperatureC, 'C'),
                    percent: sensor.temperatureC,
                  }))}
                  pageDate={now}
                  pageLabel="Temperature"
                  pageSize={3}
                  showRank={false}
                />
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
              items={diskVolumes.map((volume) => ({
                id: volume.mountpoint,
                label: volume.name,
                value: `${bytes(volume.freeBytes)} left`,
                percent: diskUsedShare(volume.usedBytes, volume.freeBytes, volume.totalBytes, volume.usagePercent),
              }))}
              pageDate={now}
              pageLabel="Disk"
              pageSize={3}
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
                <Sparkline values={networkUpSeries} color="#d7dde7" autoScale scaleFloor={0.1} />
              </div>
              <div className="network-meter">
                <span className="network-rate">
                  <ArrowDown size={18} /> {throughput(latest?.network?.rxBytesPerSecond)}
                </span>
                <Sparkline values={networkDownSeries} color="#d7dde7" autoScale scaleFloor={0.1} />
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
                  pageDate={now}
                  pageLabel="Battery"
                  pageSize={3}
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
    <main className={`dashboard state-${displayStatus}${isStandby ? ' state-standby' : ''}`}>
      {isStandby ? (
        <StandbyDashboard envelope={envelope} now={now} weather={weather} weatherError={weatherError} />
      ) : (
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
                items={latest?.memory?.topProcesses?.slice(0, 5).map((process, _index, processes) => {
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
      )}
    </main>
  );
}
