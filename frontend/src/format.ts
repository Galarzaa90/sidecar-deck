export function percent(value?: number | null): string {
  return value == null || Number.isNaN(value) ? '--' : `${Math.round(value)}%`;
}

export function number1(value?: number | null, unit = ''): string {
  return value == null || Number.isNaN(value) ? '--' : `${value.toFixed(1)}${unit}`;
}

export function bytes(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

export function throughput(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${bytes(value)}/s`;
}

export function age(seconds?: number | null): string {
  if (seconds == null) return '--';
  if (seconds < 1) return 'now';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function clock(date = new Date()): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function gbPair(used?: number | null, total?: number | null): string {
  if (used == null || total == null || total === 0) return '--';
  return `${(used / 1024 ** 3).toFixed(1)} / ${(total / 1024 ** 3).toFixed(0)} GB`;
}
