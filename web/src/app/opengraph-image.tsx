import { ImageResponse } from 'next/og'

export const runtime = 'edge'

export const alt = 'Richmond Commons — your city government, in plain language'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%)',
          padding: '60px 80px',
        }}
      >
        {/* Top accent line */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '6px',
            background: '#d97706',
          }}
        />

        {/* Main title */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '24px',
          }}
        >
          <div
            style={{
              fontSize: '72px',
              fontWeight: 700,
              color: '#ffffff',
              letterSpacing: '-1px',
              lineHeight: 1.1,
            }}
          >
            Richmond Commons
          </div>

          {/* Divider */}
          <div
            style={{
              width: '80px',
              height: '4px',
              background: '#d97706',
              borderRadius: '2px',
            }}
          />

          {/* Tagline */}
          <div
            style={{
              fontSize: '28px',
              fontWeight: 400,
              color: '#cbd5e1',
              textAlign: 'center',
              lineHeight: 1.4,
              maxWidth: '800px',
            }}
          >
            Your city government, in one place
            and in plain language.
          </div>
        </div>

        {/* Bottom bar with topics */}
        <div
          style={{
            position: 'absolute',
            bottom: '48px',
            display: 'flex',
            gap: '32px',
            alignItems: 'center',
          }}
        >
          {['Council Votes', 'Campaign Finance', 'Public Meetings'].map(
            (topic) => (
              <div
                key={topic}
                style={{
                  fontSize: '18px',
                  fontWeight: 500,
                  color: '#94a3b8',
                  letterSpacing: '1px',
                  textTransform: 'uppercase',
                }}
              >
                {topic}
              </div>
            )
          )}
        </div>
      </div>
    ),
    { ...size }
  )
}
