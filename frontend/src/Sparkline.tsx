interface SparklineProps {
  values: Array<number | null | undefined>;
  color: string;
  max?: number;
  autoScale?: boolean;
  scaleFloor?: number;
}

function roundedScaleMax(value: number): number {
  if (value <= 0) return 1;

  const padded = value * 1.15;
  const magnitude = 10 ** Math.floor(Math.log10(padded));
  const normalized = padded / magnitude;
  const rounded = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;

  return rounded * magnitude;
}

export function Sparkline({ values, color, max = 100, autoScale = false, scaleFloor = 1 }: SparklineProps) {
  const recent = values.slice(-120);
  const historyMax = Math.max(0, ...recent.map((value) => (typeof value === 'number' ? value : 0)));
  const scaleMax = autoScale ? Math.max(scaleFloor, roundedScaleMax(historyMax)) : max;
  const clean = recent.map((value) => (typeof value === 'number' ? Math.max(0, Math.min(scaleMax, value)) : null));
  const width = 300;
  const height = 96;
  const step = clean.length > 1 ? width / (clean.length - 1) : width;
  const points = clean
    .map((value, index) => {
      if (value == null) return null;
      const x = index * step;
      const y = height - (value / scaleMax) * (height - 10) - 5;
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
