export interface RankedMeterItem {
  id: string;
  label: string;
  value: string;
  percent: number;
}

interface RankedMeterListProps {
  className?: string;
  items: RankedMeterItem[];
  showRank?: boolean;
}

export function RankedMeterList({ className, items, showRank = true }: RankedMeterListProps) {
  return (
    <div className={`ranked-meter-list${className ? ` ${className}` : ''}`}>
      {items.map((item, index) => (
        <div className={`ranked-meter-item${showRank ? '' : ' without-rank'}`} key={item.id}>
          {showRank ? <span className="meter-rank">{index + 1}</span> : null}
          <div className="meter-main">
            <div className="meter-row">
              <span className="meter-name">{item.label}</span>
              <span className="meter-value">{item.value}</span>
            </div>
            <div className="meter-track">
              <i style={{ width: `${Math.max(8, Math.min(100, item.percent))}%` }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
