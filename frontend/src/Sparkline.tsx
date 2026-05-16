interface SparklineProps {
  values: Array<number | null | undefined>;
  color: string;
  max?: number;
}

export function Sparkline({ values, color, max = 100 }: SparklineProps) {
  const clean = values.slice(-120).map((value) => (typeof value === 'number' ? Math.max(0, Math.min(max, value)) : null));
  const width = 300;
  const height = 96;
  const step = clean.length > 1 ? width / (clean.length - 1) : width;
  const points = clean
    .map((value, index) => {
      if (value == null) return null;
      const x = index * step;
      const y = height - (value / max) * (height - 10) - 5;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(' ');

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={`glow-${color.replace('#', '')}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.95" />
        </linearGradient>
      </defs>
      <path className="spark-grid" d="M0 24 H300 M0 48 H300 M0 72 H300" />
      {points ? (
        <polyline
          points={points}
          fill="none"
          stroke={`url(#glow-${color.replace('#', '')})`}
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ) : (
        <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke={color} strokeDasharray="8 10" opacity="0.45" />
      )}
    </svg>
  );
}
