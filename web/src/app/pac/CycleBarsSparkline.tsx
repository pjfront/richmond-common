/**
 * CycleBarsSparkline. Tiny per-row visual showing one bar per election
 * cycle. Used on the PAC index page row to give residents the temporal
 * layer answer ("how does now compare to historically") without
 * cluttering the row.
 *
 * Inputs are 5 cycle entries (2018, 2020, 2022, 2024, 2026 by
 * convention). Each bar's height is proportional to total in+out flow
 * that cycle. The current cycle is rendered in civic-amber to stand
 * apart; historical cycles are civic-navy at lower opacity.
 *
 * Server-side renderable (pure SVG, no client interactivity at the
 * index-row level. Profile-page version will be a richer client
 * component).
 */

interface CycleBar {
  cycle: number
  in_total: number
  out_total: number
}

interface Props {
  bars: CycleBar[]
  /** Cycle to highlight in amber. Defaults to the largest cycle in bars. */
  currentCycle?: number
}

const W = 100
const H = 24
const BAR_GAP = 2

export default function CycleBarsSparkline({ bars, currentCycle }: Props) {
  if (bars.length === 0) return null
  const current = currentCycle ?? Math.max(...bars.map((b) => b.cycle))
  const totals = bars.map((b) => b.in_total + b.out_total)
  const max = Math.max(...totals, 1)

  const barW = (W - BAR_GAP * (bars.length - 1)) / bars.length

  return (
    <svg
      viewBox={`0 0 ${W} ${H + 8}`}
      width={W}
      height={H + 8}
      role="img"
      aria-label={`Activity across ${bars.length} election cycles, ${bars[0].cycle} to ${bars[bars.length - 1].cycle}`}
      className="shrink-0"
    >
      {bars.map((b, i) => {
        const total = b.in_total + b.out_total
        const h = total === 0 ? 1 : Math.max(2, (total / max) * H)
        const x = i * (barW + BAR_GAP)
        const y = H - h
        const isCurrent = b.cycle === current
        const isEmpty = total === 0
        const fill = isEmpty
          ? '#e2e8f0'
          : isCurrent
            ? '#d97706'
            : '#1e3a5f'
        const opacity = isEmpty ? 1 : isCurrent ? 1 : 0.55
        return (
          <g key={b.cycle}>
            <rect
              x={x}
              y={y}
              width={barW}
              height={h}
              fill={fill}
              opacity={opacity}
              rx={1}
            />
            <text
              x={x + barW / 2}
              y={H + 7}
              textAnchor="middle"
              fontSize={6}
              fill="#94a3b8"
            >
              {String(b.cycle).slice(2)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
