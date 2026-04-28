"""
Provenance struct builders for auto-generated text artifacts.

Every Python generator that writes a text artifact (recap, summary, bio)
also writes a Provenance struct in the SAME UPDATE — see migration 095
header for rationale (Entry 50/51 dishonest-attribution audit).

This module gives generators a typed builder for each kind so the JSONB
column shape stays consistent with the TypeScript discriminated union in
web/src/lib/types.ts. Adding a new kind: add a builder here AND a switch
arm in web/src/components/SourceAttribution.tsx.

The shape is intentionally minimal — kind + the inputs the renderer
actually needs + as_of + diagnostic-only fields (generator, backfilled).
Don't pile additional fields on without mirroring them in the TS type.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal, TypedDict


# ── Provenance variants ────────────────────────────────────────────────


class _ProvenanceBase(TypedDict, total=False):
    as_of: str
    generator: str
    backfilled: bool


class OfficialMinutesProvenance(_ProvenanceBase):
    kind: Literal["official_minutes"]
    minutes_url: str | None


class MeetingRecordingProvenance(_ProvenanceBase):
    kind: Literal["meeting_recording"]
    channel: Literal["kcrt", "granicus"]


class AgendaPacketProvenance(_ProvenanceBase):
    kind: Literal["agenda_packet"]
    agenda_url: str | None


class MixedProvenance(_ProvenanceBase):
    kind: Literal["mixed"]
    from_minutes: int
    from_transcript: int


class CampaignFilingPeriodProvenance(_ProvenanceBase):
    kind: Literal["campaign_filing_period"]
    period_label: str            # e.g. "2026-Q1"
    contributions_count: int     # rows aggregated into the briefing
    paper_filings_count: int     # rows from src/data/paper_filings/*.json
    filed_through: str | None    # ISO date — last contribution covered


Provenance = (
    OfficialMinutesProvenance
    | MeetingRecordingProvenance
    | AgendaPacketProvenance
    | MixedProvenance
    | CampaignFilingPeriodProvenance
)


# ── Builders ───────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def official_minutes(
    *, minutes_url: str | None, generator: str, backfilled: bool = False
) -> OfficialMinutesProvenance:
    """Artifact derived from official minutes (ground truth)."""
    p: OfficialMinutesProvenance = {
        "kind": "official_minutes",
        "minutes_url": minutes_url,
        "as_of": _now(),
        "generator": generator,
    }
    if backfilled:
        p["backfilled"] = True
    return p


def meeting_recording(
    *,
    channel: Literal["kcrt", "granicus"],
    generator: str,
    backfilled: bool = False,
) -> MeetingRecordingProvenance:
    """Artifact derived from auto-caption transcript of a meeting recording."""
    p: MeetingRecordingProvenance = {
        "kind": "meeting_recording",
        "channel": channel,
        "as_of": _now(),
        "generator": generator,
    }
    if backfilled:
        p["backfilled"] = True
    return p


def agenda_packet(
    *, agenda_url: str | None, generator: str, backfilled: bool = False
) -> AgendaPacketProvenance:
    """Artifact derived from the eSCRIBE agenda packet (title, description, staff reports)."""
    p: AgendaPacketProvenance = {
        "kind": "agenda_packet",
        "agenda_url": agenda_url,
        "as_of": _now(),
        "generator": generator,
    }
    if backfilled:
        p["backfilled"] = True
    return p


def mixed(
    *,
    from_minutes: int,
    from_transcript: int,
    generator: str,
    backfilled: bool = False,
) -> MixedProvenance | OfficialMinutesProvenance | MeetingRecordingProvenance:
    """Aggregate artifact spanning multiple input sources.

    If the aggregate happens to span only one kind, returns the more
    specific kind instead — keeps the rendered label as precise as the
    underlying data allows.
    """
    if from_transcript == 0:
        # Pure-minutes — the bio's normal case.
        return official_minutes(
            minutes_url=None, generator=generator, backfilled=backfilled
        )
    if from_minutes == 0:
        # Pure-transcript edge case (e.g., brand-new member).
        return meeting_recording(
            channel="kcrt", generator=generator, backfilled=backfilled
        )
    p: MixedProvenance = {
        "kind": "mixed",
        "from_minutes": from_minutes,
        "from_transcript": from_transcript,
        "as_of": _now(),
        "generator": generator,
    }
    if backfilled:
        p["backfilled"] = True
    return p


def campaign_filing_period(
    *,
    period_label: str,
    contributions_count: int,
    paper_filings_count: int,
    filed_through: str | None,
    generator: str,
    backfilled: bool = False,
) -> CampaignFilingPeriodProvenance:
    """Artifact derived from a campaign-finance filing period.

    Used by src/filing_period_briefing.py for the per-period briefing
    (F1..F9 sections). The renderer needs counts to disclose evidence
    completeness ("based on 1,247 contributions across 12 committees,
    filed through 2026-04-24") and filed_through to surface the lag
    between period close and last actual filing — a missing-paper-filer
    signal in itself.
    """
    p: CampaignFilingPeriodProvenance = {
        "kind": "campaign_filing_period",
        "period_label": period_label,
        "contributions_count": contributions_count,
        "paper_filings_count": paper_filings_count,
        "filed_through": filed_through,
        "as_of": _now(),
        "generator": generator,
    }
    if backfilled:
        p["backfilled"] = True
    return p


# ── Serialization ──────────────────────────────────────────────────────


def to_json(p: Provenance) -> str:
    """psycopg2-compatible JSONB serialization."""
    return json.dumps(p)
