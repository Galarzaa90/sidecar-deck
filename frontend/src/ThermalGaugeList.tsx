import type { CSSProperties } from 'react';
import type { TemperatureMetrics } from './types';

interface ThermalGaugeListProps {
  items: TemperatureMetrics[];
  pageDate?: Date;
  pageMs?: number;
  pageSize?: number;
}

function thermalColor(temperatureC: number): string {
  if (temperatureC >= 82) return '#ff6b6b';
  if (temperatureC >= 70) return '#ffb05c';
  return '#ff8b3d';
}

function ThermalGauge({ sensor }: { sensor: TemperatureMetrics }) {
  const color = thermalColor(sensor.temperatureC);

  return (
    <div
      className="thermal-gauge"
      style={{ '--thermal-value': color } as CSSProperties}
      aria-label={`${sensor.label}: ${Math.round(sensor.temperatureC)} degrees Celsius`}
    >
      <span className="thermal-gauge-value">{Math.round(sensor.temperatureC)}<small>°C</small></span>
      <span className="thermal-gauge-label">{sensor.label}</span>
    </div>
  );
}

export function ThermalGaugeList({
  items,
  pageDate,
  pageMs = 8000,
  pageSize = 3,
}: ThermalGaugeListProps) {
  const shouldPage = pageDate != null && items.length > pageSize;
  const pageCount = shouldPage ? Math.ceil(items.length / pageSize) : 1;
  const page = shouldPage ? Math.floor(pageDate.getTime() / pageMs) % pageCount : 0;
  const visibleItems = shouldPage ? items.slice(page * pageSize, page * pageSize + pageSize) : items;

  return (
    <div className="thermal-gauge-list">
      <div className="thermal-gauges">
        {visibleItems.map((sensor) => <ThermalGauge key={sensor.id} sensor={sensor} />)}
      </div>
      {shouldPage ? (
        <div className="meter-page-dots" aria-label={`Temperature page ${page + 1} of ${pageCount}`}>
          {Array.from({ length: pageCount }, (_, index) => <i key={index} className={index === page ? 'active' : undefined} />)}
        </div>
      ) : null}
    </div>
  );
}
