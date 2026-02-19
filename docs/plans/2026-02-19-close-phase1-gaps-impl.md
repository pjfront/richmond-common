# Close Phase 1 Gaps — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete bias audit instrumentation (Census data, sidecar persistence, surname tier tallying, ground truth CLI, periodic audit module), regenerate comment with redesigned template, and prepare for first real submission.

**Architecture:** JSON sidecar files in `src/data/audit_runs/` with UUID filenames. Census surname data downloaded and pre-processed into a tier lookup JSON. Interactive CLI for ground truth review adds verdicts to existing sidecar files. Periodic bias audit module reads all sidecars and computes per-tier false positive rates.

**Tech Stack:** Python 3.9+, requests (Census download), pytest, json, argparse

---

### Task 1: Census Surname Data — Download and Processing Script

**Files:**
- Create: `src/prepare_census_data.py`
- Create: `tests/test_prepare_census_data.py`

**Step 1: Write the failing test**

```python
# tests/test_prepare_census_data.py
"""Tests for Census surname data preprocessing."""
import json
import csv
import io
import pytest

from prepare_census_data import assign_tier, process_census_csv


class TestAssignTier:
    """assign_tier() maps rank to frequency tier."""

    def test_tier_1_top_100(self):
        assert assign_tier(1) == 1
        assert assign_tier(100) == 1

    def test_tier_2_top_1000(self):
        assert assign_tier(101) == 2
        assert assign_tier(1000) == 2

    def test_tier_3_top_10000(self):
        assert assign_tier(1001) == 3
        assert assign_tier(10000) == 3

    def test_tier_4_rare(self):
        assert assign_tier(10001) == 4
        assert assign_tier(50000) == 4


class TestProcessCensusCsv:
    """process_census_csv() converts CSV text to {surname: tier} dict."""

    def test_processes_sample_data(self):
        csv_text = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
        csv_text += "SMITH,1,2442977,828.19,828.19,70.90,23.11,0.50,0.89,2.19,2.40\n"
        csv_text += "JOHNSON,2,1932812,655.24,1483.44,58.97,34.63,0.54,0.94,2.56,2.36\n"
        csv_text += "OKAFOR,15000,1234,0.42,98000.00,1.00,95.00,0.50,0.10,1.40,2.00\n"
        result = process_census_csv(csv_text)
        assert result["smith"] == 1
        assert result["johnson"] == 1
        assert result["okafor"] == 4

    def test_handles_suppressed_values(self):
        """Census uses '(S)' for suppressed values — should still process rank."""
        csv_text = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
        csv_text += "RAMIREZ,500,500000,169.54,50000.00,(S),(S),(S),(S),(S),76.73\n"
        result = process_census_csv(csv_text)
        assert result["ramirez"] == 2

    def test_lowercase_keys(self):
        csv_text = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
        csv_text += "GARCIA,8,1166120,395.32,5000.00,5.38,0.48,1.43,0.47,1.16,91.08\n"
        result = process_census_csv(csv_text)
        assert "garcia" in result
        assert "GARCIA" not in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_prepare_census_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prepare_census_data'`

**Step 3: Write the implementation**

```python
# src/prepare_census_data.py
"""
Richmond Transparency Project — Census Surname Data Preprocessor

Downloads Census 2010 surname frequency data and pre-processes it into
a {normalized_surname: tier} JSON lookup used by bias_signals.py.

Source: https://www2.census.gov/topics/genealogy/2010surnames/names.zip
Output: src/data/census/surname_freq.json

Tiers (per docs/specs/bias-audit-spec.md):
  Tier 1: rank 1-100 (most common)
  Tier 2: rank 101-1000
  Tier 3: rank 1001-10000
  Tier 4: rank 10001+ (rare)

Usage:
  python prepare_census_data.py
  python prepare_census_data.py --skip-download  # if CSV already exists
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "census"
CSV_FILENAME = "Names_2010Census.csv"
OUTPUT_FILENAME = "surname_freq.json"
CENSUS_URL = "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"


def assign_tier(rank: int) -> int:
    """Map Census surname rank to frequency tier."""
    if rank <= 100:
        return 1
    elif rank <= 1000:
        return 2
    elif rank <= 10000:
        return 3
    else:
        return 4


def process_census_csv(csv_text: str) -> dict[str, int]:
    """Convert Census CSV text to {lowercase_surname: tier} dict.

    Args:
        csv_text: Raw CSV content with header row.

    Returns:
        Dict mapping lowercase surname to tier (1-4).
    """
    result = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        name = row.get("name", "").strip()
        rank_str = row.get("rank", "").strip()
        if not name or not rank_str:
            continue
        try:
            rank = int(rank_str)
        except ValueError:
            continue
        result[name.lower()] = assign_tier(rank)
    return result


def download_census_data() -> Path:
    """Download Census 2010 surname ZIP and extract CSV."""
    import requests

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / CSV_FILENAME

    if csv_path.exists():
        print(f"  CSV already exists at {csv_path}")
        return csv_path

    print(f"  Downloading {CENSUS_URL} ...")
    resp = requests.get(CENSUS_URL, timeout=120)
    resp.raise_for_status()

    zip_path = DATA_DIR / "names.zip"
    zip_path.write_bytes(resp.content)
    print(f"  Saved ZIP to {zip_path} ({len(resp.content):,} bytes)")

    with zipfile.ZipFile(zip_path) as zf:
        # Find the CSV inside the ZIP
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV found in ZIP. Contents: {zf.namelist()}")
        csv_name = csv_names[0]
        zf.extract(csv_name, DATA_DIR)
        extracted = DATA_DIR / csv_name
        if extracted.name != CSV_FILENAME:
            extracted.rename(csv_path)
        print(f"  Extracted {csv_name} to {csv_path}")

    return csv_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and preprocess Census 2010 surname frequency data",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download (use existing CSV)",
    )
    args = parser.parse_args()

    print("Census 2010 Surname Data Preprocessor")
    print("=" * 50)

    csv_path = DATA_DIR / CSV_FILENAME
    if not args.skip_download:
        csv_path = download_census_data()

    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        print("Run without --skip-download to fetch the data.")
        return

    print(f"  Processing {csv_path} ...")
    csv_text = csv_path.read_text(encoding="utf-8", errors="replace")
    surname_freq = process_census_csv(csv_text)

    output_path = DATA_DIR / OUTPUT_FILENAME
    with open(output_path, "w") as f:
        json.dump(surname_freq, f)
    print(f"  Wrote {len(surname_freq):,} surnames to {output_path}")

    # Print tier distribution
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for tier in surname_freq.values():
        tier_counts[tier] += 1
    print(f"  Tier 1 (rank 1-100):     {tier_counts[1]:,}")
    print(f"  Tier 2 (rank 101-1000):  {tier_counts[2]:,}")
    print(f"  Tier 3 (rank 1001-10k):  {tier_counts[3]:,}")
    print(f"  Tier 4 (rank 10001+):    {tier_counts[4]:,}")
    print("Done.")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_prepare_census_data.py -v`
Expected: All 6 tests PASS

**Step 5: Run the script to download actual Census data**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/src && python prepare_census_data.py`
Expected: Downloads ~12MB ZIP, extracts CSV, writes `src/data/census/surname_freq.json` with ~160K+ entries

**Step 6: Verify bias_signals.py now loads the data**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -c "import sys; sys.path.insert(0, 'src'); from bias_signals import lookup_surname_frequency_tier; print(lookup_surname_frequency_tier('Smith')); print(lookup_surname_frequency_tier('Okafor'))"`
Expected: `1` and some integer (3 or 4), not `None`

**Step 7: Add census data to .gitignore**

Add `src/data/census/Names_2010Census.csv` and `src/data/census/names.zip` to `.gitignore`. The processed `surname_freq.json` is small enough to commit (~3-5MB). If it's over 5MB, add it to `.gitignore` too and document that users must run `prepare_census_data.py`.

**Step 8: Commit**

```bash
git add src/prepare_census_data.py tests/test_prepare_census_data.py src/data/census/surname_freq.json .gitignore
git commit -m "Phase 1: add Census surname data pipeline for bias audit tiers"
```

---

### Task 2: Audit Sidecar Persistence — Save to Disk

**Files:**
- Modify: `src/run_pipeline.py:271-273` (after scan, before comment generation)
- Modify: `src/conflict_scanner.py:1015-1022` (CLI main, after scan)
- Create: `tests/test_audit_persistence.py`

**Step 1: Write the failing test**

```python
# tests/test_audit_persistence.py
"""Tests for audit sidecar persistence in pipeline and scanner CLI."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from conflict_scanner import scan_meeting_json


def _make_meeting(items):
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


class TestAuditSidecarPersistence:
    """run_pipeline saves audit sidecar to src/data/audit_runs/."""

    def test_scan_result_audit_log_saveable(self, tmp_path):
        """ScanResult.audit_log.save() produces valid JSON."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [{
            "donor_name": "Jane Doe",
            "donor_employer": "TestCo",
            "committee_name": "Wilson for Richmond 2024",
            "amount": 500,
            "date": "2024-01-01",
            "filing_id": "999",
            "source": "test",
        }]
        result = scan_meeting_json(meeting, contributions)
        audit_path = tmp_path / "audit_runs" / f"{result.scan_run_id}.json"
        result.audit_log.save(audit_path)

        assert audit_path.exists()
        data = json.loads(audit_path.read_text())
        assert data["scan_run_id"] == result.scan_run_id
        assert "decisions" in data
        assert "summary" in data
```

**Step 2: Run test to verify it passes** (this one should pass already since `save()` exists)

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_audit_persistence.py -v`
Expected: PASS (the save method works, we're just verifying the pattern)

**Step 3: Modify `run_pipeline.py` — add audit sidecar save after scan**

In `src/run_pipeline.py`, after line 273 (`print(f"  Found {len(scan_result.flags)} flags..."`), add:

```python
    # Save audit sidecar
    audit_dir = DATA_DIR / "audit_runs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{scan_result.scan_run_id}.json"
    scan_result.audit_log.save(audit_path)
    print(f"  Audit sidecar saved to {audit_path}")
```

**Step 4: Modify `conflict_scanner.py` CLI — add audit sidecar save after scan**

In `src/conflict_scanner.py`, after line 1016 (`report = format_scan_report(result)`), add:

```python
    # Save audit sidecar
    audit_dir = Path(__file__).parent / "data" / "audit_runs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{result.scan_run_id}.json"
    result.audit_log.save(audit_path)
    print(f"Audit sidecar saved to {audit_path}")
```

**Step 5: Run all existing tests to verify nothing breaks**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/run_pipeline.py src/conflict_scanner.py tests/test_audit_persistence.py
git commit -m "Phase 1: persist audit sidecar to src/data/audit_runs/ after each scan"
```

---

### Task 3: Surname Tier Tallying in Scan Loop

**Files:**
- Modify: `src/conflict_scanner.py:758-772` (ScanAuditSummary construction)
- Modify: `tests/test_scanner_audit_integration.py` (add tier tallying test)

**Step 1: Write the failing test**

Add to `tests/test_scanner_audit_integration.py`:

```python
class TestSurnameTierTallying:
    """Audit summary populates surname tier distribution fields."""

    def test_summary_has_donor_tier_counts(self):
        """Contributions compared should tally by surname tier."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for consulting services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [
            _make_contribution("John Smith", "TestCo", "Wilson for Richmond 2024", 500),
            _make_contribution("Jane Doe", "OtherCo", "Wilson for Richmond 2024", 200),
        ]
        result = scan_meeting_json(meeting, contributions)
        summary = result.audit_log.summary

        # At least one tier count should be nonzero (Smith is tier 1 if census loaded,
        # or all go to 'unknown' if census not loaded)
        total_donor_tiers = (
            summary.donors_surname_tier_1
            + summary.donors_surname_tier_2
            + summary.donors_surname_tier_3
            + summary.donors_surname_tier_4
            + summary.donors_surname_unknown
        )
        assert total_donor_tiers > 0, "Surname tier tallying should count all contributions"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_scanner_audit_integration.py::TestSurnameTierTallying -v`
Expected: FAIL — `total_donor_tiers` is 0 because tier fields are never populated

**Step 3: Implement tier tallying in `conflict_scanner.py`**

In `src/conflict_scanner.py`, just before the `audit_logger.summary = ScanAuditSummary(...)` block at line 759, add code to:
1. Import `lookup_surname_frequency_tier` from `bias_signals`
2. Iterate all contributions to count by surname tier
3. Iterate flagged contributions (from `flags`) to count by surname tier
4. Pass these counts to the `ScanAuditSummary` constructor

The implementation adds a helper that extracts the last token of a donor name and looks up its tier:

```python
from bias_signals import lookup_surname_frequency_tier

# ... inside scan_meeting_json, before building ScanAuditSummary:

# Tally surname frequency tiers across all contributions compared
donor_tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, None: 0}
for contribution in contributions:
    dname = contribution.get("donor_name") or contribution.get("contributor_name") or ""
    tokens = dname.strip().split()
    surname = tokens[-1] if tokens else ""
    tier = lookup_surname_frequency_tier(surname)
    donor_tier_counts[tier] = donor_tier_counts.get(tier, 0) + 1

# Tally surname tiers for flagged donors only
flagged_tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, None: 0}
for decision in audit_logger.decisions:
    if decision.matched:
        tier = decision.bias_signals.get("surname_frequency_tier")
        flagged_tier_counts[tier] = flagged_tier_counts.get(tier, 0) + 1
```

Then pass them into the `ScanAuditSummary` constructor:

```python
    donors_surname_tier_1=donor_tier_counts.get(1, 0),
    donors_surname_tier_2=donor_tier_counts.get(2, 0),
    donors_surname_tier_3=donor_tier_counts.get(3, 0),
    donors_surname_tier_4=donor_tier_counts.get(4, 0),
    donors_surname_unknown=donor_tier_counts.get(None, 0),
    flagged_surname_tier_1=flagged_tier_counts.get(1, 0),
    flagged_surname_tier_2=flagged_tier_counts.get(2, 0),
    flagged_surname_tier_3=flagged_tier_counts.get(3, 0),
    flagged_surname_tier_4=flagged_tier_counts.get(4, 0),
    flagged_surname_unknown=flagged_tier_counts.get(None, 0),
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_scanner_audit_integration.py -v`
Expected: All tests PASS including new `TestSurnameTierTallying`

**Step 5: Run full test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/conflict_scanner.py tests/test_scanner_audit_integration.py
git commit -m "Phase 1: tally surname frequency tiers in scan audit summary"
```

---

### Task 4: Ground Truth Officials Reference Data

**Files:**
- Create: `src/ground_truth/officials.json`

**Step 1: Create the officials reference file**

This uses the same data already in `conflict_scanner.py` lines 85-104, formatted as structured JSON with additional metadata (district, role, term info):

```json
{
  "city_fips": "0660620",
  "city_name": "Richmond, California",
  "updated": "2026-02-19",
  "current_council_members": [
    {"name": "Eduardo Martinez", "role": "Mayor", "district": null},
    {"name": "Cesar Zepeda", "role": "Vice Mayor", "district": 2},
    {"name": "Jamelia Brown", "role": "Council Member", "district": 1},
    {"name": "Doria Robinson", "role": "Council Member", "district": 3},
    {"name": "Soheila Bana", "role": "Council Member", "district": 4},
    {"name": "Sue Wilson", "role": "Council Member", "district": 5},
    {"name": "Claudia Jimenez", "role": "Council Member", "district": 6}
  ],
  "former_council_members": [
    {"name": "Tom Butt", "notes": "Longest-serving, former mayor, E-Forum blog"},
    {"name": "Nat Bates", "notes": "Former council member"},
    {"name": "Jovanka Beckles", "notes": "Former progressive coalition"},
    {"name": "Ben Choi", "notes": "Former progressive coalition"},
    {"name": "Jael Myrick", "notes": "Former council member"},
    {"name": "Vinay Pimple", "notes": "Former council member"},
    {"name": "Corky Booze", "notes": "Former council member"},
    {"name": "Jim Rogers", "notes": "Former council member"},
    {"name": "Ahmad Anderson", "notes": "Former council member"},
    {"name": "Oscar Garcia", "notes": "Former council member"},
    {"name": "Gayle McLaughlin", "notes": "Former mayor, progressive coalition"},
    {"name": "Melvin Willis", "notes": "Former council member"},
    {"name": "Shawn Dunning", "notes": "Former council member"}
  ]
}
```

**Step 2: Commit**

```bash
git add src/ground_truth/officials.json
git commit -m "Phase 1: add Richmond council member reference data for ground truth review"
```

---

### Task 5: Ground Truth Review CLI

**Files:**
- Modify: `src/conflict_scanner.py:991-1026` (CLI main — add `--review` mode)
- Create: `tests/test_ground_truth_review.py`

**Step 1: Write the failing test**

```python
# tests/test_ground_truth_review.py
"""Tests for ground truth review CLI."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from io import StringIO

from conflict_scanner import load_audit_sidecar, apply_verdict


class TestLoadAuditSidecar:
    """load_audit_sidecar() reads and parses a JSON sidecar file."""

    def test_loads_valid_sidecar(self, tmp_path):
        sidecar = {
            "scan_run_id": "test-123",
            "created_at": "2026-02-19T00:00:00Z",
            "decisions": [
                {
                    "donor_name": "John Smith",
                    "donor_employer": "Acme",
                    "agenda_item_number": "V.1",
                    "agenda_text_preview": "Contract text",
                    "match_type": "exact",
                    "confidence": 0.7,
                    "matched": True,
                    "bias_signals": {"has_compound_surname": False},
                    "ground_truth": None,
                    "ground_truth_source": None,
                    "audit_notes": None,
                }
            ],
            "summary": {"scan_run_id": "test-123", "meeting_date": "2026-02-17"},
        }
        path = tmp_path / "test-123.json"
        path.write_text(json.dumps(sidecar))
        data = load_audit_sidecar(path)
        assert data["scan_run_id"] == "test-123"
        assert len(data["decisions"]) == 1

    def test_returns_none_for_missing_file(self, tmp_path):
        data = load_audit_sidecar(tmp_path / "nonexistent.json")
        assert data is None


class TestApplyVerdict:
    """apply_verdict() updates a decision with ground truth."""

    def test_true_positive(self):
        decision = {
            "donor_name": "John Smith",
            "ground_truth": None,
            "ground_truth_source": None,
            "audit_notes": None,
        }
        apply_verdict(decision, verdict="T", notes=None)
        assert decision["ground_truth"] is True
        assert "manual_review" in decision["ground_truth_source"]

    def test_false_positive(self):
        decision = {
            "donor_name": "John Smith",
            "ground_truth": None,
            "ground_truth_source": None,
            "audit_notes": None,
        }
        apply_verdict(decision, verdict="F", notes="Not the same entity")
        assert decision["ground_truth"] is False
        assert decision["audit_notes"] == "Not the same entity"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_ground_truth_review.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_audit_sidecar'`

**Step 3: Implement `load_audit_sidecar` and `apply_verdict` in `conflict_scanner.py`**

Add before the `main()` function (around line 989):

```python
# ── Ground Truth Review ──────────────────────────────────────

def load_audit_sidecar(path: Path) -> dict | None:
    """Load an audit sidecar JSON file. Returns None if file missing."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def apply_verdict(decision: dict, verdict: str, notes: str | None):
    """Apply a ground truth verdict to an audit decision dict.

    Args:
        decision: Dict from sidecar's decisions list (mutated in place).
        verdict: 'T' for true positive, 'F' for false positive.
        notes: Optional reviewer notes.
    """
    from datetime import datetime, timezone
    decision["ground_truth"] = verdict == "T"
    decision["ground_truth_source"] = f"manual_review_{datetime.now(timezone.utc).isoformat()}"
    if notes:
        decision["audit_notes"] = notes


def find_latest_audit_sidecar(audit_dir: Path) -> Path | None:
    """Find the most recently created audit sidecar file."""
    if not audit_dir.exists():
        return None
    files = sorted(audit_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Skip files that start with "bias_audit_report" (those are audit reports, not sidecars)
    for f in files:
        if not f.name.startswith("bias_audit_report"):
            return f
    return None


def run_review(audit_path: Path):
    """Interactive ground truth review of an audit sidecar."""
    data = load_audit_sidecar(audit_path)
    if data is None:
        print(f"ERROR: Audit sidecar not found at {audit_path}")
        return

    decisions = data.get("decisions", [])
    unreviewed = [d for d in decisions if d.get("ground_truth") is None and d.get("matched")]
    if not unreviewed:
        print("All matched decisions already have ground truth verdicts.")
        return

    print(f"\nGround Truth Review — {audit_path.name}")
    print(f"Scan run: {data.get('scan_run_id', 'unknown')}")
    print(f"Unreviewed matched decisions: {len(unreviewed)}")
    print("=" * 60)

    reviewed = 0
    true_pos = 0
    false_pos = 0

    for i, d in enumerate(unreviewed, 1):
        print(f"\n--- Decision {i} of {len(unreviewed)} ---")
        print(f"  Donor: {d['donor_name']}")
        print(f"  Employer: {d.get('donor_employer', '')}")
        print(f"  Agenda item: {d['agenda_item_number']}")
        print(f"  Text preview: {d.get('agenda_text_preview', '')[:200]}")
        print(f"  Match type: {d['match_type']}")
        print(f"  Confidence: {d['confidence']:.0%}")
        signals = d.get("bias_signals", {})
        if signals:
            print(f"  Bias signals: compound={signals.get('has_compound_surname')}, "
                  f"diacritics={signals.get('has_diacritics')}, "
                  f"tokens={signals.get('token_count')}, "
                  f"tier={signals.get('surname_frequency_tier')}")

        while True:
            choice = input("\n  [T]rue positive / [F]alse positive / [S]kip / [N]otes then verdict: ").strip().upper()
            if choice == "T":
                apply_verdict(d, "T", None)
                reviewed += 1
                true_pos += 1
                break
            elif choice == "F":
                apply_verdict(d, "F", None)
                reviewed += 1
                false_pos += 1
                break
            elif choice == "S":
                break
            elif choice == "N":
                notes = input("  Notes: ").strip()
                choice2 = input("  Now: [T]rue / [F]alse / [S]kip: ").strip().upper()
                if choice2 == "T":
                    apply_verdict(d, "T", notes)
                    reviewed += 1
                    true_pos += 1
                    break
                elif choice2 == "F":
                    apply_verdict(d, "F", notes)
                    reviewed += 1
                    false_pos += 1
                    break
                else:
                    break
            else:
                print("  Invalid choice. Use T, F, S, or N.")

    # Save updated sidecar
    with open(audit_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n{'=' * 60}")
    print(f"Review complete. Reviewed {reviewed} of {len(unreviewed)} decisions.")
    print(f"  True positives: {true_pos}")
    print(f"  False positives: {false_pos}")
    print(f"  Skipped: {len(unreviewed) - reviewed}")
    print(f"Updated sidecar saved to {audit_path}")
```

**Step 4: Add `--review` to the CLI `main()`**

Modify the existing `main()` in `conflict_scanner.py` to support `--review`:

```python
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Richmond Transparency Project — Conflict Scanner")
    subparsers = parser.add_subparsers(dest="command")

    # Default scan mode (backwards-compatible: no subcommand required)
    parser.add_argument("meeting_json", nargs="?", help="Path to extracted meeting JSON file")
    parser.add_argument("--contributions", help="Path to contributions JSON file")
    parser.add_argument("--form700", help="Path to Form 700 interests JSON file")
    parser.add_argument("--output", help="Save report to file")

    # Review mode
    parser.add_argument("--review", action="store_true", help="Enter ground truth review mode")
    parser.add_argument("--scan-run", help="Review a specific scan run by UUID")
    parser.add_argument("--latest", action="store_true", help="Review the most recent scan run")

    args = parser.parse_args()

    audit_dir = Path(__file__).parent / "data" / "audit_runs"

    if args.review:
        if args.scan_run:
            audit_path = audit_dir / f"{args.scan_run}.json"
        elif args.latest:
            audit_path = find_latest_audit_sidecar(audit_dir)
            if audit_path is None:
                print("ERROR: No audit sidecars found in", audit_dir)
                return
        else:
            print("ERROR: --review requires --latest or --scan-run <uuid>")
            return
        run_review(audit_path)
        return

    # Normal scan mode
    if not args.meeting_json:
        parser.error("meeting_json is required for scan mode")

    with open(args.meeting_json) as f:
        meeting_data = json.load(f)

    contributions = []
    if args.contributions:
        with open(args.contributions) as f:
            contributions = json.load(f)

    form700 = []
    if args.form700:
        with open(args.form700) as f:
            form700 = json.load(f)

    result = scan_meeting_json(meeting_data, contributions, form700)
    report = format_scan_report(result)

    # Save audit sidecar
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{result.scan_run_id}.json"
    result.audit_log.save(audit_path)
    print(f"Audit sidecar saved to {audit_path}")

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(report)
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_ground_truth_review.py tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/conflict_scanner.py tests/test_ground_truth_review.py
git commit -m "Phase 1: add ground truth review CLI (--review --latest / --scan-run)"
```

---

### Task 6: Periodic Bias Audit Module

**Files:**
- Create: `src/bias_audit.py`
- Create: `tests/test_bias_audit.py`

**Step 1: Write the failing test**

```python
# tests/test_bias_audit.py
"""Tests for periodic bias audit analysis."""
import json
import pytest
from pathlib import Path

from bias_audit import load_all_verdicts, compute_bias_statistics


class TestLoadAllVerdicts:
    """load_all_verdicts() reads ground truth from all sidecars."""

    def test_loads_verdicts_from_multiple_sidecars(self, tmp_path):
        for i in range(3):
            sidecar = {
                "scan_run_id": f"run-{i}",
                "decisions": [
                    {
                        "donor_name": f"Donor {i}",
                        "matched": True,
                        "ground_truth": True if i < 2 else False,
                        "bias_signals": {"surname_frequency_tier": 1, "has_compound_surname": False},
                    }
                ],
            }
            (tmp_path / f"run-{i}.json").write_text(json.dumps(sidecar))

        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 3

    def test_skips_unreviewed_decisions(self, tmp_path):
        sidecar = {
            "scan_run_id": "run-1",
            "decisions": [
                {"donor_name": "A", "matched": True, "ground_truth": True, "bias_signals": {}},
                {"donor_name": "B", "matched": True, "ground_truth": None, "bias_signals": {}},
            ],
        }
        (tmp_path / "run-1.json").write_text(json.dumps(sidecar))
        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 1

    def test_skips_suppressed_decisions(self, tmp_path):
        sidecar = {
            "scan_run_id": "run-1",
            "decisions": [
                {"donor_name": "A", "matched": True, "ground_truth": True, "bias_signals": {}},
                {"donor_name": "B", "matched": False, "ground_truth": None, "bias_signals": {}},
            ],
        }
        (tmp_path / "run-1.json").write_text(json.dumps(sidecar))
        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 1


class TestComputeBiasStatistics:
    """compute_bias_statistics() computes per-tier false positive rates."""

    def test_computes_fp_rate_by_tier(self):
        verdicts = [
            {"ground_truth": True, "bias_signals": {"surname_frequency_tier": 1}},
            {"ground_truth": True, "bias_signals": {"surname_frequency_tier": 1}},
            {"ground_truth": False, "bias_signals": {"surname_frequency_tier": 4}},
            {"ground_truth": False, "bias_signals": {"surname_frequency_tier": 4}},
            {"ground_truth": True, "bias_signals": {"surname_frequency_tier": 4}},
        ]
        stats = compute_bias_statistics(verdicts)
        assert stats["overall"]["total"] == 5
        assert stats["overall"]["true_positives"] == 3
        assert stats["overall"]["false_positives"] == 2
        # Tier 1: 2 TP, 0 FP => FP rate 0.0
        assert stats["by_surname_tier"][1]["false_positive_rate"] == 0.0
        # Tier 4: 1 TP, 2 FP => FP rate ~0.667
        assert abs(stats["by_surname_tier"][4]["false_positive_rate"] - 2/3) < 0.01

    def test_handles_empty_verdicts(self):
        stats = compute_bias_statistics([])
        assert stats["overall"]["total"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_bias_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bias_audit'`

**Step 3: Implement `bias_audit.py`**

```python
# src/bias_audit.py
"""
Richmond Transparency Project — Periodic Bias Audit

Analyzes accumulated ground-truth data from audit sidecars to detect
systematic bias in the conflict scanner's matching logic.

See docs/specs/bias-audit-spec.md Section 6 for specification.

Usage:
  python bias_audit.py
  python bias_audit.py --min-decisions 50  # override minimum for testing
  python bias_audit.py --audit-dir path/to/audit_runs
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

AUDIT_DIR = Path(__file__).parent / "data" / "audit_runs"
DEFAULT_MIN_DECISIONS = 100


def load_all_verdicts(audit_dir: Path) -> list[dict]:
    """Load all ground-truthed decisions from audit sidecar files.

    Returns only decisions where:
      - matched is True (actual flags, not suppressed near-misses)
      - ground_truth is not None (has been reviewed)
    """
    verdicts = []
    for path in sorted(audit_dir.glob("*.json")):
        if path.name.startswith("bias_audit_report"):
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for d in data.get("decisions", []):
            if d.get("matched") and d.get("ground_truth") is not None:
                verdicts.append(d)
    return verdicts


def compute_bias_statistics(verdicts: list[dict]) -> dict:
    """Compute per-tier false positive rates and overall precision.

    Returns:
        dict with 'overall' stats, 'by_surname_tier' breakdown,
        and 'by_name_property' breakdown.
    """
    if not verdicts:
        return {
            "overall": {"total": 0, "true_positives": 0, "false_positives": 0, "precision": None},
            "by_surname_tier": {},
            "by_name_property": {},
        }

    total = len(verdicts)
    true_pos = sum(1 for v in verdicts if v["ground_truth"] is True)
    false_pos = total - true_pos

    # Per surname tier
    tier_stats = defaultdict(lambda: {"total": 0, "true_positives": 0, "false_positives": 0})
    for v in verdicts:
        tier = (v.get("bias_signals") or {}).get("surname_frequency_tier")
        tier_key = tier if tier is not None else "unknown"
        tier_stats[tier_key]["total"] += 1
        if v["ground_truth"] is True:
            tier_stats[tier_key]["true_positives"] += 1
        else:
            tier_stats[tier_key]["false_positives"] += 1

    for tier_key, stats in tier_stats.items():
        stats["false_positive_rate"] = (
            stats["false_positives"] / stats["total"] if stats["total"] > 0 else 0.0
        )

    # Per name property
    property_stats = {}
    for prop in ("has_compound_surname", "has_diacritics"):
        with_prop = [v for v in verdicts if (v.get("bias_signals") or {}).get(prop)]
        without_prop = [v for v in verdicts if not (v.get("bias_signals") or {}).get(prop)]
        property_stats[prop] = {
            "with": {
                "total": len(with_prop),
                "false_positives": sum(1 for v in with_prop if v["ground_truth"] is False),
                "false_positive_rate": (
                    sum(1 for v in with_prop if v["ground_truth"] is False) / len(with_prop)
                    if with_prop else 0.0
                ),
            },
            "without": {
                "total": len(without_prop),
                "false_positives": sum(1 for v in without_prop if v["ground_truth"] is False),
                "false_positive_rate": (
                    sum(1 for v in without_prop if v["ground_truth"] is False) / len(without_prop)
                    if without_prop else 0.0
                ),
            },
        }

    return {
        "overall": {
            "total": total,
            "true_positives": true_pos,
            "false_positives": false_pos,
            "precision": true_pos / total if total > 0 else None,
        },
        "by_surname_tier": dict(tier_stats),
        "by_name_property": property_stats,
    }


def format_bias_report(stats: dict) -> str:
    """Format bias statistics as a human-readable report."""
    lines = []
    lines.append("BIAS AUDIT REPORT")
    lines.append("=" * 60)

    overall = stats["overall"]
    lines.append(f"Total ground-truthed decisions: {overall['total']}")
    lines.append(f"True positives: {overall['true_positives']}")
    lines.append(f"False positives: {overall['false_positives']}")
    if overall["precision"] is not None:
        lines.append(f"Overall precision: {overall['precision']:.1%}")
    lines.append("")

    lines.append("FALSE POSITIVE RATE BY SURNAME FREQUENCY TIER")
    lines.append("-" * 60)
    tier_labels = {1: "Tier 1 (top 100)", 2: "Tier 2 (top 1K)", 3: "Tier 3 (top 10K)", 4: "Tier 4 (rare)", "unknown": "Unknown"}
    for tier_key in [1, 2, 3, 4, "unknown"]:
        if tier_key in stats["by_surname_tier"]:
            t = stats["by_surname_tier"][tier_key]
            label = tier_labels.get(tier_key, str(tier_key))
            lines.append(f"  {label}: {t['false_positive_rate']:.1%} FP rate ({t['total']} decisions)")
    lines.append("")

    lines.append("FALSE POSITIVE RATE BY NAME PROPERTIES")
    lines.append("-" * 60)
    for prop, data in stats.get("by_name_property", {}).items():
        lines.append(f"  {prop}:")
        lines.append(f"    With:    {data['with']['false_positive_rate']:.1%} FP rate ({data['with']['total']} decisions)")
        lines.append(f"    Without: {data['without']['false_positive_rate']:.1%} FP rate ({data['without']['total']} decisions)")

    # Flag disparities
    lines.append("")
    lines.append("DISPARITY FLAGS")
    lines.append("-" * 60)
    tier_data = stats.get("by_surname_tier", {})
    if 1 in tier_data and 4 in tier_data:
        t1_rate = tier_data[1]["false_positive_rate"]
        t4_rate = tier_data[4]["false_positive_rate"]
        if t1_rate > 0 and t4_rate / t1_rate > 2.0:
            lines.append(f"  WARNING: Tier 4 (rare) surnames have {t4_rate/t1_rate:.1f}x the FP rate of Tier 1 (common)")
        elif t4_rate > t1_rate * 1.5:
            lines.append(f"  NOTE: Tier 4 FP rate ({t4_rate:.1%}) elevated vs Tier 1 ({t1_rate:.1%})")
        else:
            lines.append("  No significant disparity detected between Tier 1 and Tier 4")
    else:
        lines.append("  Insufficient data for tier comparison")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Richmond Transparency Project — Periodic Bias Audit")
    parser.add_argument("--audit-dir", default=str(AUDIT_DIR), help="Path to audit_runs directory")
    parser.add_argument("--min-decisions", type=int, default=DEFAULT_MIN_DECISIONS,
                        help=f"Minimum ground-truthed decisions required (default: {DEFAULT_MIN_DECISIONS})")
    parser.add_argument("--output", help="Save report JSON to file")
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir)
    print(f"Loading verdicts from {audit_dir} ...")
    verdicts = load_all_verdicts(audit_dir)
    print(f"Found {len(verdicts)} ground-truthed decisions")

    if len(verdicts) < args.min_decisions:
        print(f"\nInsufficient data for meaningful bias analysis.")
        print(f"Need {args.min_decisions}+ ground-truthed decisions, currently have {len(verdicts)}.")
        print(f"Use --min-decisions to override (for testing).")
        return

    stats = compute_bias_statistics(verdicts)
    report = format_bias_report(stats)
    print(f"\n{report}")

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = audit_dir / f"bias_audit_report_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nReport JSON saved to {output_path}")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/test_bias_audit.py -v`
Expected: All tests PASS

**Step 5: Run full test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/bias_audit.py tests/test_bias_audit.py
git commit -m "Phase 1: add periodic bias audit module with per-tier FP rate analysis"
```

---

### Task 7: Regenerate Comment and Verify Redesign

**Files:**
- No new files — this is an end-to-end verification run

**Step 1: Run the pipeline for Feb 17, 2026**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/src && python run_pipeline.py --date 2026-02-17 --output data/2026-02-17_comment_v2.txt`

Expected: Pipeline completes, comment saved, audit sidecar saved to `data/audit_runs/`

**Step 2: Verify the comment format**

Read `src/data/2026-02-17_comment_v2.txt` and verify:
- Uses three-tier section headers ("Potential Conflicts of Interest", "Additional Financial Connections")
- No raw confidence percentages (like `Confidence: 40%`)
- No empty `Recipient:` fields
- No `(None)` or `(n/a)` employers
- Narrative prose format, not bullet lists
- Footer includes `pjfront@gmail.com`
- Methodology section present

**Step 3: Verify audit sidecar was saved**

Run: `ls -la /Users/phillip.front/Projects/MyProjects/RTP/src/data/audit_runs/`
Expected: At least one `.json` file (the sidecar from this run)

**Step 4: Verify surname tiers populated in sidecar**

Read the sidecar and check that `summary.donors_surname_tier_*` fields are non-zero (if Census data was loaded in Task 1).

**Step 5: Run ground truth review on the sidecar**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/src && python conflict_scanner.py --review --latest`

Review the flags interactively (this is the first real ground truth data).

**Step 6: Commit the regenerated comment (optional — may be large)**

```bash
git add src/data/2026-02-17_comment_v2.txt
git commit -m "Phase 1: regenerate Feb 17 comment with three-tier publication format"
```

---

### Task 8: Update CLAUDE.md and DECISIONS.md

**Files:**
- Modify: `CLAUDE.md` (update Done section, remove from Remaining)
- Modify: `docs/DECISIONS.md` (log new decisions)

**Step 1: Update CLAUDE.md Done section**

Add entries for:
- Census surname data pipeline (`prepare_census_data.py`)
- Audit sidecar persistence in pipeline and scanner CLI
- Ground truth review CLI (`--review --latest` / `--scan-run`)
- Periodic bias audit module (`bias_audit.py`)
- Comment regeneration with three-tier format verified

**Step 2: Update CLAUDE.md Remaining section**

The only remaining Phase 1 item: "Submit first real transparency public comment to an upcoming meeting" — now with a note that the pipeline is fully instrumented and the comment format is verified.

**Step 3: Log decisions in DECISIONS.md**

- Census data stored at `src/data/census/` (not repo root `data/census/`) — consistent with all other data paths
- Audit sidecars use UUID filenames in `src/data/audit_runs/` — multiple scans per meeting date, no collisions
- Ground truth review is interactive CLI, not batch file — natural for 1-4 flags per meeting
- Periodic bias audit minimum 100 decisions — pre-registered threshold from spec

**Step 4: Commit**

```bash
git add CLAUDE.md docs/DECISIONS.md
git commit -m "Phase 1: update docs for completed bias audit instrumentation"
```

---

### Task 9: Full Test Suite Verification

**Files:**
- No changes — verification only

**Step 1: Run complete test suite**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (should be 50+ tests across 12+ test files)

**Step 2: Verify no import errors across all modules**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/src && python -c "import prepare_census_data; import bias_audit; import bias_signals; import scan_audit; import conflict_scanner; print('All imports OK')"`
Expected: "All imports OK"

**Step 3: Final commit if any cleanup needed**

Only commit if tests revealed something that needed fixing.
