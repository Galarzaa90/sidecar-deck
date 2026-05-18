export interface RankedMeterItem {
  id: string;
  label: string;
  value: string;
  percent: number;
}

interface RankedMeterListProps {
  className?: string;
  items: RankedMeterItem[];
  pageDate?: Date;
  pageMs?: number;
  pageSize?: number;
  pageLabel?: string;
  showRank?: boolean;
}

export function RankedMeterList({
  className,
  items,
  pageDate,
  pageMs = 8000,
  pageSize,
  pageLabel = 'Meter',
  showRank = true,
}: RankedMeterListProps) {
  const shouldPage = pageDate != null && pageSize != null && items.length > pageSize;
  const pageCount = shouldPage ? Math.ceil(items.length / pageSize) : 1;
  const page = shouldPage ? Math.floor(pageDate.getTime() / pageMs) % pageCount : 0;
  const visibleItems = shouldPage ? items.slice(page * pageSize, page * pageSize + pageSize) : items;

  const list = (
    <div className={`ranked-meter-list${className ? ` ${className}` : ''}`}>
      {visibleItems.map((item, index) => (
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

  if (!shouldPage) return list;

  return (
    <div className="paged-meter-list">
      {list}
      <div className="meter-page-dots" aria-label={`${pageLabel} page ${page + 1} of ${pageCount}`}>
        {Array.from({ length: pageCount }, (_, index) => (
          <i key={index} className={index === page ? 'active' : undefined} />
        ))}
      </div>
    </div>
  );
}
