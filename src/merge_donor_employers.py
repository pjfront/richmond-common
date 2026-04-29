"""Merge donor rows with same name + near-equivalent employer strings.

The donors table's natural-key constraint is
``UNIQUE (city_fips, normalized_name, COALESCE(employer, ''))`` — so any
variation in the freeform `employer` field produces a separate donor
row, even when the underlying person is the same. From the I124
ground-truth comparison:

  Buffy Wicks       — "California" vs "California State Assembly"
  Davillier Sloan   — "" vs "N/A"
  Carl Adams        — "Developer" vs ""

This script collapses such clusters under three conservative rules.
The rules are intentionally narrow — same-name-different-employer can
also be two genuinely different people (the John Smith problem), so we
only merge when the relationship is unambiguous:

  Rule 1 (empty-equivalent): all rows in the cluster have employers in
    {NULL, "", "N/A", "n/a", "None", "none", and similar no-employer
    placeholders}. Merge into a single canonical row with employer=NULL.

  Rule 2 (one-empty-one-specific): one row's employer is empty-equivalent
    and exactly one other is specific. Merge into the specific row.

  Rule 3 (substring-of): one row's normalized employer is a substring
    of another's (>=4 chars to avoid spurious "M" ⊂ "Mike Johnson"
    matches). Merge into the more-specific row.

Anything else — two genuinely distinct specific employers — is left
alone for human review or B.46 entity resolution.

This is the donor-side counterpart to ``canonical_donors.py`` (which
handles known PAC/union/corp aliases) and complements
``dedup_contributions.py`` (which handles cross-filing 497 dupes after
donor identity is settled). Run order:
  1. canonical_donors backfill (PAC alias collapse)
  2. THIS script (individual donor employer collapse)
  3. dedup_contributions (catches any same-(donor, amount, date,
     committee) duplicates that surface from the merge)

Reads from `donors` and `contributions`. Writes only the rows that need
to change. Idempotent — re-running on a cleaned DB is a no-op.

Usage::

    python src/merge_donor_employers.py            # dry run preview
    python src/merge_donor_employers.py --apply    # write changes
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)
sys.path.insert(0, str(_ROOT / "src"))

import psycopg2  # noqa: E402

CITY_FIPS = "0660620"

# Strings that mean "no employer" in real-world filings. All compared
# in lowercase after stripping whitespace and trailing punctuation.
EMPTY_EQUIVALENTS = {
    "", "n/a", "na", "none", "null", "not employed", "not employeed",
    "not empoloyed", "unemployed", "no employer", "self", "self employed",
    "self-employed", "selfemployed", "retired",
}

# Minimum length for a substring-of merge to fire. Below this, "M" or
# "CA" can match too many distinct employers spuriously.
MIN_SUBSTRING_LEN = 4


def _normalize_emp(emp: str | None) -> str:
    """Lowercase, collapse whitespace, strip surrounding punctuation."""
    if emp is None:
        return ""
    s = emp.strip().lower()
    s = re.sub(r"[\s.,'\"()]+", " ", s).strip()
    return s


def _is_empty_eq(emp: str | None) -> bool:
    """True when the employer string is some flavor of 'no employer'."""
    return _normalize_emp(emp) in EMPTY_EQUIVALENTS


def _substring_match(a: str, b: str) -> bool:
    """True when normalized employers are equivalent or one is a substring
    of the other (and is at least MIN_SUBSTRING_LEN chars).

    Equivalent normalized strings ("Friends of the Earth" vs "Friends Of
    The Earth") DO match — they're the same employer with case-only
    differences. The original implementation excluded equivalents because
    of a misread of the spec; in practice case-only variations are
    common in NetFile data and need to merge.

    Words are also checked individually so "California" ⊂ "California
    State Assembly" matches by whole-word containment, not just raw
    string-in-string."""
    na, nb = _normalize_emp(a), _normalize_emp(b)
    if not na or not nb:
        return False
    if na == nb:
        return True  # case-equivalent — same employer
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) < MIN_SUBSTRING_LEN:
        return False
    if short in long_:
        return True
    # Also match if every word of `short` appears as a whole word in `long_`.
    short_words = set(short.split())
    long_words = set(long_.split())
    if short_words and short_words.issubset(long_words):
        return True
    return False


def _pick_canonical(rows: list[dict]) -> dict:
    """Pick the row to keep from a merge cluster.

    Prefers (in order): non-empty employer; longer employer; lower id
    (oldest record). Returns the chosen row dict.
    """
    def score(r):
        emp_norm = _normalize_emp(r["employer"])
        is_specific = not _is_empty_eq(r["employer"])
        return (is_specific, len(emp_norm), -hash(str(r["id"])))
    return max(rows, key=score)


def _plan_cluster(rows: list[dict]) -> list[tuple[str, str, str]]:
    """Decide what to merge in a single normalized_name cluster.

    Returns a list of (drop_id, target_id, reason) triples. Empty list
    means leave the cluster alone.
    """
    if len(rows) < 2:
        return []

    # Bucket by empty-equivalent vs specific.
    empties = [r for r in rows if _is_empty_eq(r["employer"])]
    specifics = [r for r in rows if not _is_empty_eq(r["employer"])]

    plan: list[tuple[str, str, str]] = []

    # Rule 1: all empties — collapse into one.
    if not specifics and len(empties) > 1:
        keeper = _pick_canonical(empties)
        for r in empties:
            if r["id"] != keeper["id"]:
                plan.append((r["id"], keeper["id"], "all-empty"))
        return plan

    # Rule 2: empties + 1 specific → merge empties into the specific.
    if specifics and len(specifics) == 1 and empties:
        keeper = specifics[0]
        for r in empties:
            plan.append((r["id"], keeper["id"], "empty→specific"))
        return plan

    # Rule 2 (extended): empties + multiple specifics. Merge empties
    # into the canonical specific (longest employer); then handle
    # specific-vs-specific via Rule 3.
    keeper_specific = _pick_canonical(specifics) if specifics else None
    if specifics and empties:
        for r in empties:
            plan.append((r["id"], keeper_specific["id"], "empty→specific"))

    # Rule 3: among the specific employers, merge substring-related pairs.
    # Build groups by transitive closure of substring_match.
    if len(specifics) > 1:
        # Group via union-find.
        parent = {r["id"]: r["id"] for r in specifics}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for i, a in enumerate(specifics):
            for b in specifics[i+1:]:
                if _substring_match(a["employer"], b["employer"]):
                    union(a["id"], b["id"])

        groups: dict[str, list[dict]] = {}
        for r in specifics:
            root = find(r["id"])
            groups.setdefault(root, []).append(r)

        for grp in groups.values():
            if len(grp) < 2:
                continue
            keeper = _pick_canonical(grp)
            for r in grp:
                if r["id"] != keeper["id"]:
                    plan.append((r["id"], keeper["id"], "substring-of"))

    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="Write changes (default dry-run)")
    parser.add_argument("--city-fips", default=CITY_FIPS)
    args = parser.parse_args()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        """SELECT id, name, normalized_name, employer
             FROM donors
            WHERE city_fips = %s
            ORDER BY normalized_name, id""",
        (args.city_fips,),
    )
    all_rows = [
        {"id": str(r[0]), "name": r[1], "normalized_name": r[2], "employer": r[3]}
        for r in cur.fetchall()
    ]
    print(f"Scanning {len(all_rows)} donors...")

    # Group by normalized_name.
    clusters: dict[str, list[dict]] = {}
    for r in all_rows:
        clusters.setdefault(r["normalized_name"], []).append(r)

    full_plan: list[tuple[str, str, str, str]] = []  # (drop, keeper, reason, name)
    for nname, rows in clusters.items():
        if len(rows) < 2:
            continue
        plan = _plan_cluster(rows)
        for drop_id, keep_id, reason in plan:
            full_plan.append((drop_id, keep_id, reason, rows[0]["name"]))

    if not full_plan:
        print("Nothing to do — no merge candidates found.")
        return

    # Group plan items by keeper for readable preview.
    by_keeper: dict[str, list[tuple[str, str, str]]] = {}
    for drop_id, keep_id, reason, name in full_plan:
        by_keeper.setdefault(keep_id, []).append((drop_id, reason, name))

    print(f"\n{len(full_plan)} donor row(s) will be merged into "
          f"{len(by_keeper)} keeper(s):\n")

    # Look up details for display.
    id_to_row = {r["id"]: r for r in all_rows}
    for keep_id, drops in sorted(by_keeper.items(), key=lambda x: id_to_row[x[0]]["normalized_name"]):
        keeper = id_to_row[keep_id]
        emp_str = repr(keeper["employer"])[:40] if keeper["employer"] else "<NULL>"
        print(f"  KEEP  {keeper['name'][:35]:35s} emp={emp_str}")
        for drop_id, reason, _ in drops:
            d = id_to_row[drop_id]
            d_emp = repr(d["employer"])[:40] if d["employer"] else "<NULL>"
            print(f"   <-   {d['name'][:35]:35s} emp={d_emp}  [{reason}]")
        print()

    if not args.apply:
        print("(Dry run — pass --apply to execute.)")
        return

    # Apply: re-point contributions, then drop donor rows. Same machinery
    # as backfill_canonical_donors but keyed on (drop_id → keep_id) pairs.
    print("Applying merges in a single transaction...")
    repointed = 0
    duplicate_drops = 0
    deleted_donors = 0
    employer_promotions = 0

    for drop_id, keep_id, reason, _ in full_plan:
        # First, if the keeper currently has NULL/empty employer and the
        # drop has a specific one (rare — Rule 2 normally puts the
        # specific row as keeper), promote the employer onto the keeper.
        cur.execute("SELECT employer FROM donors WHERE id = %s", (keep_id,))
        keep_emp = (cur.fetchone() or [None])[0]
        cur.execute("SELECT employer, occupation FROM donors WHERE id = %s", (drop_id,))
        drop_row = cur.fetchone() or (None, None)
        drop_emp, drop_occ = drop_row
        if _is_empty_eq(keep_emp) and not _is_empty_eq(drop_emp):
            cur.execute(
                "UPDATE donors SET employer = %s WHERE id = %s",
                (drop_emp, keep_id),
            )
            employer_promotions += 1
        # Backfill occupation if keeper has none and drop does.
        if drop_occ:
            cur.execute(
                """UPDATE donors SET occupation = COALESCE(occupation, %s)
                    WHERE id = %s""",
                (drop_occ, keep_id),
            )

        # Re-point contributions, deleting any that would conflict.
        cur.execute(
            """SELECT id, amount, contribution_date, committee_id
                 FROM contributions WHERE donor_id = %s""",
            (drop_id,),
        )
        for cid, amount, cdate, comm_id in cur.fetchall():
            cur.execute(
                """SELECT id FROM contributions
                    WHERE donor_id = %s AND amount = %s
                      AND contribution_date = %s
                      AND committee_id IS NOT DISTINCT FROM %s
                      AND id <> %s""",
                (keep_id, amount, cdate, comm_id, cid),
            )
            if cur.fetchone():
                cur.execute("DELETE FROM contributions WHERE id = %s", (cid,))
                duplicate_drops += 1
            else:
                cur.execute(
                    "UPDATE contributions SET donor_id = %s WHERE id = %s",
                    (keep_id, cid),
                )
                repointed += 1

        # Re-point entity_links FK. The Sprint-26 entity-resolution
        # work attaches `donor_id` to person/org link rows; we keep
        # them but flip to the surviving canonical donor.
        cur.execute(
            "UPDATE entity_links SET donor_id = %s WHERE donor_id = %s",
            (keep_id, drop_id),
        )

        # Drop the orphan donor.
        cur.execute("DELETE FROM donors WHERE id = %s", (drop_id,))
        deleted_donors += 1

    conn.commit()
    print(f"\nDone.")
    print(f"  donors merged + deleted:   {deleted_donors}")
    print(f"  contributions re-pointed:  {repointed}")
    print(f"  duplicate contribs gone:   {duplicate_drops}")
    print(f"  employer promotions:       {employer_promotions}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
