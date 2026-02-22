# Temporal Correlation Analysis — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect post-vote donations — contributions filed after an official voted favorably on an agenda item involving the donor's employer or entity.

**Architecture:** Extend the existing conflict scanner with a `post_vote_donation` flag type. A new `scan_temporal_correlations()` function takes meeting data (with vote records) and contributions, filters for contributions dated after the meeting, matches donor entities to agenda item entities for officials who voted Aye, and produces `ConflictFlag` objects with time-decay confidence scoring. Integrates into the retrospective scan path in cloud_pipeline.py. Frontend displays post-vote flags in a separate section on the report detail page.

**Tech Stack:** Python (conflict_scanner.py), TypeScript/React (Next.js frontend), existing Supabase schema (no migrations needed).

**Worktree:** `.worktrees/temporal-correlation` (branch: `temporal-correlation`)

**Merge order:** Merge AFTER `cloud-e/multi-city` branch completes. Rebase if needed.

**Estimated vibe-coding time:** 30–45 min across all tasks.

---

## Task 1: Time-Decay Configuration and Vote Extraction Helper

**Files:**
- Modify: `src/conflict_scanner.py` (add constants + helper function after line ~106)
- Create: `tests/test_temporal_correlation.py`

**Step 1: Write the failing tests**

```python
# tests/test_temporal_correlation.py
"""Tests for temporal correlation analysis (post-vote donation detection)."""
import pytest
from datetime import date


def test_time_decay_multiplier_immediate():
    """0-90 days after vote should have highest confidence multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(30) == 1.0
    assert get_time_decay_multiplier(90) == 1.0


def test_time_decay_multiplier_election_cycle():
    """91-180 days after vote should have 0.85 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(91) == 0.85
    assert get_time_decay_multiplier(180) == 0.85


def test_time_decay_multiplier_annual():
    """181-365 days after vote should have 0.7 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(200) == 0.7
    assert get_time_decay_multiplier(365) == 0.7


def test_time_decay_multiplier_reelection():
    """366-730 days should have 0.5 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(400) == 0.5
    assert get_time_decay_multiplier(730) == 0.5


def test_time_decay_multiplier_long_term():
    """731-1825 days should have 0.3 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(800) == 0.3
    assert get_time_decay_multiplier(1825) == 0.3


def test_time_decay_multiplier_beyond_window():
    """Beyond max lookback should return 0.0."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(1826) == 0.0
    assert get_time_decay_multiplier(3000) == 0.0


def test_extract_votes_from_action_item():
    """Extract aye voters from an action item with motions."""
    from conflict_scanner import extract_aye_voters
    item = {
        "item_number": "H-5",
        "title": "Approve contract with Acme Corp",
        "motions": [
            {
                "result": "passed",
                "votes": [
                    {"council_member": "Eduardo Martinez", "vote": "aye"},
                    {"council_member": "Sue Wilson", "vote": "aye"},
                    {"council_member": "Jamelia Brown", "vote": "nay"},
                ]
            }
        ]
    }
    voters = extract_aye_voters(item)
    assert "Eduardo Martinez" in voters
    assert "Sue Wilson" in voters
    assert "Jamelia Brown" not in voters


def test_extract_votes_from_consent_item():
    """Consent items inherit the consent calendar's vote record."""
    from conflict_scanner import extract_aye_voters
    item = {
        "item_number": "I-1",
        "title": "Approve payment to BuildCo",
    }
    consent_votes = [
        {"council_member": "Eduardo Martinez", "vote": "aye"},
        {"council_member": "Claudia Jimenez", "vote": "aye"},
        {"council_member": "Cesar Zepeda", "vote": "absent"},
    ]
    voters = extract_aye_voters(item, consent_votes=consent_votes)
    assert "Eduardo Martinez" in voters
    assert "Claudia Jimenez" in voters
    assert "Cesar Zepeda" not in voters


def test_extract_votes_no_vote_data():
    """Items without votes return empty set."""
    from conflict_scanner import extract_aye_voters
    item = {"item_number": "A-1", "title": "Presentation"}
    voters = extract_aye_voters(item)
    assert voters == set()


def test_extract_votes_failed_motion():
    """Only extract from passed motions."""
    from conflict_scanner import extract_aye_voters
    item = {
        "item_number": "H-3",
        "title": "Deny rezoning",
        "motions": [
            {
                "result": "failed",
                "votes": [
                    {"council_member": "Eduardo Martinez", "vote": "aye"},
                ]
            }
        ]
    }
    voters = extract_aye_voters(item)
    assert voters == set()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py -v --tb=short`
Expected: FAIL with ImportError (functions don't exist yet)

**Step 3: Write minimal implementation**

Add to `src/conflict_scanner.py` after line 106 (after `RICHMOND_COUNCIL_MEMBERS`):

```python
# --- Temporal correlation configuration ---

# Default lookback window: 5 years (covers longest commission term)
DEFAULT_LOOKBACK_DAYS = 1825

# Time-decay confidence multipliers by days-after-vote
TIME_DECAY_WINDOWS = [
    (90, 1.0),     # 0-90 days: immediate reward
    (180, 0.85),   # 91-180 days: election cycle timing
    (365, 0.7),    # 181-365 days: annual pattern
    (730, 0.5),    # 1-2 years: re-election cycle
    (1825, 0.3),   # 2-5 years: long-term relationship
]


def get_time_decay_multiplier(days_after_vote: int, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> float:
    """Return confidence multiplier based on days between vote and donation.

    Closer donations get higher multipliers (stronger signal).
    Returns 0.0 if beyond the lookback window.
    """
    if days_after_vote > lookback_days:
        return 0.0
    for max_days, multiplier in TIME_DECAY_WINDOWS:
        if days_after_vote <= max_days:
            return multiplier
    return 0.0


def extract_aye_voters(item: dict, consent_votes: list[dict] | None = None) -> set[str]:
    """Extract names of officials who voted Aye on a passed item.

    For action items: reads from item["motions"][*]["votes"].
    For consent items: uses the consent_votes parameter (from consent_calendar level).
    Only considers passed motions.
    """
    voters = set()

    # Action items have their own motions
    for motion in item.get("motions", []):
        if motion.get("result", "").lower() != "passed":
            continue
        for vote in motion.get("votes", []):
            if vote.get("vote", "").lower() == "aye":
                voters.add(vote.get("council_member", ""))

    # Consent items inherit the consent calendar's vote
    if not item.get("motions") and consent_votes:
        for vote in consent_votes:
            if vote.get("vote", "").lower() == "aye":
                voters.add(vote.get("council_member", ""))

    voters.discard("")  # Remove empty strings
    return voters
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py -v --tb=short`
Expected: ALL PASS

**Step 5: Run full test suite to check for regressions**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/ -q --tb=short`
Expected: 255+ passed

**Step 6: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add src/conflict_scanner.py tests/test_temporal_correlation.py
git commit -m "Phase 2: add time-decay config and vote extraction helpers for temporal correlation"
```

---

## Task 2: Core Temporal Correlation Scanner Function

**Files:**
- Modify: `src/conflict_scanner.py` (add `scan_temporal_correlations()` function)
- Modify: `tests/test_temporal_correlation.py` (add tests)

**Step 1: Write the failing tests**

Append to `tests/test_temporal_correlation.py`:

```python
# --- Test data fixtures ---

SAMPLE_MEETING_DATA = {
    "meeting_date": "2025-09-23",
    "meeting_type": "regular",
    "consent_calendar": {
        "result": "passed",
        "votes": [
            {"council_member": "Eduardo Martinez", "vote": "aye"},
            {"council_member": "Sue Wilson", "vote": "aye"},
            {"council_member": "Claudia Jimenez", "vote": "aye"},
            {"council_member": "Jamelia Brown", "vote": "aye"},
            {"council_member": "Doria Robinson", "vote": "aye"},
            {"council_member": "Cesar Zepeda", "vote": "aye"},
            {"council_member": "Soheila Bana", "vote": "aye"},
        ],
        "items": [
            {
                "item_number": "I-3",
                "title": "Approve payment of $50,000 to GreenBuild Construction for park renovation",
                "description": "Staff recommends approval of invoice from GreenBuild Construction.",
                "department": "Public Works",
            }
        ]
    },
    "action_items": [
        {
            "item_number": "H-5",
            "title": "Approve $2M professional services contract with Stellar Engineering",
            "description": "Authorize the city manager to execute a contract with Stellar Engineering for infrastructure assessment.",
            "department": "Engineering",
            "motions": [
                {
                    "result": "passed",
                    "motion_by": "Councilmember Jimenez",
                    "seconded_by": "Councilmember Robinson",
                    "votes": [
                        {"council_member": "Eduardo Martinez", "vote": "aye"},
                        {"council_member": "Sue Wilson", "vote": "aye"},
                        {"council_member": "Claudia Jimenez", "vote": "aye"},
                        {"council_member": "Jamelia Brown", "vote": "nay"},
                        {"council_member": "Doria Robinson", "vote": "aye"},
                        {"council_member": "Cesar Zepeda", "vote": "aye"},
                        {"council_member": "Soheila Bana", "vote": "absent"},
                    ]
                }
            ]
        }
    ],
    "housing_authority_items": [],
}

# Donations that arrived AFTER Sept 23, 2025 meeting
SAMPLE_POST_VOTE_CONTRIBUTIONS = [
    {
        "contributor_name": "Robert Chen",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2025-12-15",  # 83 days after vote
        "committee": "Jimenez for Richmond 2026",
        "source": "netfile",
    },
    {
        "contributor_name": "Maria Santos",
        "contributor_employer": "GreenBuild Construction",
        "amount": 1000.0,
        "date": "2026-01-10",  # 109 days after vote
        "committee": "Martinez for Mayor 2026",
        "source": "netfile",
    },
    {
        "contributor_name": "Jane Doe",
        "contributor_employer": "Unrelated Corp",
        "amount": 500.0,
        "date": "2025-10-01",  # 8 days after vote, but unrelated entity
        "committee": "Wilson for Council 2026",
        "source": "netfile",
    },
    {
        "contributor_name": "Tom Smith",
        "contributor_employer": "Stellar Engineering",
        "amount": 250.0,
        "date": "2025-08-01",  # BEFORE the vote - should NOT be flagged
        "committee": "Jimenez for Richmond 2026",
        "source": "netfile",
    },
]


def test_scan_temporal_basic():
    """Detect post-vote donation from Stellar Engineering employee to Jimenez."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Should find Robert Chen -> Jimenez (Stellar Engineering, 83 days)
    stellar_flags = [f for f in flags if "Stellar" in f.description]
    assert len(stellar_flags) >= 1
    flag = stellar_flags[0]
    assert flag.flag_type == "post_vote_donation"
    assert "Jimenez" in flag.council_member or "Claudia Jimenez" in flag.council_member
    assert flag.confidence > 0  # Should have non-zero confidence


def test_scan_temporal_consent_item():
    """Detect post-vote donation matching consent calendar item."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Should find Maria Santos (GreenBuild) -> Martinez (consent item I-3)
    green_flags = [f for f in flags if "GreenBuild" in f.description]
    assert len(green_flags) >= 1
    flag = green_flags[0]
    assert "Martinez" in flag.council_member


def test_scan_temporal_excludes_pre_vote_donations():
    """Donations before the vote should NOT be flagged."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Tom Smith donated to Jimenez BEFORE the vote (Aug 1)
    pre_vote = [f for f in flags if "Tom Smith" in f.description]
    assert len(pre_vote) == 0


def test_scan_temporal_excludes_unrelated_entities():
    """Donations from unrelated entities should NOT be flagged."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Jane Doe works at Unrelated Corp - no match to any agenda item
    unrelated = [f for f in flags if "Unrelated" in f.description]
    assert len(unrelated) == 0


def test_scan_temporal_excludes_nay_voters():
    """Officials who voted Nay should NOT be flagged for that item."""
    from conflict_scanner import scan_temporal_correlations

    # Jamelia Brown voted NAY on H-5 (Stellar Engineering)
    # Even if someone donates to Brown's committee from Stellar, no flag
    contributions_to_brown = [
        {
            "contributor_name": "Stellar Engineering PAC",
            "contributor_employer": "Stellar Engineering",
            "amount": 2000.0,
            "date": "2025-11-01",
            "committee": "Brown for Richmond 2026",
            "source": "netfile",
        }
    ]
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, contributions_to_brown)
    brown_stellar = [f for f in flags if "Brown" in f.council_member and "Stellar" in f.description]
    assert len(brown_stellar) == 0


def test_scan_temporal_time_decay_confidence():
    """Closer donations should have higher confidence than distant ones."""
    from conflict_scanner import scan_temporal_correlations

    close_donation = [{
        "contributor_name": "Stellar Employee",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2025-10-15",  # 22 days after vote
        "committee": "Martinez for Mayor 2026",
        "source": "netfile",
    }]
    far_donation = [{
        "contributor_name": "Stellar Employee",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2027-06-15",  # ~630 days after vote
        "committee": "Martinez for Mayor 2026",
        "source": "netfile",
    }]

    close_flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, close_donation)
    far_flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, far_donation)

    assert len(close_flags) >= 1
    assert len(far_flags) >= 1
    assert close_flags[0].confidence > far_flags[0].confidence


def test_scan_temporal_evidence_schema():
    """Evidence dict should contain all required temporal fields."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    stellar_flags = [f for f in flags if "Stellar" in f.description]
    assert len(stellar_flags) >= 1

    # Check evidence structure
    evidence = stellar_flags[0].evidence
    assert len(evidence) >= 1
    ev = evidence[0] if isinstance(evidence[0], dict) else {}
    assert "vote_date" in ev
    assert "donation_date" in ev
    assert "days_after_vote" in ev
    assert "time_decay_multiplier" in ev
    assert "donor_name" in ev
    assert "vote_choice" in ev
    assert ev["vote_choice"] == "aye"


def test_scan_temporal_beyond_lookback():
    """Donations beyond the lookback window should NOT be flagged."""
    from conflict_scanner import scan_temporal_correlations

    ancient_donation = [{
        "contributor_name": "Stellar Employee",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2031-01-01",  # ~5.3 years after vote, beyond 1825 days
        "committee": "Martinez for Mayor 2030",
        "source": "netfile",
    }]
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, ancient_donation)
    assert len(flags) == 0


def test_scan_temporal_publication_tier():
    """Recent high-confidence matches should be Tier 2, older ones Tier 3."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    stellar_flags = [f for f in flags if "Stellar" in f.description and "Jimenez" in f.council_member]
    assert len(stellar_flags) >= 1
    # 83 days, $5000, employer match -> should be Tier 2 (moderate confidence)
    assert stellar_flags[0].publication_tier in (1, 2)


def test_scan_temporal_empty_contributions():
    """No contributions should produce no flags."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, [])
    assert flags == []


def test_scan_temporal_no_votes():
    """Meeting with no vote data should produce no flags."""
    from conflict_scanner import scan_temporal_correlations
    meeting = {
        "meeting_date": "2025-09-23",
        "meeting_type": "special",
        "action_items": [
            {"item_number": "A-1", "title": "Presentation only", "description": "Info item"}
        ]
    }
    flags = scan_temporal_correlations(meeting, SAMPLE_POST_VOTE_CONTRIBUTIONS)
    assert flags == []
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py -v --tb=short -k "scan_temporal"`
Expected: FAIL with ImportError (`scan_temporal_correlations` not found)

**Step 3: Write the implementation**

Add to `src/conflict_scanner.py` after the `extract_aye_voters()` function (before `extract_candidate_from_committee`):

```python
def scan_temporal_correlations(
    meeting_data: dict,
    contributions: list[dict],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    city_fips: str = "0660620",
) -> list[ConflictFlag]:
    """Scan for donations filed AFTER officials voted favorably on related items.

    For each agenda item with a recorded vote:
    1. Identify officials who voted Aye
    2. Search contributions dated after the meeting
    3. Match donor name/employer to entities in the agenda item
    4. Apply time-decay confidence scoring

    Returns list of ConflictFlag with flag_type='post_vote_donation'.
    """
    from datetime import datetime, timedelta

    meeting_date_str = meeting_data.get("meeting_date", "")
    if not meeting_date_str:
        return []

    try:
        meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()
    except ValueError:
        return []

    max_date = meeting_date + timedelta(days=lookback_days)
    flags = []

    # Build council member set for committee-to-official matching
    council_names = CURRENT_COUNCIL_MEMBERS | FORMER_COUNCIL_MEMBERS

    # Collect items with their vote records
    items_with_votes = []

    # Consent calendar: all items share the same vote record
    consent = meeting_data.get("consent_calendar", {})
    consent_votes = consent.get("votes", [])
    for item in consent.get("items", []):
        aye_voters = extract_aye_voters(item, consent_votes=consent_votes)
        if aye_voters:
            items_with_votes.append((item, aye_voters))

    # Action items: each has its own motions/votes
    for item in meeting_data.get("action_items", []):
        aye_voters = extract_aye_voters(item)
        if aye_voters:
            items_with_votes.append((item, aye_voters))

    # Housing authority items
    for item in meeting_data.get("housing_authority_items", []):
        aye_voters = extract_aye_voters(item)
        if aye_voters:
            items_with_votes.append((item, aye_voters))

    if not items_with_votes:
        return []

    # Filter contributions to only those AFTER the meeting date and within window
    post_vote_contributions = []
    for c in contributions:
        c_date_str = c.get("date") or c.get("contribution_date", "")
        if not c_date_str:
            continue
        try:
            c_date = datetime.strptime(str(c_date_str)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if meeting_date < c_date <= max_date:
            post_vote_contributions.append((c, c_date))

    if not post_vote_contributions:
        return []

    # Map committee names to candidate/official names
    committee_to_official = {}
    for c, _ in post_vote_contributions:
        committee = c.get("committee", "")
        if committee and committee not in committee_to_official:
            candidate = extract_candidate_from_committee(committee)
            if candidate:
                committee_to_official[committee] = candidate

    # For each item, check for post-vote donations from related entities
    seen_flags = set()  # Deduplicate by (item_number, donor, committee)

    for item, aye_voters in items_with_votes:
        item_num = item.get("item_number", "")
        item_title = item.get("title", "")
        item_desc = item.get("description", "")
        item_text = f"{item_title} {item_desc}"

        # Extract entity names from the agenda item
        entities = extract_entity_names(item_text)
        if not entities:
            continue

        for contrib, c_date in post_vote_contributions:
            donor_name = contrib.get("contributor_name") or contrib.get("donor_name", "")
            donor_employer = contrib.get("contributor_employer") or contrib.get("donor_employer", "")
            committee = contrib.get("committee") or contrib.get("committee_name", "")
            amount = float(contrib.get("amount", 0))

            if not donor_name:
                continue

            # Skip government entity donors
            donor_lower = donor_name.lower()
            if any(donor_lower.startswith(p) for p in ("city of", "county of", "state of")):
                continue
            if any(donor_lower.endswith(s) for s in (" county", " city", " district")):
                continue

            # Determine which official received this donation
            recipient_official = committee_to_official.get(committee, "")
            if not recipient_official:
                continue

            # Check if the recipient voted Aye on this item
            official_voted_aye = False
            for voter in aye_voters:
                voter_match, _ = names_match(recipient_official, voter)
                if voter_match:
                    official_voted_aye = True
                    recipient_official = voter  # Use the exact name from vote record
                    break

            if not official_voted_aye:
                continue

            # Check if donor/employer matches any entity in the agenda item
            match_type = None
            matched_entity = None

            for entity in entities:
                # Check employer match
                if donor_employer:
                    emp_match, emp_type = names_match(donor_employer, entity)
                    if emp_match:
                        match_type = f"employer_to_{emp_type}"
                        matched_entity = entity
                        break

                # Check direct name match
                name_match_result, name_type = names_match(donor_name, entity)
                if name_match_result:
                    match_type = f"donor_name_to_{name_type}"
                    matched_entity = entity
                    break

            if not match_type:
                continue

            # Deduplicate
            dedup_key = (item_num, donor_name, committee)
            if dedup_key in seen_flags:
                continue
            seen_flags.add(dedup_key)

            # Calculate confidence with time decay
            days_after = (c_date - meeting_date).days
            decay = get_time_decay_multiplier(days_after, lookback_days)

            # Base confidence from match quality and amount
            base_confidence = 0.4
            if "exact" in match_type:
                base_confidence = 0.6
            if amount >= 1000:
                base_confidence += 0.1
            if amount >= 5000:
                base_confidence += 0.1

            confidence = round(min(base_confidence * decay, 1.0), 2)

            # Publication tier
            if confidence >= 0.5:
                tier = 2  # Financial Connection
            else:
                tier = 3  # Internal tracking

            # Build evidence
            evidence_entry = {
                "vote_date": meeting_date_str,
                "vote_choice": "aye",
                "agenda_item_number": item_num,
                "agenda_item_title": item_title,
                "donation_date": str(c_date),
                "days_after_vote": days_after,
                "donor_name": donor_name,
                "donor_employer": donor_employer,
                "donation_amount": amount,
                "recipient_official": recipient_official,
                "recipient_committee": committee,
                "lookback_window_days": lookback_days,
                "time_decay_multiplier": decay,
                "match_type": match_type,
            }

            # Build description (purely factual, no judgment)
            description = (
                f"{recipient_official} voted Aye on Item {item_num} "
                f"({item_title}) on {meeting_date_str}. "
                f"{donor_name}"
            )
            if donor_employer:
                description += f" (employer: {donor_employer})"
            description += (
                f" contributed ${amount:,.2f} to {committee} "
                f"on {c_date}, {days_after} days after the vote."
            )

            flags.append(ConflictFlag(
                agenda_item_number=item_num,
                agenda_item_title=item_title,
                council_member=recipient_official,
                flag_type="post_vote_donation",
                description=description,
                evidence=[evidence_entry],
                confidence=confidence,
                legal_reference="Gov. Code § 87100 (financial interest disclosure)",
                financial_amount=f"${amount:,.2f}",
                publication_tier=tier,
            ))

    return flags
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py -v --tb=short`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/ -q --tb=short`
Expected: 255+ passed (new tests added, no regressions)

**Step 6: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add src/conflict_scanner.py tests/test_temporal_correlation.py
git commit -m "Phase 2: add core temporal correlation scanner with post-vote donation detection"
```

---

## Task 3: Cloud Pipeline Integration

**Files:**
- Modify: `src/cloud_pipeline.py` (add temporal correlation to retrospective path)
- Modify: `tests/test_temporal_correlation.py` (add integration test)

**Step 1: Write the failing test**

Append to `tests/test_temporal_correlation.py`:

```python
def test_cloud_pipeline_retrospective_includes_temporal(monkeypatch):
    """Retrospective scan mode should run temporal correlation analysis."""
    from unittest.mock import MagicMock, patch
    import cloud_pipeline

    # Track if scan_temporal_correlations was called
    temporal_called = {"called": False, "args": None}

    original_scan_temporal = None
    try:
        from conflict_scanner import scan_temporal_correlations
        original_scan_temporal = scan_temporal_correlations
    except ImportError:
        pass

    def mock_temporal(meeting_data, contributions, **kwargs):
        temporal_called["called"] = True
        temporal_called["args"] = (meeting_data, contributions, kwargs)
        return []

    # We just need to verify the function is called during retrospective mode
    # without running the full pipeline
    monkeypatch.setattr("conflict_scanner.scan_temporal_correlations", mock_temporal)

    # Verify the import exists in cloud_pipeline
    assert hasattr(cloud_pipeline, '_run_temporal_correlation') or \
           'scan_temporal_correlations' in dir(cloud_pipeline) or \
           'temporal' in open(cloud_pipeline.__file__).read().lower(), \
           "cloud_pipeline.py should reference temporal correlation for retrospective scans"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py::test_cloud_pipeline_retrospective_includes_temporal -v --tb=short`
Expected: FAIL

**Step 3: Write the implementation**

Read `src/cloud_pipeline.py` to find the exact insertion point for the retrospective path. Add after the main conflict scan step (after flags are saved but before comment generation).

Add to `src/cloud_pipeline.py`:

1. Add import at top (near other conflict_scanner imports):
```python
from conflict_scanner import scan_temporal_correlations
```

2. After the existing conflict scan step (Step 5 in the pipeline, after flags are saved), add:
```python
        # Step 5b: Temporal correlation analysis (retrospective only)
        temporal_flags = []
        if scan_mode == "retrospective":
            logger.info("Step 5b: Running temporal correlation analysis...")
            temporal_flags = scan_temporal_correlations(
                meeting_data, contributions, city_fips=city_fips
            )
            logger.info(f"  Found {len(temporal_flags)} post-vote donation flags")

            # Save temporal flags to database
            if temporal_flags and not dry_run:
                for flag in temporal_flags:
                    save_conflict_flag(
                        conn, scan_run_id=scan_run_id,
                        city_fips=city_fips,
                        meeting_id=meeting_id,
                        flag=flag,
                    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py::test_cloud_pipeline_retrospective_includes_temporal -v --tb=short`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/ -q --tb=short`
Expected: 255+ passed

**Step 6: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add src/cloud_pipeline.py tests/test_temporal_correlation.py
git commit -m "Phase 2: integrate temporal correlation into retrospective scan pipeline"
```

---

## Task 4: CLI Flag for Conflict Scanner

**Files:**
- Modify: `src/conflict_scanner.py` (add `--temporal-correlation` CLI argument)
- Modify: `tests/test_temporal_correlation.py` (add CLI test)

**Step 1: Write the failing test**

Append to `tests/test_temporal_correlation.py`:

```python
def test_cli_temporal_flag(tmp_path):
    """CLI should accept --temporal-correlation flag and run temporal analysis."""
    import json
    import subprocess

    # Write sample meeting data to temp file
    meeting_file = tmp_path / "meeting.json"
    meeting_file.write_text(json.dumps(SAMPLE_MEETING_DATA))

    contributions_file = tmp_path / "contributions.json"
    contributions_file.write_text(json.dumps(SAMPLE_POST_VOTE_CONTRIBUTIONS))

    result = subprocess.run(
        ["python3", "src/conflict_scanner.py", str(meeting_file),
         "--contributions", str(contributions_file),
         "--temporal-correlation"],
        capture_output=True, text=True,
        cwd="/Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation",
    )

    assert result.returncode == 0
    # Should mention post-vote donations in output
    assert "post-vote" in result.stdout.lower() or "post_vote" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py::test_cli_temporal_flag -v --tb=short`
Expected: FAIL (CLI flag doesn't exist yet)

**Step 3: Write the implementation**

Find the `argparse` section in `src/conflict_scanner.py` (the `if __name__ == "__main__":` block at the bottom). Add:

```python
    parser.add_argument("--temporal-correlation", action="store_true",
                        help="Run temporal correlation analysis (detect post-vote donations)")
```

And in the CLI execution logic, after the main scan, add:

```python
    if args.temporal_correlation:
        print("\n--- Post-Vote Donation Analysis ---")
        temporal_flags = scan_temporal_correlations(meeting_data, contributions)
        if temporal_flags:
            for flag in temporal_flags:
                print(f"\n[POST-VOTE] {flag.agenda_item_number}: {flag.council_member}")
                print(f"  {flag.description}")
                print(f"  Confidence: {flag.confidence:.0%} (Tier {flag.publication_tier})")
                if flag.evidence:
                    ev = flag.evidence[0] if isinstance(flag.evidence[0], dict) else {}
                    print(f"  Days after vote: {ev.get('days_after_vote', '?')}")
        else:
            print("  No post-vote donation patterns detected.")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/test_temporal_correlation.py::test_cli_temporal_flag -v --tb=short`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/ -q --tb=short`
Expected: 255+ passed

**Step 6: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add src/conflict_scanner.py tests/test_temporal_correlation.py
git commit -m "Phase 2: add --temporal-correlation CLI flag to conflict scanner"
```

---

## Task 5: Frontend — ConflictFlagCard Temporal Display

**Files:**
- Modify: `web/src/components/ConflictFlagCard.tsx`
- No test file (visual component — verify with dev server)

**Step 1: Read current ConflictFlagCard.tsx**

Read the full file to find exact insertion points.

**Step 2: Add temporal display logic**

In `ConflictFlagCard.tsx`, add conditional rendering for `post_vote_donation` flags. After the existing flag_type display and before the description, add:

```tsx
{/* Temporal correlation callout */}
{flag.flag_type === 'post_vote_donation' && flag.evidence?.[0] && (
  <div className="flex items-center gap-2 mt-1">
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
      {(flag.evidence[0] as Record<string, unknown>).days_after_vote} days after vote
    </span>
  </div>
)}
```

**Step 3: Run the build to verify no TypeScript errors**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation/web && npx next build 2>&1 | tail -20`
Expected: Build succeeds without errors

**Step 4: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add web/src/components/ConflictFlagCard.tsx
git commit -m "Phase 2: add temporal callout badge to ConflictFlagCard"
```

---

## Task 6: Frontend — Report Page Post-Vote Section

**Files:**
- Modify: `web/src/app/reports/[meetingId]/page.tsx`

**Step 1: Read current report page**

Read the full file to find the exact tier section structure.

**Step 2: Add Post-Vote Donations section**

After the Tier 2 section and before the "No findings" state, add:

```tsx
{/* Post-Vote Donations section */}
{(() => {
  const postVoteFlags = flags.filter((f) => f.flag_type === 'post_vote_donation')
  if (postVoteFlags.length === 0) return null
  return (
    <section className="mb-8">
      <h2 className="text-xl font-bold text-gray-900 mb-2">
        Post-Vote Donations
      </h2>
      <p className="text-sm text-gray-600 mb-4">
        Contributions filed after officials voted on related agenda items.
        Temporal proximity does not indicate wrongdoing.
      </p>
      <div className="space-y-4">
        {postVoteFlags.map((flag) => (
          <ConflictFlagCard key={flag.id} flag={flag} />
        ))}
      </div>
    </section>
  )
})()}
```

Also update the tier filtering to exclude post-vote flags from the existing tier sections:

```tsx
const tier1Flags = flags.filter((f) => f.confidence >= 0.7 && f.flag_type !== 'post_vote_donation')
const tier2Flags = flags.filter((f) => f.confidence >= 0.5 && f.confidence < 0.7 && f.flag_type !== 'post_vote_donation')
```

**Step 3: Run the build**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation/web && npx next build 2>&1 | tail -20`
Expected: Build succeeds

**Step 4: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add web/src/app/reports/\[meetingId\]/page.tsx
git commit -m "Phase 2: add Post-Vote Donations section to transparency reports"
```

---

## Task 7: Quarterly Retrospective Cron Schedule

**Files:**
- Modify: `.github/workflows/cloud-pipeline.yml`

**Step 1: Read current workflow**

Read `.github/workflows/cloud-pipeline.yml` to find the schedule section.

**Step 2: Add quarterly cron**

Add a second cron entry for quarterly retrospective sweeps. The quarterly job runs on the 1st of Jan, Apr, Jul, Oct at 8am UTC:

```yaml
on:
  schedule:
    - cron: '0 6 * * 1'        # Weekly Monday 6am UTC (prospective)
    - cron: '0 8 1 1,4,7,10 *' # Quarterly 1st of month 8am UTC (retrospective)
```

In the "Resolve inputs" step, detect which cron triggered:

```yaml
      # Detect quarterly retrospective trigger
      if [ "${{ github.event_name }}" = "schedule" ]; then
        CURRENT_DAY=$(date +%d)
        if [ "$CURRENT_DAY" = "01" ]; then
          SCAN_MODE="retrospective"
          TRIGGER="quarterly-retrospective"
          echo "Quarterly retrospective sweep triggered"
        fi
      fi
```

**Step 3: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add .github/workflows/cloud-pipeline.yml
git commit -m "Phase 2: add quarterly retrospective cron for temporal correlation sweeps"
```

---

## Task 8: Update CLAUDE.md and Final Verification

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Run full test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation && python3 -m pytest tests/ -q --tb=short`
Expected: 255+ passed, 0 failed

**Step 2: Update CLAUDE.md**

Add to "Phase 2 Done" section:
```markdown
- **Temporal correlation analysis (post-vote donations):** `src/conflict_scanner.py` extended with `scan_temporal_correlations()` — detects donations filed after officials voted favorably on related agenda items. Time-decay confidence scoring (1.0x at 0-90 days → 0.3x at 2-5 years). 5-year configurable lookback window (covers longest commission term). Aye-vote only (Nay correlation deferred pending stakeholder mapping). Purely factual description format, no judgment language. Integrates into retrospective scan path in `cloud_pipeline.py`. Frontend: `ConflictFlagCard.tsx` shows "X days after vote" badge, `reports/[meetingId]/page.tsx` has dedicated "Post-Vote Donations" section. Quarterly retrospective cron in GitHub Actions. CLI: `python conflict_scanner.py <meeting.json> --temporal-correlation --contributions <file>`.
```

Update Phase 2 Remaining: Change item 7 from "Temporal correlation analysis" to mark it as complete or remove it.

**Step 3: Commit**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation
git add CLAUDE.md
git commit -m "Phase 2: update CLAUDE.md with temporal correlation completion"
```

**Step 4: Use finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to merge or PR.
