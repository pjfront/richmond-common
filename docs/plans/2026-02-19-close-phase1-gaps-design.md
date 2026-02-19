# Close Phase 1 Gaps — Design Doc

**Date:** 2026-02-19
**Status:** Approved
**Goal:** Complete the bias audit instrumentation, regenerate the public comment with the redesigned template, and prepare for first real comment submission.

## Context

Phase 1's extraction pipeline is functionally complete — 21 meetings extracted, 27K contributions loaded, conflict scanner hardened with three-tier publication system, and an end-to-end `run_pipeline.py` command. But several bias audit pieces were spec'd but never implemented, and the first real comment has not been submitted.

### What Exists

- `src/bias_signals.py` — computes structural risk signals (compound surname, diacritics, token/char count, surname frequency tier). Complete.
- `src/scan_audit.py` — `MatchingDecision`, `ScanAuditSummary`, `ScanAuditLogger` with `save()` method. Complete.
- `src/conflict_scanner.py` — fully integrated with `ScanAuditLogger`. Creates audit logger, logs every flag and suppressed near-miss. Returns `ScanResult` with `audit_log` attached.
- Tests: `test_bias_signals.py`, `test_scan_audit.py`, `test_scanner_audit_integration.py` all pass.

### What's Missing

| Gap | Impact |
|-----|--------|
| Census surname frequency data (`src/data/census/surname_freq.json`) | All surname_frequency_tier fields are `None` |
| No script to download/process Census data | Can't set up surname tiers for any city |
| `audit_log.save()` never called in run_pipeline.py or scanner CLI | Audit data computed then silently dropped |
| Surname tier tallying in scan loop | All tier distribution fields in ScanAuditSummary stay 0 |
| `filtered_no_text_match` counter | Not tracked |
| `--review` CLI for ground truth verdicts | No way to accumulate human-verified labels |
| `src/bias_audit.py` periodic audit module | No way to analyze bias from accumulated verdicts |
| `src/ground_truth/officials.json` | No council member reference data for review context |
| Old comment at `src/data/2026-02-17_comment.txt` | Pre-redesign format with bugs (empty recipients, raw confidence) |

## Design

### 1. Census Surname Data Pipeline

**New file: `src/prepare_census_data.py`**

- Downloads `https://www2.census.gov/topics/genealogy/2010surnames/names.zip`
- Extracts `Names_2010Census.csv`
- Processes into `src/data/census/surname_freq.json`: `{"SMITH": 1, "JOHNSON": 1, ...}` (uppercase surname → tier number)
- Tier thresholds per spec: Tier 1 (rank 1-100), Tier 2 (101-1000), Tier 3 (1001-10000), Tier 4 (10001+)
- Keeps raw CSV at `src/data/census/Names_2010Census.csv` for reference
- CLI: `python prepare_census_data.py` (no args)

**Path fix:** `bias_signals.py` already looks in `src/data/census/` (resolved via `Path(__file__).parent / "data" / "census"`). This is correct — all data lives under `src/data/`. The spec's file table says `data/census/` which is inconsistent; we follow the code's convention.

### 2. Audit Sidecar Persistence

**Changes to `src/run_pipeline.py`:**
- After `scan_meeting_json()` returns, create `src/data/audit_runs/` if needed
- Call `scan_result.audit_log.save(Path("src/data/audit_runs") / f"{scan_result.scan_run_id}.json")`
- Print the audit file path to stdout

**Changes to `src/conflict_scanner.py` CLI (`main()`):**
- Same — save audit sidecar after scan completes

**Fix surname tier tallying in `conflict_scanner.py`:**
- Before building `ScanAuditSummary`, iterate all contributions compared and count by surname tier
- Iterate flagged-only contributions and count by surname tier
- Pass all 10 tier distribution fields to `ScanAuditSummary` constructor
- Track `filtered_no_text_match` in the filter funnel

### 3. Ground Truth Review CLI

**New `--review` mode on `conflict_scanner.py`:**

```
python conflict_scanner.py --review --latest
python conflict_scanner.py --review --scan-run <uuid>
```

Interactive flow per decision:
1. Load audit sidecar from `src/data/audit_runs/{scan_run_id}.json`
2. For each `MatchingDecision` where `ground_truth is None`:
   - Display: donor name, amount, committee, agenda item, confidence, bias signals
   - Prompt: `[T]rue positive / [F]alse positive / [S]kip / [N]otes`
   - T/F: record verdict + timestamp in `ground_truth` and `ground_truth_source`
   - N: prompt for notes text, then re-prompt for T/F/S
   - S: move to next
3. Save updated sidecar back to same file
4. Print summary: "Reviewed X of Y decisions"

**New file: `src/ground_truth/officials.json`** — Richmond council member reference data (current + recent former) for review context display.

### 4. Periodic Bias Audit Module

**New file: `src/bias_audit.py`**

Core function: `bias_audit(audit_dir: Path, city_fips: str) -> dict`
- Loads all JSON sidecars from `src/data/audit_runs/`
- Filters to decisions with ground_truth verdicts
- Computes per-tier statistics: false positive rate by surname frequency tier, flag rate by name characteristics
- Minimum data gate: refuses to run with < 100 ground-truthed decisions (configurable via `--min-decisions`)
- Saves report to `src/data/audit_runs/bias_audit_report_{timestamp}.json`

CLI:
```
python bias_audit.py
python bias_audit.py --min-decisions 50
```

### 5. Comment Regeneration + Submission Prep

- Regenerate Feb 17 comment via `python run_pipeline.py --date 2026-02-17`
- Verify three-tier format: no raw confidence scores, no empty recipients, narrative prose
- Add `--output` flag to `run_pipeline.py` to save comment to a file
- Manual copy-paste for first submission (SMTP can come later)
- Document submission workflow in this design doc or CLAUDE.md

**Target:** Next upcoming Richmond council meeting.

## Architecture Decisions

1. **Interactive CLI for ground truth** (not batch file editing) — more natural for 1-4 flags per meeting, matches spec
2. **`prepare_census_data.py` as reusable script** (not one-time manual) — horizontal scaling needs this for every new city
3. **Dedicated `src/data/audit_runs/` directory** with UUID filenames — audit runs are their own entity, multiple scans per meeting date

## Files Changed / Created

| File | Action |
|------|--------|
| `src/prepare_census_data.py` | Create |
| `src/data/census/surname_freq.json` | Generated by script |
| `src/data/census/Names_2010Census.csv` | Downloaded by script |
| `src/run_pipeline.py` | Modify — add audit sidecar save + `--output` flag |
| `src/conflict_scanner.py` | Modify — add `--review` CLI, fix tier tallying, save audit in CLI mode |
| `src/bias_audit.py` | Create |
| `src/ground_truth/officials.json` | Create |
| `src/data/audit_runs/` | Create (directory) |
| Tests for all new functionality | Create |
