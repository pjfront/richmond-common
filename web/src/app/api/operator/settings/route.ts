import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import type {
  OperatorConfig,
  OperatorPublication,
  OperatorEvidence,
} from '@/lib/types'

const RICHMOND_FIPS = '0660620'

export async function GET() {
  try {
    const { data, error } = await supabase
      .from('operator_config')
      .select('publication, evidence, temporal, financial, quality, updated_at')
      .eq('city_fips', RICHMOND_FIPS)
      .maybeSingle()

    if (error) throw error
    if (!data) {
      return NextResponse.json(
        { error: 'No config row found. Migration 074 may need to be applied.' },
        { status: 404 },
      )
    }

    const config: OperatorConfig = {
      publication: data.publication as OperatorPublication,
      evidence: data.evidence as OperatorEvidence,
      temporal: data.temporal,
      financial: data.financial,
      quality: data.quality,
      updated_at: data.updated_at,
    }

    return NextResponse.json(config, {
      headers: { 'Cache-Control': 'no-store' },
    })
  } catch (err) {
    console.error('Operator settings fetch failed:', err)
    return NextResponse.json(
      { error: 'Failed to fetch operator settings' },
      { status: 500 },
    )
  }
}

export async function PUT(request: Request) {
  try {
    const body = await request.json() as Partial<OperatorConfig>

    // Validate evidence weights sum to 1.0 (±0.01)
    if (body.evidence) {
      const ev = body.evidence
      const sum =
        (ev.match_strength ?? 0) +
        (ev.temporal_factor ?? 0) +
        (ev.financial_factor ?? 0) +
        (ev.anomaly_factor ?? 0)
      if (Math.abs(sum - 1.0) > 0.01) {
        return NextResponse.json(
          { error: `Evidence weights must sum to 1.0 (got ${sum.toFixed(4)})` },
          { status: 400 },
        )
      }
    }

    // Validate tier thresholds are descending
    if (body.publication) {
      const pub = body.publication
      if (pub.tier_high <= pub.tier_medium || pub.tier_medium <= pub.tier_low) {
        return NextResponse.json(
          { error: 'Tier thresholds must be descending: high > medium > low' },
          { status: 400 },
        )
      }
    }

    // Build update payload — only include provided fields
    const update: Record<string, unknown> = {
      updated_at: new Date().toISOString(),
      updated_by: 'operator',
    }
    if (body.publication) update.publication = body.publication
    if (body.evidence) update.evidence = body.evidence
    if (body.temporal) update.temporal = body.temporal
    if (body.financial) update.financial = body.financial
    if (body.quality) update.quality = body.quality

    const { data, error } = await supabase
      .from('operator_config')
      .update(update)
      .eq('city_fips', RICHMOND_FIPS)
      .select('publication, evidence, temporal, financial, quality, updated_at')
      .single()

    if (error) throw error

    const config: OperatorConfig = {
      publication: data.publication,
      evidence: data.evidence,
      temporal: data.temporal,
      financial: data.financial,
      quality: data.quality,
      updated_at: data.updated_at,
    }

    return NextResponse.json(config)
  } catch (err) {
    console.error('Operator settings update failed:', err)
    return NextResponse.json(
      { error: 'Failed to update operator settings' },
      { status: 500 },
    )
  }
}
