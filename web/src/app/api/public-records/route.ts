import { NextResponse } from 'next/server'
import { getPublicRecordsStats, getDepartmentCompliance } from '@/lib/queries'

export async function GET() {
  try {
    const [stats, departments] = await Promise.all([
      getPublicRecordsStats(),
      getDepartmentCompliance(),
    ])

    return NextResponse.json(
      { stats, departments },
      {
        headers: {
          'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
        },
      }
    )
  } catch (error) {
    console.error('Public records API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch public records data' },
      { status: 500 }
    )
  }
}
