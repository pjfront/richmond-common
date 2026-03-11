# Scanner Batch Performance Optimization

**Date:** 2026-03-11
**Sprint:** S9.5 (batch rescan)
**Status:** Spec
**Publication tier:** N/A (pipeline internals, no public-facing changes)

## Problem

The v3 conflict scanner batch validation takes **3.8 hours** for 785 meetings (~17s/meeting). This blocks the S9.5 production rescan and makes iterative development painful. The root cause is O(n²) string matching: every contribution (~22K after prefilter) is checked against every agenda item (~25/meeting) across every meeting.

## Goal

Reduce batch scan time to **~10-15 minutes** without changing any output. Same flags, same confidence scores, same publication tiers. Pure internal optimization.

## Baseline Metrics

From `v2_validation_2026-03-09.json`:
- 785 meetings scanned
- 13,680 seconds (3.8 hours)
- ~17.4 seconds/meeting average
- 9,872 v2 flags produced

## Optimizations

### O1: Pre-normalize contributions (eliminate redundant normalize_text calls)

**File:** `conflict_scanner.py` — `prefilter_contributions()` and `signal_campaign_contribution()`

**Current behavior:** `normalize_text()` is called on donor_name and donor_employer inside the per-item loop in `signal_campaign_contribution()`. The same contribution is re-normalized for every agenda item in every meeting (~5,000+ times per contribution across the full batch).

**Change:** Compute and store normalized values during `prefilter_contributions()`:

```python
# In prefilter_contributions(), add to each contribution dict:
c["_norm_donor"] = normalize_text(donor_name)
c["_norm_employer"] = normalize_text(donor_employer) if donor_employer else ""
c["_norm_committee"] = normalize_text(committee)
c["_donor_words"] = set(w for w in c["_norm_donor"].split() if len(w) >= 4)
c["_employer_words"] = set(w for w in c["_norm_employer"].split() if len(w) >= 4)
```

In `signal_campaign_contribution()`, read `_norm_donor`, `_norm_employer`, `_norm_committee`, `_donor_words`, `_employer_words` from the contribution dict instead of recomputing. Fall back to computing if the keys are missing (backward compat for non-batch callers).

**Note:** `prefilter_contributions()` already removes self-donations (donor in committee name) and government donors, so the corresponding checks inside `signal_campaign_contribution()` at lines 1093-1133 are redundant for prefiltered contributions. However, retain them for safety (they're cheap with pre-cached values) and for the non-batch fallback path.

**Impact:** Eliminates ~600M redundant `normalize_text()` calls. Estimated 2-3x speedup on its own.

**Test impact:** None. Output identical. Existing tests pass because single-meeting callers still work (fallback path).

### O2: Word-token index for contribution pre-screening

**File:** `conflict_scanner.py` — new function + changes to `signal_campaign_contribution()`

**Current behavior:** The word-overlap pre-screen (lines 1135-1140) already filters contributions by checking if donor/employer words overlap with item text words. But it iterates **all** contributions to do this check.

**Change:** Build an inverted index after prefiltering:

```python
def build_contribution_word_index(contributions: list[dict]) -> dict[str, list[int]]:
    """Map each 4+ char word from donor names and employers to contribution indices."""
    index: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(contributions):
        for word in c.get("_donor_words", set()) | c.get("_employer_words", set()):
            index[word].append(i)
    return index
```

In the per-item loop, instead of iterating all contributions:

```python
# Get candidate indices from word index
candidate_indices = set()
for word in text_words:
    candidate_indices.update(contrib_word_index.get(word, []))

# Only iterate matching contributions
for idx in candidate_indices:
    contribution = contributions[idx]
    # ... existing matching logic EXCEPT the word-overlap pre-screen (lines 1135-1140),
    # which is already handled by the index. All other per-contribution checks remain:
    # - dedup check (lines 1087-1090)
    # - council member donor check (lines 1093-1098)
    # - government donor check (lines 1101-1110)
    # - self-donation check (lines 1113-1117)
    # These are cheap with pre-cached normalized values from O1.
```

**Interface change:** `signal_campaign_contribution()` gains an optional `contrib_word_index` parameter. When provided (batch mode), uses indexed lookup instead of linear scan. When None (single-meeting mode), falls back to current linear scan with word-overlap pre-screen.

**Critical implementation note:** When using the index path, skip ONLY the word-overlap check (lines 1135-1140). Retain all other per-contribution checks (dedup, council member, government donor, self-donation). The index replaces the word-overlap filter, not the semantic filters.

**Impact:** Instead of checking 22K contributions per item, typically checks 50-200. ~100x reduction in the inner loop iteration count. Estimated 5-10x speedup on the contribution matching specifically.

**Test impact:** None. Output identical. Index is an acceleration structure only.

### O3: Memoize name_in_text() results

**File:** `conflict_scanner.py` — `name_in_text()`

**Current behavior:** `name_in_text(name, text)` normalizes both arguments and does a substring check. The same (name, text) pair can be checked multiple times across items with similar text, and across alias lookups.

**Change:** Add a simple dict cache inside scan_meeting_json scope (not global, to avoid cross-meeting state leakage):

```python
# In scan_meeting_json(), create cache:
_name_in_text_cache: dict[tuple[str, str], tuple[bool, str]] = {}

# Pass to signal detectors, or use a wrapper:
def cached_name_in_text(name, text, cache):
    key = (name, text[:200])  # truncate text key to avoid memory bloat
    if key in cache:
        return cache[key]
    result = name_in_text(name, text)
    cache[key] = result
    return result
```

**Implementation:** Add a `name_in_text_cache: dict` field to the `_ScanContext` dataclass (initialized to `{}`). Pass `ctx.name_in_text_cache` to a `cached_name_in_text()` wrapper used in `signal_campaign_contribution()`. The cache is scoped per `scan_meeting_json()` call since a new `_ScanContext` is created per meeting. This provides automatic lifecycle management without global state.

**Impact:** 10-15% speedup. Low effort.

**Test impact:** None. Pure acceleration.

### O4: Pre-group Form 700 interests by council member

**File:** `conflict_scanner.py` — `scan_meeting_json()`

**Current behavior:** All 150-200 Form 700 interests are passed to signal detectors, which iterate all of them per item. But only ~7 council members are present at any meeting. Interests for non-present members can never produce valid flags.

**Change:** In `scan_meeting_json()`, filter `form700_interests` to only those whose `council_member` matches a member present at the meeting:

```python
# After building council_member_names, collect raw names of present members:
present_members_raw = [m.get("name", "") for m in meeting_data.get("members_present", [])]
present_members_norm = {normalize_text(name) for name in present_members_raw if name}

# Filter form700 interests to present members
if present_members_norm:
    relevant_interests = [
        interest for interest in form700_interests
        if normalize_text(interest.get("council_member", "")) in present_members_norm
        or any(
            names_match(interest.get("council_member", ""), raw_name)[0]
            for raw_name in present_members_raw if raw_name
        )
    ]
else:
    relevant_interests = form700_interests  # fallback: check all (e.g., eSCRIBE agendas)
```

**Note:** `names_match()` normalizes both arguments internally, so pass raw names (not pre-normalized) to avoid asymmetry. The `present_members_norm` set is used for the fast exact-match check; `present_members_raw` is used for the fuzzy `names_match()` fallback.

Pass `relevant_interests` to the Form 700 signal detectors instead of the full list.

**Impact:** ~70% reduction in Form 700 iterations. Estimated 1.2-1.3x overall speedup.

**Test impact:** None. Non-present members can't produce flags anyway (no vote record).

### O5: Parallel per-meeting scanning

**File:** `batch_scan.py` — `run_validation()` and `run_batch_scan()`

**Current behavior:** Meetings are scanned sequentially in a for loop.

**Change:** Use `concurrent.futures.ProcessPoolExecutor` to scan meetings in parallel.

```python
from concurrent.futures import ProcessPoolExecutor, as_completed

def _scan_single_meeting(meeting_id, meeting_date, city_fips, contributions, form700_interests, expenditures):
    """Worker function for parallel scanning."""
    conn = _fresh_conn()
    try:
        result = scan_meeting_db(
            conn, str(meeting_id), city_fips,
            contributions=contributions,
            form700_interests=form700_interests,
            expenditures=expenditures,
        )
        return (meeting_id, meeting_date, result, None)
    except Exception as e:
        return (meeting_id, meeting_date, None, str(e))
    finally:
        conn.close()
```

**Key design decisions:**

1. **Data sharing:** Contributions and Form 700 interests are pre-loaded once and passed to workers. Python's `ProcessPoolExecutor` serializes these via pickle. For 22K contribution dicts, this is ~5-10MB per worker — acceptable.

2. **Connection management:** Each worker creates its own DB connection (required for process isolation). Connections are created and closed per-worker, not per-meeting.

3. **Worker count:** Default to `min(os.cpu_count(), 8)`. CLI flag `--workers N` for override.

4. **Progress reporting:** Use a shared counter or periodic aggregation. Workers return results; main process aggregates and prints progress.

5. **Validation mode:** Read-only, no state concerns. Workers return `ScanResult` objects; main process aggregates counts.

6. **Batch scan mode (writes):** Workers return flags; main process handles DB writes (supersede + insert) sequentially. This avoids concurrent write conflicts on `conflict_flags`. The `official_cache` and `item_cache` dicts live in the main process and are populated as workers return results. Workers only return `ScanResult` objects containing council_member names and agenda_item_numbers. The main process calls `resolve_official_id()` and `resolve_agenda_item_id()` using its own connection and caches.

7. **Fallback:** `--workers 1` disables parallelization for debugging.

**Impact:** ~4-6x speedup on 8-core machine.

**Test impact:** Existing tests unaffected (they use `scan_meeting_json` directly). Add a new test for the parallel wrapper.

### Bonus: Flush print output

**File:** `batch_scan.py`

Add `flush=True` to all `print()` calls in `run_validation()` and `run_batch_scan()`. This ensures progress is visible when stdout is piped or buffered (e.g., when run from Claude Code).

## Combined Performance Estimate

O1 and O2 address overlapping work (both reduce contribution-loop cost), so their speedups don't multiply independently. Realistic estimate:

| Optimization | Independent factor | Notes |
|---|---|---|
| O1 + O2 combined | 8-15x | O1 eliminates redundant normalization; O2 eliminates redundant iteration. Together they transform the contribution loop from O(C) to O(~100) per item. |
| O3: name_in_text cache | 1.1-1.2x | Modest, essentially free |
| O4: Form 700 filter | 1.2-1.3x | Reduces Form 700 loops by ~70% |
| O5: Parallelization | 4-6x | CPU-bound work distributes well |

**Conservative estimate (O1-O4 only):** 10-20x → **3.8 hours becomes 12-23 minutes**
**With parallelization (O1-O5):** 40-100x → **3.8 hours becomes 2-6 minutes**

These are estimates. The benchmark after implementation is the source of truth.

## Implementation Order

1. O1 (pre-normalize) — foundational, O2 depends on it
2. O2 (word index) — biggest single win after O1
3. O3 (name_in_text cache) — quick add
4. O4 (Form 700 filter) — quick add
5. O5 (parallelization) — largest structural change, do last
6. Bonus (flush prints) — trivial, do anytime

After each step, run `python3 -u batch_scan.py --validate --meeting-id <sample>` to verify identical output.

After all steps, run full validation and compare report against `src/data/validation_reports/v3_validation_2026-03-10.json`.

## Testing Strategy

- **Unit tests:** No new unit tests needed for O1-O4 (output-preserving optimizations). Add test for `build_contribution_word_index()`.
- **Integration test:** Run single-meeting validation before and after, diff the output.
- **Benchmark:** Time the full 785-meeting validation run. Target: < 15 minutes.
- **Regression:** Full pytest suite must pass unchanged.

## Files Modified

| File | Changes |
|---|---|
| `src/conflict_scanner.py` | O1 (prefilter), O2 (word index + signal_campaign_contribution), O3 (name_in_text cache), O4 (Form 700 filter) |
| `src/batch_scan.py` | O5 (parallel workers), bonus (flush prints), CLI `--workers` flag |

## Risks

- **O5 (parallelization):** Pickle serialization of contribution data adds overhead. If contributions are very large, the serialization cost may offset parallelism gains. Mitigation: benchmark with/without parallelization.
- **O2 (word index):** If word distribution is highly skewed (one common word matches 10K+ contributions), the index provides less benefit. Mitigation: the existing word-length filter (≥4 chars) already removes the worst offenders.
- **Cache memory (O3):** For very long meetings with many items, the cache could grow large. Mitigation: truncate text key to 200 chars.

## Success Criteria

1. Full 785-meeting validation completes in < 15 minutes
2. Validation report numbers match pre-optimization run (same flag counts, same tier distribution)
3. All existing tests pass
4. Progress output is visible during execution (flush fix)
