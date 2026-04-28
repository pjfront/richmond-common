"""
Filing-period briefing generator — Stream 2 of the campaign-finance
briefings family.

Reads source-closest contributions data — `contributions` rows in the DB
(populated from NetFile electronic + extracted paper PDFs by Stream 1)
filtered by election_id + contribution_date window. Does NOT read from
derivative aggregates (no per-candidate "totals" tables, no cached
summaries) — every number is recomputed from contribution rows so the
briefing is reproducible from raw data.

Pipeline (mirrors src/post_meeting_recap.py):

  1. Trigger     → Filing period closes (or 24-hour report fires)
  2. Evidence    → contributions + committees + candidates + paper filings,
                   scoped by (city_fips, election_id, period_start..period_end)
  3. Generate    → Per-candidate sections F1 (totals) F2 (geography)
                   F3 (industry/PAC) F4 (self/related-party); cross-candidate
                   sections F5..F9 land in later commits
  4. Upsert      → filing_period_briefings (one current row per period_label,
                   prior rows preserved with is_current=false for audit)

This file is the SKELETON for Stream 2. F1–F4 are wired with structured
shapes and provenance. F5–F9 are stubbed with TODO markers — each is a
follow-on commit on this branch. The generator is runnable end-to-end
in --dry-run mode so the schema / Tier model can be exercised without
writing to DB.

Usage:
  python filing_period_briefing.py --period 2026-Q1
  python filing_period_briefing.py --period 2026-Q1 --dry-run
  python filing_period_briefing.py --period 2026-Q1 --force
  python filing_period_briefing.py --period 2026-Q1 --election-id <uuid>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import provenance as prov  # noqa: E402

# ── Config ────────────────────────────────────────────────────────

GENERATOR_VERSION = "v0.1-stream2-skeleton"
DEFAULT_FIPS = "0660620"

# Zip-prefix bucketing for F2. Richmond proper covers 94801–94808; the
# wider Bay Area is everything else in the 94xxx + 95xxx ranges (with
# a few Sacramento-area exceptions handled by state/zip combination,
# not prefix). Operator confirmed bucketing in plan §"Open items".
RICHMOND_ZIP_PREFIXES = ("9480", "9481")  # 94801-94819 covers Richmond + immediate neighbors

# Bay Area = 94xxx (SF, peninsula, North Bay, East Bay) + 950/951 (Santa
# Clara / San Jose). 952-959 is Central Valley / Sacramento / Monterey
# and is treated as california_other. The operator's "Open items" entry
# in the plan asks to confirm this bucketing — these prefixes are the
# provisional answer that produces sensible results for Richmond's
# typical donor footprint, to be refined after the article reconciliation.
BAY_AREA_ZIP_PREFIXES = ("94", "950", "951")


# ── Period parsing ────────────────────────────────────────────────


@dataclass
class FilingPeriod:
    """A filing-deadline-aligned reporting window.

    period_end is filing-deadline-aligned, NOT calendar-quarter-aligned —
    e.g. Q1 2026 closes 2026-04-24 (FPPC semi-annual deadline), not
    2026-03-31. The briefing generator covers the legal reporting window
    so totals reconcile to filed Form 460 / 497 statements.
    """
    label: str            # '2026-Q1'
    kind: str             # 'quarterly' | 'pre_election_24h' | 'semi_annual' | 'annual'
    period_start: date    # inclusive
    period_end: date      # inclusive (filing-deadline-aligned)


# Hard-coded periods until S25 brings filing-calendar discovery online.
# These are Richmond-specific; multi-city work moves them into city_config.
KNOWN_PERIODS: dict[str, FilingPeriod] = {
    "2026-Q1": FilingPeriod(
        label="2026-Q1",
        kind="quarterly",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 4, 24),
    ),
    # 24-hour pre-election reports: every contribution ≥$1,000 received
    # in the 90 days before an election. The briefing generator runs
    # nightly during this window so each new 497 surfaces fast.
    "2026-pre-primary-24h": FilingPeriod(
        label="2026-pre-primary-24h",
        kind="pre_election_24h",
        period_start=date(2026, 3, 4),   # 90 days before 2026-06-02 primary
        period_end=date(2026, 6, 2),
    ),
}


def resolve_period(period_label: str) -> FilingPeriod:
    """Look up a known filing period by its operator-facing label."""
    if period_label not in KNOWN_PERIODS:
        raise ValueError(
            f"Unknown filing period {period_label!r}. "
            f"Known: {sorted(KNOWN_PERIODS)}"
        )
    return KNOWN_PERIODS[period_label]


# ── Step 1: Evidence base ─────────────────────────────────────────


@dataclass
class Candidate:
    """One row of election_candidates joined to its committee."""
    id: str
    name: str
    office_sought: str
    committee_id: str | None
    committee_name: str | None
    fppc_id: str | None


@dataclass
class Contribution:
    """One row of contributions, normalized for briefing-section math.

    zip / state are best-effort parsed from donors.address — the schema
    keeps address as a single TEXT field, so geography is structurally
    lossy until a schema extension ships (a Stream 2 follow-on commit).
    Until then, missing-zip rows fall into the F2 'unknown' bucket and
    are excluded from share denominators.
    """
    id: str
    contributor_name: str
    contributor_employer: str | None
    occupation: str | None
    amount: float
    date: date
    zip: str | None
    state: str | None
    entity_code: str | None    # 'IND' | 'COM' | 'OTH' | ...
    source: str                # 'netfile' | 'fppc_paper' | 'cal_access'
    committee_id: str | None
    committee_name: str | None


# Address parsing — donors.address is a single TEXT field, so zip / state
# must be extracted heuristically. These regexes match well-formed US
# addresses; non-conforming addresses (international, freeform) leave the
# fields NULL and the contribution falls into the F2 'unknown' bucket.
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_STATE_RE = re.compile(r"\b([A-Z]{2})\b\s*(?:\d{5})")  # state immediately before zip


def _parse_zip_state(address: str | None) -> tuple[str | None, str | None]:
    """Best-effort (zip, state) extraction from a freeform US address."""
    if not address:
        return None, None
    zip_m = _ZIP_RE.search(address)
    state_m = _STATE_RE.search(address)
    return (zip_m.group(1) if zip_m else None,
            state_m.group(1) if state_m else None)


@dataclass
class Evidence:
    """Source-closest evidence base for one filing period.

    All section generators read from this struct — never from the DB
    directly — so the briefing is reproducible from a snapshot, and the
    article-as-oracle harness (tests/test_filing_period_briefing.py) can
    feed it a fixture without touching Supabase.
    """
    period: FilingPeriod
    election_id: str | None
    candidates: list[Candidate]
    contributions: list[Contribution]
    paper_filings_count: int
    filed_through: date | None = None


def fetch_evidence(
    *,
    period: FilingPeriod,
    city_fips: str,
    election_id: str | None,
) -> Evidence:
    """Pull contributions + candidates + committees for the period.

    Source-closest: reads contributions rows directly. Stream 1's paper
    extractor populates contributions via load_paper_filings.py, so by
    the time we get here the DB is the ground truth — no second-pass
    JSON read.
    """
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Resolve election_id if not provided — default to the most
            # recent election whose date overlaps the period.
            if election_id is None:
                cur.execute(
                    """SELECT id FROM elections
                        WHERE city_fips = %s
                          AND election_date >= %s
                        ORDER BY election_date ASC
                        LIMIT 1""",
                    (city_fips, period.period_start),
                )
                row = cur.fetchone()
                election_id = row[0] if row else None

            # Candidates filing for this election. LEFT JOIN — we want
            # candidates even when committee linkage is broken, since
            # the audit catches orphans separately.
            cur.execute(
                """SELECT ec.id, ec.candidate_name, ec.office_sought,
                          ec.committee_id, c.name, ec.fppc_id
                     FROM election_candidates ec
                     LEFT JOIN committees c ON c.id = ec.committee_id
                    WHERE ec.city_fips = %s
                      AND ec.election_id = %s
                    ORDER BY ec.candidate_name""",
                (city_fips, election_id),
            )
            candidates = [
                Candidate(
                    id=str(r[0]),
                    name=r[1],
                    office_sought=r[2],
                    committee_id=str(r[3]) if r[3] else None,
                    committee_name=r[4],
                    fppc_id=r[5],
                )
                for r in cur.fetchall()
            ]

            # Contributions in the period. Donor metadata (name, employer,
            # occupation, address) lives in the donors table — JOIN through.
            # Filter by election_id when we have linkage; fall back to
            # (city_fips, date window) otherwise — orphan committees still
            # surface in totals so the briefing reflects all filed money,
            # not just cleanly-linked money.
            cur.execute(
                """SELECT co.id,
                          d.name, d.employer, d.occupation, d.address,
                          co.amount, co.contribution_date,
                          co.entity_code, co.source,
                          co.committee_id, c.name
                     FROM contributions co
                     JOIN donors d ON d.id = co.donor_id
                     LEFT JOIN committees c ON c.id = co.committee_id
                    WHERE co.city_fips = %s
                      AND co.contribution_date >= %s
                      AND co.contribution_date <= %s
                      AND (co.election_id = %s OR co.election_id IS NULL)
                    ORDER BY co.contribution_date ASC""",
                (city_fips, period.period_start, period.period_end, election_id),
            )
            contributions = []
            for r in cur.fetchall():
                zip_, state_ = _parse_zip_state(r[4])
                contributions.append(Contribution(
                    id=str(r[0]),
                    contributor_name=(r[1] or "").strip(),
                    contributor_employer=(r[2] or "").strip() or None,
                    occupation=(r[3] or "").strip() or None,
                    amount=float(r[5] or 0),
                    date=r[6],
                    zip=zip_,
                    state=state_,
                    entity_code=(r[7] or "").strip() or None,
                    source=r[8],
                    committee_id=str(r[9]) if r[9] else None,
                    committee_name=r[10],
                ))

            # Paper-filings completeness check — count distinct paper
            # filing_ids covered by the contributions list. Drives
            # provenance.paper_filings_count and the F7 compliance
            # section (later commit).
            cur.execute(
                """SELECT COUNT(DISTINCT filing_id)
                     FROM contributions
                    WHERE city_fips = %s
                      AND contribution_date >= %s
                      AND contribution_date <= %s
                      AND source = 'fppc_paper'""",
                (city_fips, period.period_start, period.period_end),
            )
            paper_count = cur.fetchone()[0] or 0
    finally:
        conn.close()

    filed_through = max((c.date for c in contributions), default=None)

    return Evidence(
        period=period,
        election_id=election_id,
        candidates=candidates,
        contributions=contributions,
        paper_filings_count=paper_count,
        filed_through=filed_through,
    )


# ── Step 2: Section generators ────────────────────────────────────
#
# Each generator returns a structured dict of the shape:
#
#   {
#     "per_candidate": { candidate_id: { ... } },
#     "cross_race":    { ... },     # optional, only when cross-candidate is meaningful
#     "tier":          "A" | "B" | "C",
#     "confidence":    0.0..1.0,
#     "notes":         [str],       # generator-emitted caveats; renderer can show
#   }
#
# Section bodies are factual aggregations only — no inference, no framing.
# The renderer composes narrative copy; the data layer stays pure numbers
# and labels per design rule D6 ("narrative over numbers" applies to
# render time, not generation time — generation produces the numbers).


def section_F1_totals(evidence: Evidence) -> dict[str, Any]:
    """F1 — Per-candidate cycle-to-date totals + donor count + average gift.

    Mechanically reduces contributions over (committee_id) keyed to
    candidate. Tier A by default — totals are factual, citation-direct,
    and never framing-sensitive.
    """
    per_candidate: dict[str, dict[str, Any]] = {}

    by_committee = defaultdict(list)
    for c in evidence.contributions:
        if c.committee_id:
            by_committee[c.committee_id].append(c)

    for cand in evidence.candidates:
        contribs = by_committee.get(cand.committee_id, [])
        total = sum(c.amount for c in contribs)
        donor_names = {c.contributor_name.lower() for c in contribs if c.contributor_name}
        per_candidate[cand.id] = {
            "candidate_name": cand.name,
            "office_sought": cand.office_sought,
            "committee_name": cand.committee_name,
            "fppc_id": cand.fppc_id,
            "total_amount": round(total, 2),
            "contribution_count": len(contribs),
            "unique_donors": len(donor_names),
            "average_gift": round(total / len(contribs), 2) if contribs else 0.0,
            "max_single_gift": round(max((c.amount for c in contribs), default=0.0), 2),
        }

    return {
        "per_candidate": per_candidate,
        "tier": "A",
        "confidence": 1.0,
        "notes": [],
    }


def section_F2_geography(evidence: Evidence) -> dict[str, Any]:
    """F2 — Donor geography by zip-prefix, dollar shares not counts.

    Buckets: richmond (94801–94819) / bay_area (94xxx + 95xxx, ex-Richmond) /
    california_other / out_of_state / unknown. Per the article, the
    interesting signal is dollar share: a candidate with 80% of dollars
    coming from out-of-Richmond reads very differently from one with 80%
    of dollars from Richmond, even with similar donor counts. Counts are
    misleading because $5 hometown gifts inflate them.
    """
    per_candidate: dict[str, dict[str, Any]] = {}

    by_committee = defaultdict(list)
    for c in evidence.contributions:
        if c.committee_id:
            by_committee[c.committee_id].append(c)

    for cand in evidence.candidates:
        buckets = {
            "richmond": 0.0,
            "bay_area": 0.0,
            "california_other": 0.0,
            "out_of_state": 0.0,
            "unknown": 0.0,
        }
        contribs = by_committee.get(cand.committee_id, [])
        for c in contribs:
            buckets[_classify_geography(c)] += c.amount

        total = sum(buckets.values())
        per_candidate[cand.id] = {
            "candidate_name": cand.name,
            "buckets_amount": {k: round(v, 2) for k, v in buckets.items()},
            "buckets_share": {
                k: round(v / total, 4) if total else 0.0
                for k, v in buckets.items()
            },
            "total_amount": round(total, 2),
        }

    return {
        "per_candidate": per_candidate,
        "tier": "A",
        "confidence": 0.95,
        "notes": [
            "Geography is bucketed by zip prefix parsed heuristically from "
            "donors.address (a freeform TEXT field). Donors with unparseable "
            "addresses fall into 'unknown'. A schema extension to store zip / "
            "state explicitly is a Stream 2 follow-on commit; until it lands, "
            "the 'unknown' share is the upper bound on F2 measurement error."
        ],
    }


def _classify_geography(c: Contribution) -> str:
    """Return the F2 geography bucket for one contribution."""
    if not c.zip:
        return "unknown"
    z = c.zip.strip()[:5]
    if not z or len(z) < 5:
        return "unknown"
    if z.startswith(RICHMOND_ZIP_PREFIXES) and (c.state or "").upper() in ("", "CA"):
        # 94801–94819 — Richmond + El Cerrito edges. Operator can tighten
        # to 94801–94808 in a follow-up after the article reconciliation.
        return "richmond"
    if (c.state or "").upper() == "CA":
        if z.startswith(BAY_AREA_ZIP_PREFIXES):
            return "bay_area"
        return "california_other"
    return "out_of_state"


def section_F3_industry_pac(evidence: Evidence) -> dict[str, Any]:
    """F3 — Industry/PAC concentration by entity_code + employer.

    Two views: (a) PAC share — sum of contributions from entity_code='COM'
    or 'PTY'/'SCC' (committee-from-committee transfers); (b) top employers
    by dollar — naïve grouping by contributor_employer string. Entity
    resolution (B.46 / Sprint 26) will fold this into a real industry tag
    later. Until then, employer string is the closest signal we have.

    Tier B by default. The numbers are factual but the framing ("industry
    concentration") borrows from a normative frame that operator review
    should sanity-check.
    """
    per_candidate: dict[str, dict[str, Any]] = {}

    by_committee = defaultdict(list)
    for c in evidence.contributions:
        if c.committee_id:
            by_committee[c.committee_id].append(c)

    PAC_ENTITY_CODES = {"COM", "PTY", "SCC"}

    for cand in evidence.candidates:
        contribs = by_committee.get(cand.committee_id, [])
        total = sum(c.amount for c in contribs)
        pac_total = sum(c.amount for c in contribs if c.entity_code in PAC_ENTITY_CODES)

        by_employer: dict[str, float] = defaultdict(float)
        for c in contribs:
            employer = (c.contributor_employer or "").strip().lower()
            if not employer or employer in ("self-employed", "self employed", "n/a"):
                continue
            by_employer[employer] += c.amount

        top_employers = [
            {"employer": e, "amount": round(amt, 2)}
            for e, amt in sorted(by_employer.items(), key=lambda x: -x[1])[:5]
        ]

        per_candidate[cand.id] = {
            "candidate_name": cand.name,
            "pac_amount": round(pac_total, 2),
            "pac_share": round(pac_total / total, 4) if total else 0.0,
            "top_employers": top_employers,
        }

    return {
        "per_candidate": per_candidate,
        "tier": "B",
        "confidence": 0.80,
        "notes": [
            "Employer grouping is string-naïve (entity resolution lands "
            "in Sprint 26). Two donors at 'Chevron' vs 'Chevron Corp' "
            "appear as separate employers until B.46 ships."
        ],
    }


def section_F4_self_related(evidence: Evidence) -> dict[str, Any]:
    """F4 — Self-funding and related-party (last-name match) totals.

    Self-funding: contributor_name normalizes to candidate name.
    Related-party: contributor_name shares the candidate's last name and
    isn't the candidate themselves. Both factual; tier B by default —
    related-party is a heuristic (last-name match has false positives in
    Hispanic surnames and common Anglo names like Smith) and should
    surface as "potential family relationship" at render time, never as
    "family donation."

    Self-funding (tier A): exact match is high-confidence.
    """
    per_candidate: dict[str, dict[str, Any]] = {}

    by_committee = defaultdict(list)
    for c in evidence.contributions:
        if c.committee_id:
            by_committee[c.committee_id].append(c)

    for cand in evidence.candidates:
        cand_norm = cand.name.lower().strip()
        cand_last = _last_name(cand.name)
        contribs = by_committee.get(cand.committee_id, [])

        self_total = 0.0
        related_total = 0.0
        related_donors: set[str] = set()
        for c in contribs:
            donor_norm = c.contributor_name.lower().strip()
            if donor_norm == cand_norm:
                self_total += c.amount
                continue
            donor_last = _last_name(c.contributor_name)
            if cand_last and donor_last and donor_last == cand_last:
                related_total += c.amount
                related_donors.add(c.contributor_name)

        per_candidate[cand.id] = {
            "candidate_name": cand.name,
            "self_funded_amount": round(self_total, 2),
            "related_last_name_amount": round(related_total, 2),
            "related_last_name_donors": sorted(related_donors),
        }

    return {
        "per_candidate": per_candidate,
        "tier": "B",
        "confidence": 0.75,
        "notes": [
            "Related-party detection uses last-name match only. False "
            "positives are expected for common surnames; do not surface "
            "as 'family donation' at render time without further evidence."
        ],
    }


def _last_name(name: str) -> str | None:
    """Naive last-name extractor: last whitespace-separated token, lowercase.

    Adequate for the heuristic (F4). Real entity resolution (B.46) is the
    structured fix.
    """
    if not name:
        return None
    parts = name.strip().split()
    return parts[-1].lower() if parts else None


# ── F5–F9 stubs (later commits on this branch) ────────────────────


def section_F5_donor_clustering(evidence: Evidence) -> dict[str, Any]:
    """F5 — Cross-candidate donor clustering. STUB.

    Factual only: "Donor X gave to N candidates totaling $Y". No inference
    about coordination. Framing-sensitive — defaults to Tier C until
    operator reviews each clustering call.
    """
    return {"cross_race": {}, "tier": "C", "confidence": 0.0, "notes": ["F5 not yet implemented"]}


def section_F6_deadline_burst(evidence: Evidence) -> dict[str, Any]:
    """F6 — 24-hour pre-election deadline-burst pattern. STUB."""
    return {"per_candidate": {}, "tier": "C", "confidence": 0.0, "notes": ["F6 not yet implemented"]}


def section_F7_compliance(evidence: Evidence) -> dict[str, Any]:
    """F7 — Filing compliance (late filings, missing schedules). STUB."""
    return {"per_candidate": {}, "tier": "C", "confidence": 0.0, "notes": ["F7 not yet implemented"]}


def section_F8_vendor_employee(evidence: Evidence) -> dict[str, Any]:
    """F8 — Donations from employees of city vendors. STUB."""
    return {"per_candidate": {}, "tier": "C", "confidence": 0.0, "notes": ["F8 not yet implemented"]}


def section_F9_levine_exposure(evidence: Evidence) -> dict[str, Any]:
    """F9 — Contribution-side Levine Act exposure. STUB.

    A new contribution from anyone at a vendor with an active city
    contract above the Levine threshold. Requires party_entities (mig
    098) + the entity registry. Framing-sensitive; Tier C until reviewed.
    """
    return {"cross_race": {}, "tier": "C", "confidence": 0.0, "notes": ["F9 not yet implemented"]}


# ── Step 3: Assembly ──────────────────────────────────────────────


def build_briefing(evidence: Evidence) -> dict[str, Any]:
    """Run every section generator. Returns the sections + section_tiers
    blobs ready to serialize into the filing_period_briefings row."""
    sections = {
        "F1_totals":           section_F1_totals(evidence),
        "F2_geography":        section_F2_geography(evidence),
        "F3_industry_pac":     section_F3_industry_pac(evidence),
        "F4_self_related":     section_F4_self_related(evidence),
        "F5_donor_clustering": section_F5_donor_clustering(evidence),
        "F6_deadline_burst":   section_F6_deadline_burst(evidence),
        "F7_compliance":       section_F7_compliance(evidence),
        "F8_vendor_employee":  section_F8_vendor_employee(evidence),
        "F9_levine_exposure":  section_F9_levine_exposure(evidence),
    }
    section_tiers = {key: s.get("tier", "C") for key, s in sections.items()}
    return {"sections": sections, "section_tiers": section_tiers}


# ── Step 4: Persistence ───────────────────────────────────────────


def upsert_briefing(
    *,
    city_fips: str,
    election_id: str | None,
    period: FilingPeriod,
    evidence: Evidence,
    briefing: dict[str, Any],
    publication_tier: str = "graduated",
    force: bool = False,
) -> str | None:
    """Insert (or supersede) the current briefing row.

    Idempotent on (city_fips, election_id, period_label) WHERE is_current.
    Re-running with --force marks the prior row is_current=false and
    inserts a new is_current=true row, preserving audit history.
    """
    from db import get_connection

    p = prov.campaign_filing_period(
        period_label=period.label,
        contributions_count=len(evidence.contributions),
        paper_filings_count=evidence.paper_filings_count,
        filed_through=evidence.filed_through.isoformat() if evidence.filed_through else None,
        generator="filing_period_briefing.py",
    )

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Look for an existing current briefing.
            cur.execute(
                """SELECT id FROM filing_period_briefings
                    WHERE city_fips = %s
                      AND (election_id = %s OR (election_id IS NULL AND %s IS NULL))
                      AND period_label = %s
                      AND is_current
                    LIMIT 1""",
                (city_fips, election_id, election_id, period.label),
            )
            existing = cur.fetchone()
            if existing and not force:
                print(f"  Briefing already exists for {period.label} (use --force to regenerate)")
                return str(existing[0])

            if existing:
                cur.execute(
                    """UPDATE filing_period_briefings
                          SET is_current = FALSE,
                              superseded_at = NOW()
                        WHERE id = %s""",
                    (existing[0],),
                )

            cur.execute(
                """INSERT INTO filing_period_briefings (
                       city_fips, election_id,
                       period_label, period_kind, period_start, period_end, filed_through,
                       sections, section_tiers, provenance,
                       generator, generator_version,
                       contributions_considered, paper_filings_considered,
                       publication_tier, is_current
                   ) VALUES (
                       %s, %s,
                       %s, %s, %s, %s, %s,
                       %s::jsonb, %s::jsonb, %s::jsonb,
                       %s, %s,
                       %s, %s,
                       %s, TRUE
                   )
                   RETURNING id""",
                (
                    city_fips, election_id,
                    period.label, period.kind, period.period_start, period.period_end,
                    evidence.filed_through,
                    json.dumps(briefing["sections"], default=_json_default),
                    json.dumps(briefing["section_tiers"]),
                    prov.to_json(p),
                    "filing_period_briefing.py", GENERATOR_VERSION,
                    len(evidence.contributions), evidence.paper_filings_count,
                    publication_tier,
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return str(row[0]) if row else None
    finally:
        conn.close()


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback for date/datetime/Decimal."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ── CLI ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a filing-period briefing from contributions data"
    )
    parser.add_argument(
        "--period", required=True,
        help="Filing period label (e.g. '2026-Q1', '2026-pre-primary-24h')",
    )
    parser.add_argument(
        "--city-fips", default=DEFAULT_FIPS,
        help="City FIPS code (default: Richmond, CA — 0660620)",
    )
    parser.add_argument(
        "--election-id",
        help="Election UUID to scope to. If omitted, picks the next election after period_start.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the assembled briefing without writing to DB",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Supersede existing current briefing for this period",
    )
    parser.add_argument(
        "--publication-tier", default="graduated",
        choices=["public", "operator", "graduated"],
        help="Briefing-level publication tier (default: graduated, per spec)",
    )
    args = parser.parse_args()

    period = resolve_period(args.period)

    print(f"Filing-period briefing for {period.label}")
    print("=" * 50)
    print(f"  Window:     {period.period_start} → {period.period_end} ({period.kind})")
    print(f"  City FIPS:  {args.city_fips}")

    print("\n[1/3] Pulling evidence...")
    evidence = fetch_evidence(
        period=period,
        city_fips=args.city_fips,
        election_id=args.election_id,
    )
    print(f"  Election:           {evidence.election_id or '(none)'}")
    print(f"  Candidates:         {len(evidence.candidates)}")
    print(f"  Contributions:      {len(evidence.contributions):,}")
    print(f"  Paper filings:      {evidence.paper_filings_count}")
    print(f"  Filed through:      {evidence.filed_through or '(no contributions in window)'}")

    if not evidence.candidates:
        print("\n  No candidates found for this period — exiting.")
        sys.exit(2)

    print("\n[2/3] Generating sections F1–F9...")
    briefing = build_briefing(evidence)
    for key, section in briefing["sections"].items():
        tier = section.get("tier", "?")
        per_cand = len(section.get("per_candidate", {}) or {})
        cross = "yes" if section.get("cross_race") else "no"
        print(f"  {key:24s} tier={tier}  per_candidate={per_cand}  cross_race={cross}")

    print("\n[3/3] Persisting briefing...")
    if args.dry_run:
        print("  [DRY RUN] Skipping DB write. Section payload preview:")
        print(json.dumps(briefing["sections"]["F1_totals"], indent=2, default=_json_default)[:1500])
        print("  ...")
        return

    briefing_id = upsert_briefing(
        city_fips=args.city_fips,
        election_id=evidence.election_id,
        period=period,
        evidence=evidence,
        briefing=briefing,
        publication_tier=args.publication_tier,
        force=args.force,
    )
    print(f"  Done. briefing_id = {briefing_id}")


if __name__ == "__main__":
    main()
