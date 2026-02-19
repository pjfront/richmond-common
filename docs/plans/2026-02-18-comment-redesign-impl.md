# Comment Output Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the public comment output with three-tier finding classification, narrative formatting, and bug fixes so the comment reads like an investigative report rather than code output.

**Architecture:** The scanner (`conflict_scanner.py`) gains a `publication_tier` field on each `ConflictFlag`. The comment generator (`comment_generator.py`) filters by tier and renders findings as narrative paragraphs using a new Jinja2 template. Two output formats share the same data model: plain text (Phase 1) and HTML (Phase 2, template stub only).

**Tech Stack:** Python 3, Jinja2, pytest (new — install for this project)

---

## Prerequisites

Install pytest (not currently in the project):

```bash
pip install pytest
echo "pytest>=7.0.0" >> requirements.txt
```

All tests run from the repo root: `python -m pytest tests/ -v`

All source imports assume `src/` is on the Python path. Tests add `src/` to `sys.path` at the top of each test file.

---

### Task 1: Set Up Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_conflict_scanner_tiers.py`

**Step 1: Create test directories and conftest**

```bash
mkdir -p tests
touch tests/__init__.py
```

Write `tests/conftest.py`:

```python
"""Shared test fixtures for Richmond Transparency Project."""
import sys
from pathlib import Path

# Add src/ to Python path so we can import project modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

**Step 2: Write the first failing test — tier assignment for a sitting-member exact match**

Write `tests/test_conflict_scanner_tiers.py`:

```python
"""Tests for ConflictFlag.publication_tier assignment."""
import pytest
from conflict_scanner import ConflictFlag


def test_tier1_sitting_member_exact_match_high_amount():
    """Sitting council member + exact name match + >= $500 = Tier 1."""
    flag = ConflictFlag(
        agenda_item_number="V.6.a",
        agenda_item_title="Approve Contract with Maier Consulting",
        council_member="Sue Wilson (sitting council member)",
        flag_type="campaign_contribution",
        description="Cheryl Maier contributed $5,000.00 to Wilson for Richmond 2024",
        evidence=["Source: netfile, Filing ID: 211752889"],
        confidence=0.7,
        legal_reference="Gov. Code SS 87100-87105",
        financial_amount="$1,217,161",
        publication_tier=1,
    )
    assert flag.publication_tier == 1


def test_tier2_sitting_member_employer_match():
    """Sitting council member + employer match (weaker) = Tier 2."""
    flag = ConflictFlag(
        agenda_item_number="V.3.a",
        agenda_item_title="Approve Maintenance Contract",
        council_member="Eduardo Martinez (sitting council member)",
        flag_type="campaign_contribution",
        description="James Torres (Pacific Environmental) contributed $200",
        evidence=["Source: calaccess, Filing ID: 2345678"],
        confidence=0.5,
        legal_reference="Gov. Code SS 87100-87105",
        financial_amount="$85,000",
        publication_tier=2,
    )
    assert flag.publication_tier == 2


def test_tier3_non_sitting_candidate():
    """Donation to a former/failed candidate = Tier 3 (suppressed)."""
    flag = ConflictFlag(
        agenda_item_number="V.6",
        agenda_item_title="Library and Community Services",
        council_member="Oscar Garcia (not a current council member)",
        flag_type="campaign_contribution",
        description="Cheryl Maier contributed $100.00 to Oscar Garcia for Richmond City Council 2022",
        evidence=["Source: netfile, Filing ID: 204807209"],
        confidence=0.3,
        legal_reference="Gov. Code SS 87100-87105",
        financial_amount="$1,217,161",
        publication_tier=3,
    )
    assert flag.publication_tier == 3
```

**Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_conflict_scanner_tiers.py -v`

Expected: FAIL — `ConflictFlag.__init__() got an unexpected keyword argument 'publication_tier'`

**Step 4: Commit test infrastructure**

```bash
git add tests/ requirements.txt
git commit -m "Phase 1: add test infrastructure and tier assignment tests (red)"
```

---

### Task 2: Add `publication_tier` Field to ConflictFlag

**Files:**
- Modify: `src/conflict_scanner.py` — lines 29-39 (`ConflictFlag` dataclass)

**Step 1: Add the field to the dataclass**

In `src/conflict_scanner.py`, add `publication_tier` to the `ConflictFlag` dataclass after `financial_amount`:

```python
@dataclass
class ConflictFlag:
    """A potential conflict of interest detected by the scanner."""
    agenda_item_number: str
    agenda_item_title: str
    council_member: str
    flag_type: str           # 'campaign_contribution', 'vendor_donor_match', 'form700_real_property', 'form700_income'
    description: str
    evidence: list[str]
    confidence: float        # 0.0-1.0
    legal_reference: str
    financial_amount: Optional[str] = None  # from the agenda item
    publication_tier: int = 3  # 1=Potential Conflict, 2=Financial Connection, 3=internal only
```

**Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_conflict_scanner_tiers.py -v`

Expected: 3 PASSED

**Step 3: Commit**

```bash
git add src/conflict_scanner.py
git commit -m "Phase 1: add publication_tier field to ConflictFlag dataclass"
```

---

### Task 3: Assign Tiers in the Scanner

**Files:**
- Modify: `src/conflict_scanner.py` — lines 536-604 (flag creation block in `scan_meeting_json`)
- Create: `tests/test_scanner_tier_assignment.py`

**Step 1: Write failing test — scanner auto-assigns tiers based on confidence + sitting status**

Write `tests/test_scanner_tier_assignment.py`:

```python
"""Tests that scan_meeting_json assigns publication_tier correctly."""
import pytest
from conflict_scanner import scan_meeting_json


def _make_meeting(items):
    """Helper to build minimal meeting JSON."""
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "members_present": [],
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


def _make_contribution(donor_name, amount, committee, employer="", date="2024-01-01", source="netfile"):
    """Helper to build a contribution dict."""
    return {
        "donor_name": donor_name,
        "donor_employer": employer,
        "council_member": "",
        "committee_name": committee,
        "amount": amount,
        "date": date,
        "filing_id": "TEST-001",
        "source": source,
    }


def test_sitting_member_exact_match_gets_tier1():
    """Exact donor name match + sitting member + high confidence = Tier 1."""
    meeting = _make_meeting([{
        "item_number": "V.1.a",
        "title": "Approve Contract with National Auto Fleet Group for Vehicle Purchases",
        "description": "Purchase 10 vehicles from National Auto Fleet Group.",
        "category": "contracts",
        "financial_amount": "$450,000",
    }])
    contributions = [
        _make_contribution(
            "National Auto Fleet Group", 4900.00,
            "Jimenez for Richmond City Council 2024",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    flag = result.flags[0]
    assert flag.publication_tier == 1  # sitting member, exact, high amount


def test_non_sitting_candidate_gets_tier3():
    """Donation to a former/failed candidate = Tier 3."""
    meeting = _make_meeting([{
        "item_number": "V.6.a",
        "title": "Approve Contract with Maier Consulting for Library Design",
        "description": "Professional services agreement with Cheryl Maier.",
        "category": "contracts",
        "financial_amount": "$100,000",
    }])
    contributions = [
        _make_contribution(
            "Cheryl Maier", 100.00,
            "Oscar Garcia for Richmond City Council 2022",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    for flag in result.flags:
        assert flag.publication_tier == 3  # non-sitting candidate


def test_sitting_member_employer_match_low_amount_gets_tier2():
    """Sitting member + employer match + low amount = Tier 2."""
    meeting = _make_meeting([{
        "item_number": "V.3.a",
        "title": "Approve Contract with Gallagher Benefit Services for Employee Benefits",
        "description": "Annual benefits administration contract with Gallagher Benefit Services.",
        "category": "contracts",
        "financial_amount": "$200,000",
    }])
    contributions = [
        _make_contribution(
            "Sarah Whitfield", 200.00,
            "Wilson for Richmond 2024",
            employer="Gallagher Benefit Services",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    flag = result.flags[0]
    assert flag.publication_tier == 2  # sitting member, but employer match + low amount
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scanner_tier_assignment.py -v`

Expected: FAIL — `publication_tier` defaults to 3 for all flags.

**Step 3: Add tier assignment logic in scanner**

In `src/conflict_scanner.py`, in the `scan_meeting_json` function, right before the `flags.append(ConflictFlag(...))` call (around line 593), compute the tier:

Replace the existing block (lines ~593-604):

```python
            # Assign publication tier based on confidence and sitting status.
            # Tier 1: Potential Conflict — sitting member, high confidence
            # Tier 2: Financial Connection — sitting member, lower confidence
            # Tier 3: Internal only — non-sitting recipient, suppressed from comment
            if sitting and confidence >= 0.6:
                tier = 1
            elif sitting and confidence >= 0.4:
                tier = 2
            else:
                tier = 3

            flags.append(ConflictFlag(
                agenda_item_number=item_num,
                agenda_item_title=item_title,
                council_member=council_member_label,
                flag_type="campaign_contribution",
                description=description,
                evidence=evidence,
                confidence=min(confidence, 1.0),
                legal_reference="Gov. Code SS 87100-87105, 87300 (financial interest in governmental decision)",
                financial_amount=financial,
                publication_tier=tier,
            ))
            flagged_items.add(item_num)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scanner_tier_assignment.py -v`

Expected: 3 PASSED

**Step 5: Also run the tier dataclass tests to make sure nothing broke**

Run: `python -m pytest tests/ -v`

Expected: 6 PASSED

**Step 6: Commit**

```bash
git add src/conflict_scanner.py tests/test_scanner_tier_assignment.py
git commit -m "Phase 1: assign publication_tier in scanner based on confidence + sitting status"
```

---

### Task 4: Fix Bug — Empty Recipient Field on PAC Contributions

**Files:**
- Modify: `src/conflict_scanner.py` — lines 536-543 (council_member_label logic)
- Create: `tests/test_scanner_bugs.py`

**Step 1: Write failing test**

Write `tests/test_scanner_bugs.py`:

```python
"""Tests for scanner bug fixes."""
import pytest
from conflict_scanner import ConflictFlag, scan_meeting_json


def _make_meeting(items):
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "members_present": [],
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


def _make_contribution(**kwargs):
    defaults = {
        "donor_name": "", "donor_employer": "", "council_member": "",
        "committee_name": "", "amount": 0, "date": "2024-01-01",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


class TestEmptyRecipientBug:
    """Bug: PAC contributions produce empty council_member field."""

    def test_pac_contribution_shows_pac_name(self):
        """When committee is a PAC (no candidate extractable),
        council_member should show the PAC/committee name."""
        meeting = _make_meeting([{
            "item_number": "V.5.a",
            "title": "Approve Fire Department Overtime Budget",
            "description": "Budget allocation for fire department overtime.",
            "category": "budget",
            "financial_amount": "$30,494",
        }])
        contributions = [
            _make_contribution(
                donor_name="Rico Rincon",
                donor_employer="Some Company",
                committee_name="Independent PAC Local 188 International Association of Firefighters",
                amount=2500.00,
            ),
        ]
        result = scan_meeting_json(meeting, contributions)
        # Find the flag for this item
        flags_for_item = [f for f in result.flags if f.agenda_item_number == "V.5.a"]
        if flags_for_item:
            flag = flags_for_item[0]
            # council_member should NOT be empty
            assert flag.council_member != ""
            assert flag.council_member is not None
            # Should contain the PAC name
            assert "PAC" in flag.council_member or "Local 188" in flag.council_member


class TestNoneEmployerBug:
    """Bug: employer displays as '(None)' or '(n/a)' in output."""

    def test_none_employer_not_displayed(self):
        """Employer field should be empty string when value is None/n/a."""
        meeting = _make_meeting([{
            "item_number": "V.6.a",
            "title": "Approve Contract with Cheryl Maier Consulting",
            "description": "Professional services with Cheryl Maier.",
            "category": "contracts",
            "financial_amount": "$100,000",
        }])
        contributions = [
            _make_contribution(
                donor_name="Cheryl Maier",
                donor_employer="n/a",
                committee_name="Wilson for Richmond 2024",
                amount=500.00,
            ),
        ]
        result = scan_meeting_json(meeting, contributions)
        flags_for_item = [f for f in result.flags if f.agenda_item_number == "V.6.a"]
        if flags_for_item:
            flag = flags_for_item[0]
            # Description should NOT contain "(n/a)" or "(None)"
            assert "(n/a)" not in flag.description
            assert "(None)" not in flag.description
            assert "(none)" not in flag.description
            assert "(N/A)" not in flag.description
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scanner_bugs.py -v`

Expected: At least one FAIL

**Step 3: Fix the empty recipient bug**

In `src/conflict_scanner.py`, replace the `council_member_label` logic (around lines 536-543):

```python
            # Determine the candidate who received the contribution
            # and whether they currently sit on the council
            candidate = extract_candidate_from_committee(rep["committee"])
            sitting = is_sitting_council_member(candidate) if candidate else False
            council_member_label = rep["council_member"]  # may be empty
            if candidate:
                if sitting:
                    council_member_label = f"{candidate} (sitting council member)"
                else:
                    council_member_label = f"{candidate} (not a current council member)"
            elif not council_member_label:
                # PAC/IE committee with no extractable candidate name —
                # use the committee name itself so the field isn't blank
                council_member_label = rep["committee"]
```

**Step 4: Fix the None employer bug**

In `src/conflict_scanner.py`, replace the `employer_note` line (around line 558):

```python
            # Filter out meaningless employer values before display
            raw_employer = rep["donor_employer"] or ""
            cleaned_employer = raw_employer.strip()
            if cleaned_employer.lower() in {"", "none", "n/a", "na", "not employed", "unemployed", "-"}:
                cleaned_employer = ""
            employer_note = f" ({cleaned_employer})" if cleaned_employer else ""
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_scanner_bugs.py -v`

Expected: PASSED

**Step 6: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All PASSED

**Step 7: Commit**

```bash
git add src/conflict_scanner.py tests/test_scanner_bugs.py
git commit -m "Phase 1: fix empty recipient on PAC contributions, fix None employer display"
```

---

### Task 5: Redesign Comment Template — Narrative Format

**Files:**
- Modify: `src/comment_generator.py` — replace `COMMENT_TEMPLATE` (lines 100-167)
- Create: `tests/test_comment_generator.py`

**Step 1: Write failing test — tier filtering and narrative output**

Write `tests/test_comment_generator.py`:

```python
"""Tests for comment generator redesign."""
import pytest
from conflict_scanner import ConflictFlag, ScanResult
from comment_generator import generate_comment_from_scan, MissingDocument


def _make_scan_result(flags=None, clean_items=None):
    """Helper to build a ScanResult."""
    return ScanResult(
        meeting_date="2026-02-17",
        meeting_type="regular",
        total_items_scanned=27,
        flags=flags or [],
        vendor_matches=[],
        clean_items=clean_items or [],
        enriched_items=[],
    )


def _make_flag(tier, **overrides):
    """Helper to build a ConflictFlag with sensible defaults."""
    defaults = {
        "agenda_item_number": "V.1.a",
        "agenda_item_title": "Approve Contract with Acme Corp",
        "council_member": "Sue Wilson (sitting council member)",
        "flag_type": "campaign_contribution",
        "description": "John Doe contributed $5,000.00 to Wilson for Richmond 2024 on 2024-01-06",
        "evidence": ["Source: netfile, Filing ID: 211752889"],
        "confidence": 0.7,
        "legal_reference": "Gov. Code SS 87100-87105, 87300",
        "financial_amount": "$500,000",
        "publication_tier": tier,
    }
    defaults.update(overrides)
    return ConflictFlag(**defaults)


class TestTierFiltering:
    """Comment generator should only include Tier 1 and Tier 2 findings."""

    def test_tier1_appears_in_output(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "POTENTIAL CONFLICTS OF INTEREST" in comment
        assert "Acme Corp" in comment

    def test_tier2_appears_in_separate_section(self):
        flag = _make_flag(tier=2, confidence=0.5)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "ADDITIONAL FINANCIAL CONNECTIONS" in comment
        assert "Acme Corp" in comment

    def test_tier3_suppressed_from_output(self):
        flag = _make_flag(
            tier=3,
            confidence=0.3,
            council_member="Oscar Garcia (not a current council member)",
        )
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Oscar Garcia" not in comment
        assert "POTENTIAL CONFLICTS" not in comment

    def test_mixed_tiers_in_correct_sections(self):
        tier1 = _make_flag(tier=1, agenda_item_number="V.1.a",
                           agenda_item_title="Big Contract with AlphaCo")
        tier2 = _make_flag(tier=2, agenda_item_number="V.3.a",
                           agenda_item_title="Small Contract with BetaCo",
                           confidence=0.5)
        tier3 = _make_flag(tier=3, agenda_item_number="V.6",
                           agenda_item_title="Suppressed Item",
                           confidence=0.3)
        result = _make_scan_result(flags=[tier1, tier2, tier3])
        comment = generate_comment_from_scan(result)
        assert "AlphaCo" in comment
        assert "BetaCo" in comment
        assert "Suppressed Item" not in comment


class TestNarrativeFormat:
    """Comment should read as prose, not code output."""

    def test_no_raw_confidence_scores(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Confidence:" not in comment
        assert "70%" not in comment

    def test_no_evidence_bullet_list(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Evidence:" not in comment

    def test_item_title_in_plain_english(self):
        flag = _make_flag(tier=1, agenda_item_title="Approve Contract with Acme Corp for Consulting Services")
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Approve Contract with Acme Corp for Consulting Services" in comment

    def test_legal_context_in_plain_english(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        # Should contain plain English legal explanation
        assert "Gov. Code" in comment or "Political Reform Act" in comment


class TestCleanItemsSummary:
    """Clean items should show summary count, not item numbers."""

    def test_clean_items_shows_count(self):
        result = _make_scan_result(
            clean_items=["V.1", "V.2", "V.3", "V.4", "V.5"],
        )
        comment = generate_comment_from_scan(result)
        assert "5 additional agenda items were scanned" in comment
        # Should NOT list individual item numbers
        assert "V.1, V.2" not in comment


class TestEmailPlaceholder:
    """Email should be filled in, not placeholder."""

    def test_contact_email_present(self):
        result = _make_scan_result()
        comment = generate_comment_from_scan(result)
        assert "pjfront@gmail.com" in comment
        assert "[email]" not in comment
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_comment_generator.py -v`

Expected: Multiple FAIL — template still uses old format

**Step 3: Replace COMMENT_TEMPLATE in comment_generator.py**

Replace the entire `COMMENT_TEMPLATE` (lines 100-167) with the new narrative template. Also update `generate_comment_from_scan` to pass tier-filtered lists to the template.

In `src/comment_generator.py`, replace from `COMMENT_TEMPLATE = Template("""\` through the closing `""")` with:

```python
COMMENT_TEMPLATE = Template("""\
PUBLIC COMMENT: Pre-Meeting Transparency Report
{{ meeting_type | title }} City Council Meeting, {{ meeting_date }}
Submitted by: Richmond Transparency Project

===============================================================

METHODOLOGY

This report cross-references publicly available campaign finance
records (filed with the City Clerk via NetFile and the FPPC via
CAL-ACCESS) against the agenda for the upcoming City Council
meeting. All citations reference specific public filings.

This report is informational only and does not constitute legal
advice or a determination of conflict under Government Code
Sections 87100-87105.

Items scanned: {{ total_items }}
Campaign finance records searched: {{ contribution_count | default("27,035", true) }}
{% if enriched_count > 0 -%}
Items with enhanced document scanning: {{ enriched_count }}
{% endif -%}
Findings: {{ tier1_count + tier2_count }}
{% if suppressed_count > 0 -%}
Additional matches tracked internally: {{ suppressed_count }}
{% endif %}
===============================================================
{% if tier1_flags %}
POTENTIAL CONFLICTS OF INTEREST
===============================================================
{% for flag in tier1_flags %}
{{ loop.index }}. {{ flag.agenda_item_title }}
{%- if flag.financial_amount %} -- {{ flag.financial_amount }}{% endif %}

   (Agenda Item {{ flag.agenda_item_number }})

   {{ flag.description }}

{% if "sitting council member" in (flag.council_member or "") -%}
   {{ flag.council_member.split(" (")[0] }} is a sitting member who
   will vote on this item.

{% endif -%}
   Under California's Political Reform Act (Gov. Code SS87100),
   elected officials must disqualify themselves from governmental
   decisions that could financially benefit a source of income
   of $500 or more received in the prior 12 months. The FPPC
   defines "source of income" to include persons from whom the
   official received payments (2 Cal. Code Regs. SS18700.3).

   This report does not determine whether a legal conflict
   exists. We disclose this connection so the public and Council
   can evaluate it independently.

{% endfor -%}
{% endif -%}
{% if tier2_flags %}
ADDITIONAL FINANCIAL CONNECTIONS
===============================================================

The following donor-vendor connections were identified in public
campaign finance records. These do not necessarily indicate
conflicts of interest but are disclosed for transparency.
{% for flag in tier2_flags %}
{{ loop.index }}. {{ flag.agenda_item_title }}
{%- if flag.financial_amount %} -- {{ flag.financial_amount }}{% endif %}

   (Agenda Item {{ flag.agenda_item_number }})

   {{ flag.description }}

{% endfor -%}
{% endif -%}
{% if clean_count > 0 %}
ITEMS WITH NO FINANCIAL CONNECTIONS IDENTIFIED
===============================================================

{{ clean_count }} additional agenda items were scanned against
{{ contribution_count | default("27,035", true) }} campaign finance records
(CAL-ACCESS and City Clerk NetFile filings). No donor-vendor
connections were identified.
{% endif %}
===============================================================

ABOUT THIS REPORT

The Richmond Transparency Project is a citizen-led initiative
to make local government more transparent by systematically
cross-referencing public records. All data used in this report
is drawn from publicly available sources. We encourage all
residents to verify information independently.

For questions or corrections: pjfront@gmail.com
Report generated: {{ generated_at }}
""")
```

**Step 4: Update `generate_comment_from_scan` to filter by tier**

Replace the existing `generate_comment_from_scan` function (lines ~172-205) with:

```python
def generate_comment_from_scan(
    scan_result: ScanResult,
    missing_docs: list[MissingDocument] = None,
    contribution_count: str = "27,035",
) -> str:
    """Generate the formatted public comment from a ScanResult.

    Filters findings by publication_tier:
      Tier 1 (Potential Conflict) — published in main section
      Tier 2 (Financial Connection) — published in secondary section
      Tier 3 (internal) — suppressed from public comment
    """
    missing_docs = missing_docs or []

    # Split flags by tier
    tier1_flags = [f for f in scan_result.flags if f.publication_tier == 1]
    tier2_flags = [f for f in scan_result.flags if f.publication_tier == 2]
    suppressed_flags = [f for f in scan_result.flags if f.publication_tier == 3]

    # Merge clean items: remove any flagged by missing docs
    missing_item_nums = set()
    for doc in missing_docs:
        ref = doc.referenced_in
        if ref.startswith("Item "):
            missing_item_nums.add(ref[5:])

    clean_items = [n for n in scan_result.clean_items if n not in missing_item_nums]

    return COMMENT_TEMPLATE.render(
        meeting_date=scan_result.meeting_date,
        meeting_type=scan_result.meeting_type,
        total_items=scan_result.total_items_scanned,
        enriched_count=len(scan_result.enriched_items),
        contribution_count=contribution_count,
        tier1_flags=tier1_flags,
        tier2_flags=tier2_flags,
        tier1_count=len(tier1_flags),
        tier2_count=len(tier2_flags),
        suppressed_count=len(suppressed_flags),
        missing_docs=missing_docs,
        clean_count=len(clean_items),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S PT"),
    )
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_comment_generator.py -v`

Expected: All PASSED

**Step 6: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All PASSED

**Step 7: Commit**

```bash
git add src/comment_generator.py tests/test_comment_generator.py
git commit -m "Phase 1: redesign comment template with three-tier classification and narrative format"
```

---

### Task 6: Regenerate the Feb 17 Comment and Verify

**Files:**
- Modify: `src/data/2026-02-17_comment.txt` (regenerated output)

**Step 1: Regenerate the comment using the existing pipeline**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/src
python comment_generator.py \
    data/extracted/2026-02-17_agenda.json \
    --contributions data/combined_contributions.json \
    --escribemeetings data/escribemeetings/2026-02-17/meeting_data.json \
    --output data/2026-02-17_comment.txt
```

Note: If the eSCRIBE data path differs, check `ls src/data/escribemeetings/` and adjust.

**Step 2: Manually inspect the output**

Read `src/data/2026-02-17_comment.txt` and verify:

- [ ] No "Confidence:" lines appear
- [ ] No "Evidence:" bullet lists
- [ ] No empty "Recipient:" fields
- [ ] No "(None)" or "(n/a)" employer strings
- [ ] `pjfront@gmail.com` appears (not `[email]`)
- [ ] Tier 3 findings (Rico Rincon firefighter union, Cheryl Maier to Oscar Garcia/Shawn Dunning) are NOT present
- [ ] Clean items show summary count, not individual item numbers
- [ ] If any Tier 1/2 findings exist, they appear as narrative paragraphs

**Step 3: Commit**

```bash
git add src/data/2026-02-17_comment.txt
git commit -m "Phase 1: regenerate Feb 17 comment with redesigned format"
```

---

### Task 7: Log Decision in DECISIONS.md

**Files:**
- Modify: `docs/DECISIONS.md`

**Step 1: Add decision entry**

Append to `docs/DECISIONS.md`:

```markdown
## 2026-02-18: Three-Tier Finding Classification

**Decision:** Findings are classified into three tiers for publication:
- Tier 1 "Potential Conflict of Interest" — sitting council member, direct match, material amount. Published prominently.
- Tier 2 "Potential Financial Connection" — sitting member but weaker signal. Published in secondary section.
- Tier 3 internal — non-sitting recipients, union dues, trivial amounts. Stored for pattern analysis but suppressed from public comment.

**Rationale:** Calling firefighter union payroll deductions and $100 donations to failed candidates "potential conflicts" was misleading and would damage credibility. Only findings where a sitting council member could plausibly have a financial conflict should use that label. Weak signals are still valuable for longitudinal analysis but shouldn't appear in the official public record.

**Design doc:** `docs/plans/2026-02-18-comment-redesign-design.md`

## 2026-02-18: Narrative Comment Format

**Decision:** Public comment output uses narrative paragraphs (reads like investigative journalism) instead of structured code-like format (bullet lists, raw confidence scores, evidence sections).

**Rationale:** The comment is submitted to the City Clerk and becomes part of the official meeting record. It must be readable by any resident, council member, or journalist without the agenda packet open. Item names in plain English, legal context in plain English, filing references woven into prose.
```

**Step 2: Commit**

```bash
git add docs/DECISIONS.md
git commit -m "Phase 1: log three-tier classification and narrative format decisions"
```

---

### Task 8: Run Full Test Suite and Final Verification

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASSED (approximately 12-15 tests across 3 test files).

**Step 2: Verify no regressions in the scanner CLI**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP/src
python conflict_scanner.py \
    data/extracted/2026-02-17_agenda.json \
    --contributions data/combined_contributions.json
```

Verify scanner report still runs without errors. The `format_scan_report` function (internal report) still shows all tiers — only the public comment filters.

**Step 3: Verify comment generator CLI**

```bash
python comment_generator.py \
    data/extracted/2026-02-17_agenda.json \
    --contributions data/combined_contributions.json
```

Verify dry-run output prints the redesigned comment format.

---

## Summary of All Commits

| # | Commit Message | Files |
|---|---------------|-------|
| 1 | `Phase 1: add test infrastructure and tier assignment tests (red)` | `tests/`, `requirements.txt` |
| 2 | `Phase 1: add publication_tier field to ConflictFlag dataclass` | `src/conflict_scanner.py` |
| 3 | `Phase 1: assign publication_tier in scanner based on confidence + sitting status` | `src/conflict_scanner.py`, `tests/test_scanner_tier_assignment.py` |
| 4 | `Phase 1: fix empty recipient on PAC contributions, fix None employer display` | `src/conflict_scanner.py`, `tests/test_scanner_bugs.py` |
| 5 | `Phase 1: redesign comment template with three-tier classification and narrative format` | `src/comment_generator.py`, `tests/test_comment_generator.py` |
| 6 | `Phase 1: regenerate Feb 17 comment with redesigned format` | `src/data/2026-02-17_comment.txt` |
| 7 | `Phase 1: log three-tier classification and narrative format decisions` | `docs/DECISIONS.md` |
