"""Article-as-oracle test for filing_period_briefing.

Pins per-candidate Q1 2026 mayoral totals from the Richmondside article
("Richmond mayoral candidates' campaign finance reports", 2026-04-27,
https://richmondside.org/2026/04/27/richmond-mayoral-candidates-campaign-finance-reports/)
as tolerance-bounded assertions. The article is the closest-to-ground-truth
public reckoning we have — when our totals diverge from it, that's the
signal to chase down a data-quality bug.

The article reports figures "through April 18, 2026", so this fixture
slices Evidence at that cutoff. Tolerance is intentionally generous
($500) to absorb late-amendment timing noise without burying real
divergences. As I124 items (2) cross-committee dedup and (3) canonical
donor names land, the assertions tighten through code; this file does
not need to be edited, just re-run.

Each candidate also asserts a donor count in a similarly generous range
because article totals are sometimes rounded and often exclude
"contributions of $100 or less" itemization rules — the count signal is
weaker than the dollar signal.

Run with `PYTHONIOENCODING=utf-8` if Windows console emits UnicodeEncodeError.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)

# These tests hit the live database — skip in CI without secrets.
_HAS_DB = bool(os.getenv("DATABASE_URL")) and "test" not in (os.getenv("DATABASE_URL") or "")

pytestmark = pytest.mark.skipif(
    not _HAS_DB,
    reason="DATABASE_URL missing or placeholder (CI without secrets)",
)


# ── Article ground truth ─────────────────────────────────────────
#
# Source: Richmondside, "Richmond mayoral candidates' campaign finance
# reports" (2026-04-27). The article reports cycle-to-date figures
# "through April 18, 2026". Tolerances are tuned to absorb the noise
# we expect from:
#   - rounding in the article's narrative ("about $40,500")
#   - paper-filing extraction not yet caught up (some 4/15-4/18 filings)
#   - cross-committee Form 497 dedup not yet shipped (I124 item 2)
#
# When this fixture starts passing without the wide tolerances, the
# data quality work has converged. Tighten by editing TOLERANCE_USD
# downward in a future commit — the article values themselves are
# canonical and should not move.

ELECTION_ID = "8f49a3f9-1ca2-46ab-92d2-f28e27cefd69"  # Richmond June 2026 Primary
ARTICLE_CUTOFF = date(2026, 4, 18)
TOLERANCE_USD = 500.0  # see header

# (candidate_name_lower_substring, expected_total_usd, expected_donor_count_min)
# donor_count_min is a floor — the article cites donor counts loosely so
# we only check we're not way under (which would be a load failure) or
# way over (which would be a dedup failure).
ARTICLE_TOTALS: list[tuple[str, float, int, int]] = [
    # (substring, expected_total, donor_count_min, donor_count_max)
    ("anderson",   40_500.00, 80, 200),
    ("jimenez",    31_000.00, 40, 150),
    ("johnson",     7_500.00, 10,  80),
    ("martinez",    6_000.00, 10,  80),
    ("wassberg",        0.00,  0,  10),
]


# ── Helpers ──────────────────────────────────────────────────────


def _build_evidence_through_cutoff():
    """Pull Q1 2026 evidence and slice contributions at ARTICLE_CUTOFF.

    The briefing's normal period_end is 2026-04-24 (filing deadline). The
    article reports "through April 18", so the fixture must enforce its
    own narrower cutoff to compare apples to apples.
    """
    import sys
    sys.path.insert(0, str(_ROOT / "src"))
    from filing_period_briefing import (  # noqa: E402
        Evidence, fetch_evidence, resolve_period, section_F1_totals,
    )

    period = resolve_period("2026-Q1")
    evidence = fetch_evidence(
        period=period,
        city_fips="0660620",
        election_id=ELECTION_ID,
    )

    # Slice to article cutoff. Re-wrap in a new Evidence so downstream
    # generators see a coherent struct (paper_filings_count is loose
    # here — only the contributions list matters for F1 totals).
    sliced = Evidence(
        period=period,
        election_id=evidence.election_id,
        candidates=evidence.candidates,
        contributions=[c for c in evidence.contributions if c.date <= ARTICLE_CUTOFF],
        paper_filings_count=evidence.paper_filings_count,
        filed_through=max(
            (c.date for c in evidence.contributions if c.date <= ARTICLE_CUTOFF),
            default=None,
        ),
    )
    return sliced, section_F1_totals(sliced)


def _find_candidate(per_candidate: dict, name_substring: str) -> tuple[str, dict]:
    """Locate the per_candidate entry whose name contains the substring."""
    for cand_id, row in per_candidate.items():
        if name_substring.lower() in row["candidate_name"].lower():
            return cand_id, row
    raise AssertionError(
        f"No candidate matching {name_substring!r} in F1 output. "
        f"Got: {[r['candidate_name'] for r in per_candidate.values()]}"
    )


# ── Tests ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def f1_through_cutoff():
    """Module-scoped because fetch_evidence hits Supabase — one call per run."""
    return _build_evidence_through_cutoff()


@pytest.mark.parametrize(
    "name_substring, expected_total, donor_min, donor_max",
    ARTICLE_TOTALS,
    ids=[t[0] for t in ARTICLE_TOTALS],
)
def test_candidate_total_matches_article(
    f1_through_cutoff, name_substring, expected_total, donor_min, donor_max
):
    """Per-candidate Q1 2026 total reconciles to the Richmondside article.

    Tolerance is wide on purpose (see header). The point is to track
    convergence as I124 fixes ship, not to gate CI on perfect agreement.
    """
    _, f1 = f1_through_cutoff
    _, row = _find_candidate(f1["per_candidate"], name_substring)

    actual_total = row["total_amount"]
    diff = abs(actual_total - expected_total)
    assert diff <= TOLERANCE_USD, (
        f"{row['candidate_name']}: DB total ${actual_total:,.2f} "
        f"vs article ${expected_total:,.2f} (diff ${diff:,.2f}). "
        f"Tolerance is ${TOLERANCE_USD:.0f}. "
        f"Likely causes: cross-committee 497 duplication (I124 item 2), "
        f"canonical-name drift on Vision-extracted donors (I124 item 3), "
        f"or genuinely missing paper filings."
    )


@pytest.mark.parametrize(
    "name_substring, expected_total, donor_min, donor_max",
    ARTICLE_TOTALS,
    ids=[t[0] for t in ARTICLE_TOTALS],
)
def test_candidate_donor_count_in_range(
    f1_through_cutoff, name_substring, expected_total, donor_min, donor_max
):
    """Donor count is in a generous floor/ceiling range.

    Floor catches the "we're missing whole filings" failure mode.
    Ceiling catches the "we're double-counting due to alias drift" mode.
    """
    _, f1 = f1_through_cutoff
    _, row = _find_candidate(f1["per_candidate"], name_substring)

    unique_donors = row["unique_donors"]
    assert donor_min <= unique_donors <= donor_max, (
        f"{row['candidate_name']}: {unique_donors} unique donors, "
        f"expected {donor_min}-{donor_max}. "
        f"Below floor = missing data; above ceiling = alias drift."
    )


def test_no_pre_period_dollars_in_q1_total(f1_through_cutoff):
    """Q1 totals should not include pre-2026 contributions.

    Catches a regression where the period filter falls back to "all
    contributions ever" — the briefing window is filing-deadline-aligned
    and inclusive of 2026-01-01 onward only.
    """
    sliced, _ = f1_through_cutoff
    pre_2026 = [c for c in sliced.contributions if c.date < date(2026, 1, 1)]
    assert not pre_2026, (
        f"Found {len(pre_2026)} contributions dated before 2026-01-01 "
        f"in the Q1 evidence base. Earliest: {min(c.date for c in pre_2026)}."
    )


def test_anderson_q1_includes_paper_filings(f1_through_cutoff):
    """Anderson is a paper filer — Q1 total should reflect Vision OCR rows.

    Pre-OCR baseline was ~$5K (4 donors). Post-OCR the article expects
    ~$40K (~120 donors). If we regress under $20K, the paper extractor
    has stopped contributing — most likely a Vision OCR fallback failure
    that landed silently.
    """
    _, f1 = f1_through_cutoff
    _, row = _find_candidate(f1["per_candidate"], "anderson")
    assert row["total_amount"] > 20_000, (
        f"Anderson total ${row['total_amount']:,.2f} is suspiciously low. "
        f"Paper-filing extraction may have regressed — check "
        f"src/data/paper_filings/anderson_mayor_2026.json freshness and "
        f"netfile_paper_extractor.py Vision OCR path."
    )
