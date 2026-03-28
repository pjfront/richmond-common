import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const size = { width: 180, height: 180 }
export const contentType = 'image/png'

const NAVY = '#1e3a5f'
const AMBER = '#fbbf24'

// 32-unit design → 180px canvas
const S = 180 / 32

function px(n: number) {
  return Math.round(n * S)
}

export default function AppleIcon() {
  const r = px(4.5)
  const d = r * 2

  const dots: Array<{ cx: number; cy: number; fill: string }> = [
    { cx: 9.5, cy: 9.5, fill: 'white' },
    { cx: 22.5, cy: 9.5, fill: 'white' },
    { cx: 9.5, cy: 22.5, fill: 'white' },
    { cx: 22.5, cy: 22.5, fill: AMBER },
  ]

  return new ImageResponse(
    (
      <div
        style={{
          width: 180,
          height: 180,
          borderRadius: px(7),
          background: NAVY,
          display: 'flex',
          position: 'relative',
        }}
      >
        {dots.map(({ cx, cy, fill }, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: px(cx) - r,
              top: px(cy) - r,
              width: d,
              height: d,
              borderRadius: '50%',
              background: fill,
            }}
          />
        ))}
      </div>
    ),
    { ...size },
  )
}
