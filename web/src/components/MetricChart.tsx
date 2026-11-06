import type { ResearchCell } from '../types'

function format(value: number | null, unit: string) {
  if (value === null) return '—'
  if (unit === '%') return `${value.toFixed(1)}%`
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
  }
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

export function MetricChart({
  cells,
  periods,
  unit,
  activePeriod,
  onSelect,
}: {
  cells: Record<string, ResearchCell>
  periods: string[]
  unit: string
  activePeriod?: string
  onSelect: (period: string) => void
}) {
  const points = periods
    .map((period, index) => ({ period, index, cell: cells[period] }))
    .filter((point) => point.cell?.value !== null && point.cell?.value !== undefined)

  if (points.length < 2) {
    return (
      <div className="flex h-[168px] items-center justify-center rounded-md border border-border/60 text-[10px] text-muted">
        至少需要两个年度的数据才能画曲线
      </div>
    )
  }

  const width = 640
  const height = 170
  const pad = { left: 42, right: 16, top: 14, bottom: 26 }
  const values = points.map((point) => Number(point.cell.value))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || Math.abs(max) || 1
  const yMin = min - span * 0.15
  const yMax = max + span * 0.15
  const x = (index: number) =>
    pad.left + (index / Math.max(periods.length - 1, 1)) * (width - pad.left - pad.right)
  const y = (value: number) =>
    pad.top + ((yMax - value) / (yMax - yMin)) * (height - pad.top - pad.bottom)

  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(point.index)} ${y(Number(point.cell.value))}`)
    .join(' ')
  const area = `${path} L ${x(points.at(-1)!.index)} ${height - pad.bottom} L ${x(points[0].index)} ${height - pad.bottom} Z`

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-[168px] w-full overflow-visible"
      role="img"
      aria-label="指标趋势"
    >
      <defs>
        <linearGradient id="metric-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--foreground)" stopOpacity="0.10" />
          <stop offset="100%" stopColor="var(--foreground)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((ratio) => {
        const value = yMax - (yMax - yMin) * ratio
        return (
          <g key={ratio}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--separator)"
              strokeDasharray="2 3"
            />
            <text x={pad.left - 7} y={y(value) + 3} textAnchor="end" fontSize="8" fill="var(--muted)">
              {format(value, unit)}
            </text>
          </g>
        )
      })}
      <path d={area} fill="url(#metric-fill)" />
      <path d={path} fill="none" stroke="var(--foreground)" strokeWidth="1.4" strokeLinejoin="round" />
      {points.map((point) => {
        const cy = y(Number(point.cell.value))
        const active = point.period === activePeriod
        return (
          <g key={point.period} className="cursor-pointer" onClick={() => onSelect(point.period)}>
            <circle cx={x(point.index)} cy={cy} r={active ? 4 : 2.6} fill={active ? 'var(--foreground)' : 'var(--background)'} stroke="var(--foreground)" strokeWidth="1.2" />
            <text x={x(point.index)} y={height - 9} textAnchor="middle" fontSize="9" fill={active ? 'var(--foreground)' : 'var(--muted)'}>
              {point.period}
            </text>
            <text x={x(point.index)} y={cy - 8} textAnchor="middle" fontSize="8" fill="var(--muted)">
              {format(Number(point.cell.value), unit)}
            </text>
          </g>
        )
      })}
      {periods.map((period, index) => {
        const cell = cells[period]
        if (cell?.value !== null && cell?.value !== undefined) return null
        return (
          <text key={`missing-${period}`} x={x(index)} y={height - 9} textAnchor="middle" fontSize="8" fill="#4f4f54">
            {period} 未披露
          </text>
        )
      })}
    </svg>
  )
}
