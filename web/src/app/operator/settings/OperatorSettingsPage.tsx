'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import OperatorGate from '@/components/OperatorGate'
import type {
  OperatorConfig,
  OperatorPublication,
  OperatorEvidence,
  OperatorTemporal,
  OperatorFinancialBand,
  OperatorQuality,
} from '@/lib/types'

// ── Default values (match migration 074 seeds) ──────────────

const DEFAULTS: OperatorConfig = {
  publication: {
    tier_high: 0.85, tier_medium: 0.70, tier_low: 0.50,
    hedge_enabled: true,
    hedge_text: 'Other explanations may exist.',
    blocklist: [
      'corruption', 'corrupt', 'illegal', 'illegally',
      'bribery', 'bribe', 'kickback',
      'scandal', 'scandalous', 'suspicious', 'suspiciously',
    ],
  },
  evidence: {
    match_strength: 0.35, temporal_factor: 0.25,
    financial_factor: 0.20, anomaly_factor: 0.20,
    sitting_mult: 1.0, non_sitting_mult: 0.6,
    corroboration_2: 1.15, corroboration_3plus: 1.30,
  },
  temporal: {
    bands: [
      { days: 90, factor: 1.0 }, { days: 180, factor: 0.8 },
      { days: 365, factor: 0.6 }, { days: 730, factor: 0.4 },
    ],
    beyond_factor: 0.2, post_vote_penalty: 0.70,
    anomaly_boost_days: 30, anomaly_boost_amount: 0.10,
  },
  financial: [
    { min: 5000, factor: 1.0 }, { min: 1000, factor: 0.7 },
    { min: 500, factor: 0.5 }, { min: 100, factor: 0.3 },
    { min: 0, factor: 0.1 },
  ],
  quality: {
    weight_items: 30, weight_votes: 30,
    weight_attendance: 20, weight_urls: 20,
    anomaly_stddev: 2.0, min_baselines: 50, default_anomaly: 0.5,
  },
  updated_at: '',
}

// ── Helpers ──────────────────────────────────────────────────

function formatAge(dateStr: string): string {
  if (!dateStr) return 'never'
  const diffMs = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

// ── Slider Component ────────────────────────────────────────

function Slider({
  label, value, min, max, step, onChange, suffix = '', disabled,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  suffix?: string
  disabled?: boolean
}) {
  return (
    <div className="flex items-center gap-3">
      <label className="text-sm text-slate-600 w-40 shrink-0">{label}</label>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        className="flex-1 accent-civic-amber"
      />
      <span className="text-sm font-mono text-slate-700 w-16 text-right">
        {value.toFixed(step < 1 ? 2 : 0)}{suffix}
      </span>
    </div>
  )
}

// ── Collapsible Section ─────────────────────────────────────

function Section({
  title, isDirty, onReset, defaultOpen = false, children,
}: {
  title: string
  isDirty: boolean
  onReset: () => void
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-800">{title}</span>
          {isDirty && (
            <span className="w-2 h-2 rounded-full bg-amber-500" title="Unsaved changes" />
          )}
        </div>
        <span className="text-slate-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-slate-100">
          <div className="pt-3 space-y-3">
            {children}
          </div>
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={onReset}
              className="text-xs text-slate-400 hover:text-slate-600 underline decoration-dotted"
            >
              Reset to defaults
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Blocklist Pills ─────────────────────────────────────────

function BlocklistEditor({
  words, onChange,
}: {
  words: string[]
  onChange: (words: string[]) => void
}) {
  const [input, setInput] = useState('')

  const addWord = () => {
    const word = input.trim().toLowerCase()
    if (word && !words.includes(word)) {
      onChange([...words, word])
    }
    setInput('')
  }

  return (
    <div>
      <label className="text-sm text-slate-600 block mb-1">Blocklisted words</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {words.map((w) => (
          <span
            key={w}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-50 text-red-700 text-xs rounded-full border border-red-200"
          >
            {w}
            <button
              type="button"
              onClick={() => onChange(words.filter((x) => x !== w))}
              className="hover:text-red-900"
              aria-label={`Remove ${w}`}
            >
              &times;
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addWord() } }}
          placeholder="Add word..."
          className="text-sm border border-slate-200 rounded px-2 py-1 flex-1"
        />
        <button
          type="button"
          onClick={addWord}
          className="text-sm px-3 py-1 bg-slate-100 hover:bg-slate-200 rounded border border-slate-200"
        >
          Add
        </button>
      </div>
    </div>
  )
}

// ── Main Dashboard ──────────────────────────────────────────

function SettingsDashboard() {
  const [config, setConfig] = useState<OperatorConfig | null>(null)
  const [draft, setDraft] = useState<OperatorConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const saveMsgTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    fetch('/api/operator/settings')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: OperatorConfig) => {
        setConfig(data)
        setDraft(data)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const isDirty = config && draft ? !deepEqual(config, draft) : false

  const evidenceSum = draft
    ? draft.evidence.match_strength +
      draft.evidence.temporal_factor +
      draft.evidence.financial_factor +
      draft.evidence.anomaly_factor
    : 1.0

  const canSave = isDirty && !saving && Math.abs(evidenceSum - 1.0) <= 0.01

  const handleSave = useCallback(async () => {
    if (!draft || !canSave) return
    setSaving(true)
    setError(null)
    try {
      const res = await fetch('/api/operator/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error || `HTTP ${res.status}`)
      }
      const updated: OperatorConfig = await res.json()
      setConfig(updated)
      setDraft(updated)
      setSaveMsg('Saved')
      if (saveMsgTimer.current) clearTimeout(saveMsgTimer.current)
      saveMsgTimer.current = setTimeout(() => setSaveMsg(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }, [draft, canSave])

  // Section-level dirty checks
  const pubDirty = config && draft ? !deepEqual(config.publication, draft.publication) : false
  const evDirty = config && draft ? !deepEqual(config.evidence, draft.evidence) : false
  const tempDirty = config && draft ? !deepEqual(config.temporal, draft.temporal) : false
  const finDirty = config && draft ? !deepEqual(config.financial, draft.financial) : false
  const qualDirty = config && draft ? !deepEqual(config.quality, draft.quality) : false

  // Update helpers
  const updatePub = (patch: Partial<OperatorPublication>) =>
    setDraft((d) => d ? { ...d, publication: { ...d.publication, ...patch } } : d)
  const updateEv = (patch: Partial<OperatorEvidence>) =>
    setDraft((d) => d ? { ...d, evidence: { ...d.evidence, ...patch } } : d)
  const updateTemp = (patch: Partial<OperatorTemporal>) =>
    setDraft((d) => d ? { ...d, temporal: { ...d.temporal, ...patch } } : d)
  const updateTempBand = (idx: number, factor: number) =>
    setDraft((d) => {
      if (!d) return d
      const bands = d.temporal.bands.map((b, i) => i === idx ? { ...b, factor } : b)
      return { ...d, temporal: { ...d.temporal, bands } }
    })
  const updateFinBand = (idx: number, factor: number) =>
    setDraft((d) => {
      if (!d) return d
      const fin = d.financial.map((b, i) => i === idx ? { ...b, factor } : b)
      return { ...d, financial: fin }
    })
  const updateQual = (patch: Partial<OperatorQuality>) =>
    setDraft((d) => d ? { ...d, quality: { ...d.quality, ...patch } } : d)

  if (loading) {
    return <div className="text-center py-12 text-slate-500">Loading settings...</div>
  }

  if (error && !draft) {
    return <div className="text-center py-12 text-red-600">Failed to load settings: {error}</div>
  }

  if (!draft) return null

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-800">Scanner Parameters</h2>
        <span className="text-xs text-slate-400">
          Last saved {formatAge(config?.updated_at ?? '')}
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Section 1: Publication thresholds */}
      <Section
        title="1. What gets published?"
        isDirty={pubDirty}
        onReset={() => setDraft((d) => d ? { ...d, publication: DEFAULTS.publication } : d)}
        defaultOpen
      >
        <Slider
          label="High-confidence (Tier 1)"
          value={draft.publication.tier_high}
          min={0.40} max={1.00} step={0.01}
          onChange={(v) => updatePub({ tier_high: v })}
          suffix="%"
        />
        <Slider
          label="Medium-confidence (Tier 2)"
          value={draft.publication.tier_medium}
          min={0.40} max={1.00} step={0.01}
          onChange={(v) => updatePub({ tier_medium: v })}
          suffix="%"
        />
        <Slider
          label="Low-confidence (Tier 3)"
          value={draft.publication.tier_low}
          min={0.40} max={1.00} step={0.01}
          onChange={(v) => updatePub({ tier_low: v })}
          suffix="%"
        />
        {/* Tier diagram */}
        <div className="mt-2 rounded bg-slate-50 border border-slate-200 p-3">
          <div className="text-xs text-slate-500 mb-2">Visibility mapping</div>
          <div className="flex gap-1 text-xs font-mono">
            <span className="bg-green-100 text-green-800 px-2 py-1 rounded">
              &ge;{(draft.publication.tier_high * 100).toFixed(0)}% Public (Tier 1)
            </span>
            <span className="bg-amber-100 text-amber-800 px-2 py-1 rounded">
              &ge;{(draft.publication.tier_medium * 100).toFixed(0)}% Public (Tier 2)
            </span>
            <span className="bg-orange-100 text-orange-800 px-2 py-1 rounded">
              &ge;{(draft.publication.tier_low * 100).toFixed(0)}% Operator-only
            </span>
            <span className="bg-slate-100 text-slate-500 px-2 py-1 rounded">
              &lt;{(draft.publication.tier_low * 100).toFixed(0)}% Hidden
            </span>
          </div>
        </div>
      </Section>

      {/* Section 2: Evidence weights */}
      <Section
        title="2. How is evidence weighted?"
        isDirty={evDirty}
        onReset={() => setDraft((d) => d ? { ...d, evidence: DEFAULTS.evidence } : d)}
      >
        <div className="space-y-2">
          <Slider
            label="Match strength"
            value={draft.evidence.match_strength}
            min={0.05} max={0.60} step={0.01}
            onChange={(v) => updateEv({ match_strength: v })}
          />
          <Slider
            label="Temporal factor"
            value={draft.evidence.temporal_factor}
            min={0.05} max={0.60} step={0.01}
            onChange={(v) => updateEv({ temporal_factor: v })}
          />
          <Slider
            label="Financial factor"
            value={draft.evidence.financial_factor}
            min={0.05} max={0.60} step={0.01}
            onChange={(v) => updateEv({ financial_factor: v })}
          />
          <Slider
            label="Anomaly factor"
            value={draft.evidence.anomaly_factor}
            min={0.05} max={0.60} step={0.01}
            onChange={(v) => updateEv({ anomaly_factor: v })}
          />
          <div className={`text-xs font-mono text-right ${Math.abs(evidenceSum - 1.0) > 0.01 ? 'text-amber-600 font-bold' : 'text-slate-400'}`}>
            Sum: {evidenceSum.toFixed(2)}{Math.abs(evidenceSum - 1.0) > 0.01 ? ' (must equal 1.00)' : ''}
          </div>
        </div>

        <div className="border-t border-slate-100 pt-3 mt-3 space-y-2">
          <div className="text-xs text-slate-500 mb-1">Multipliers</div>
          <Slider
            label="Sitting member"
            value={draft.evidence.sitting_mult}
            min={0.5} max={1.5} step={0.05}
            onChange={(v) => updateEv({ sitting_mult: v })}
            suffix="x"
          />
          <Slider
            label="Non-sitting member"
            value={draft.evidence.non_sitting_mult}
            min={0.1} max={1.0} step={0.05}
            onChange={(v) => updateEv({ non_sitting_mult: v })}
            suffix="x"
          />
          <Slider
            label="2-signal corroboration"
            value={draft.evidence.corroboration_2}
            min={1.0} max={1.5} step={0.05}
            onChange={(v) => updateEv({ corroboration_2: v })}
            suffix="x"
          />
          <Slider
            label="3+ signal corroboration"
            value={draft.evidence.corroboration_3plus}
            min={1.0} max={2.0} step={0.05}
            onChange={(v) => updateEv({ corroboration_3plus: v })}
            suffix="x"
          />
        </div>
      </Section>

      {/* Section 3: Temporal bands */}
      <Section
        title="3. Temporal signal bands"
        isDirty={tempDirty}
        onReset={() => setDraft((d) => d ? { ...d, temporal: DEFAULTS.temporal } : d)}
      >
        {draft.temporal.bands.map((band, i) => (
          <Slider
            key={band.days}
            label={`Within ${band.days <= 365 ? band.days + 'd' : (band.days / 365).toFixed(0) + 'yr'}`}
            value={band.factor}
            min={0.0} max={1.0} step={0.05}
            onChange={(v) => updateTempBand(i, v)}
          />
        ))}
        <Slider
          label="Beyond all bands"
          value={draft.temporal.beyond_factor}
          min={0.0} max={0.5} step={0.05}
          onChange={(v) => updateTemp({ beyond_factor: v })}
        />
        <div className="border-t border-slate-100 pt-3 mt-2 space-y-2">
          <Slider
            label="Post-vote penalty"
            value={draft.temporal.post_vote_penalty}
            min={0.3} max={1.0} step={0.05}
            onChange={(v) => updateTemp({ post_vote_penalty: v })}
            suffix="x"
          />
          <Slider
            label="Anomaly boost window"
            value={draft.temporal.anomaly_boost_days}
            min={7} max={90} step={1}
            onChange={(v) => updateTemp({ anomaly_boost_days: v })}
            suffix="d"
          />
          <Slider
            label="Anomaly boost amount"
            value={draft.temporal.anomaly_boost_amount}
            min={0.0} max={0.3} step={0.01}
            onChange={(v) => updateTemp({ anomaly_boost_amount: v })}
          />
        </div>
      </Section>

      {/* Section 4: Financial bands */}
      <Section
        title="4. Financial materiality"
        isDirty={finDirty}
        onReset={() => setDraft((d) => d ? { ...d, financial: DEFAULTS.financial } : d)}
      >
        {draft.financial.map((band, i) => (
          <Slider
            key={band.min}
            label={band.min === 0 ? 'Under $100' : `$${band.min.toLocaleString()}+`}
            value={band.factor}
            min={0.0} max={1.0} step={0.05}
            onChange={(v) => updateFinBand(i, v)}
          />
        ))}
      </Section>

      {/* Section 5: Language controls */}
      <Section
        title="5. Language controls"
        isDirty={pubDirty}
        onReset={() => setDraft((d) => d ? { ...d, publication: DEFAULTS.publication } : d)}
      >
        <div className="flex items-center gap-3">
          <label className="text-sm text-slate-600">Hedge clause</label>
          <button
            type="button"
            onClick={() => updatePub({ hedge_enabled: !draft.publication.hedge_enabled })}
            className={`relative w-10 h-5 rounded-full transition-colors ${draft.publication.hedge_enabled ? 'bg-civic-amber' : 'bg-slate-300'}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${draft.publication.hedge_enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </button>
          <span className="text-xs text-slate-400">{draft.publication.hedge_enabled ? 'Enabled' : 'Disabled'}</span>
        </div>
        {draft.publication.hedge_enabled && (
          <div>
            <label className="text-sm text-slate-600 block mb-1">Hedge text</label>
            <input
              type="text"
              value={draft.publication.hedge_text}
              onChange={(e) => updatePub({ hedge_text: e.target.value })}
              className="w-full text-sm border border-slate-200 rounded px-3 py-1.5"
            />
          </div>
        )}
        <BlocklistEditor
          words={draft.publication.blocklist}
          onChange={(blocklist) => updatePub({ blocklist })}
        />
      </Section>

      {/* Section 6: Data quality weights (from quality config) */}
      <Section
        title="6. Data completeness weights"
        isDirty={qualDirty}
        onReset={() => setDraft((d) => d ? { ...d, quality: DEFAULTS.quality } : d)}
      >
        <Slider
          label="Agenda items weight"
          value={draft.quality.weight_items}
          min={0} max={100} step={5}
          onChange={(v) => updateQual({ weight_items: v })}
        />
        <Slider
          label="Votes weight"
          value={draft.quality.weight_votes}
          min={0} max={100} step={5}
          onChange={(v) => updateQual({ weight_votes: v })}
        />
        <Slider
          label="Attendance weight"
          value={draft.quality.weight_attendance}
          min={0} max={100} step={5}
          onChange={(v) => updateQual({ weight_attendance: v })}
        />
        <Slider
          label="URLs weight"
          value={draft.quality.weight_urls}
          min={0} max={100} step={5}
          onChange={(v) => updateQual({ weight_urls: v })}
        />
        <div className="text-xs text-slate-400 font-mono text-right">
          Sum: {draft.quality.weight_items + draft.quality.weight_votes + draft.quality.weight_attendance + draft.quality.weight_urls}
          {' '}(should be 100)
        </div>
        <div className="border-t border-slate-100 pt-3 mt-2 space-y-2">
          <Slider
            label="Anomaly stddev threshold"
            value={draft.quality.anomaly_stddev}
            min={1.0} max={4.0} step={0.1}
            onChange={(v) => updateQual({ anomaly_stddev: v })}
          />
          <Slider
            label="Min baselines"
            value={draft.quality.min_baselines}
            min={10} max={200} step={10}
            onChange={(v) => updateQual({ min_baselines: v })}
          />
          <Slider
            label="Default anomaly factor"
            value={draft.quality.default_anomaly}
            min={0.0} max={1.0} step={0.05}
            onChange={(v) => updateQual({ default_anomaly: v })}
          />
        </div>
      </Section>

      {/* Sticky save bar */}
      {isDirty && (
        <div className="sticky bottom-0 bg-white border-t border-slate-200 px-4 py-3 flex items-center justify-between rounded-b-lg shadow-lg -mx-1">
          <span className="text-sm text-amber-600">
            Unsaved changes
          </span>
          <div className="flex items-center gap-3">
            {saveMsg && (
              <span className="text-sm text-green-600">{saveMsg}</span>
            )}
            <button
              type="button"
              onClick={() => setDraft(config)}
              className="text-sm px-3 py-1.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              className={`text-sm px-4 py-1.5 rounded font-semibold ${
                canSave
                  ? 'bg-civic-amber text-white hover:bg-amber-600'
                  : 'bg-slate-200 text-slate-400 cursor-not-allowed'
              }`}
            >
              {saving ? 'Saving...' : 'Save changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Page Wrapper ────────────────────────────────────────────

export default function OperatorSettingsPage() {
  return (
    <OperatorGate>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-civic-navy mb-6">
          Settings
        </h1>
        <SettingsDashboard />
      </div>
    </OperatorGate>
  )
}
