import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const size = { width: 180, height: 180 }
export const contentType = 'image/png'

const NAVY = '#1e3a5f'
const AMBER = '#fbbf24'

// Scale factor: our SVG is 32×32, icon is 180×180
const S = 180 / 32

function px(n: number) {
  return Math.round(n * S)
}

export default function AppleIcon() {
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
          overflow: 'hidden',
        }}
      >
        {/* Suspension ring */}
        <div style={{
          position: 'absolute',
          left: px(16) - px(1.5),
          top: px(5) - px(1.5),
          width: px(3),
          height: px(3),
          borderRadius: '50%',
          background: 'white',
        }} />

        {/* Cap — rendered as a bordered div rotated, approximated as triangle via borders */}
        {/* We use a CSS border trick for the triangle */}
        <div style={{
          position: 'absolute',
          left: px(8),
          top: px(7),
          width: 0,
          height: 0,
          borderLeft: `${px(8)}px solid transparent`,
          borderRight: `${px(8)}px solid transparent`,
          borderBottom: `${px(7)}px solid white`,
        }} />

        {/* Lantern body */}
        <div style={{
          position: 'absolute',
          left: px(8),
          top: px(14),
          width: px(16),
          height: px(11),
          background: 'white',
          borderRadius: `0 0 ${px(1.5)}px ${px(1.5)}px`,
        }} />

        {/* Amber glow */}
        <div style={{
          position: 'absolute',
          left: px(10.5),
          top: px(15.5),
          width: px(11),
          height: px(8),
          background: AMBER,
          opacity: 0.5,
          borderRadius: px(1),
        }} />

        {/* Pane — horizontal bar */}
        <div style={{
          position: 'absolute',
          left: px(8),
          top: px(19),
          width: px(16),
          height: Math.max(1, px(0.75)),
          background: NAVY,
        }} />

        {/* Pane — vertical bar */}
        <div style={{
          position: 'absolute',
          left: px(15.625),
          top: px(14),
          width: Math.max(1, px(0.75)),
          height: px(11),
          background: NAVY,
        }} />

        {/* Base */}
        <div style={{
          position: 'absolute',
          left: px(11.5),
          top: px(25),
          width: px(9),
          height: px(3),
          background: 'white',
          borderRadius: px(1.5),
        }} />
      </div>
    ),
    { ...size },
  )
}
