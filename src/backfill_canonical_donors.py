"""Backfill: collapse alias-drifted donor rows into their canonical forms.

One-shot cleanup for I124 item (3). Future contribution loads apply
``canonical_donors.canonicalize_donor_name`` at insert time (via
``db.load_contributions_to_db``), but rows that were loaded before the
canonical map shipped retain the OCR/alias surface form. This script
walks every Richmond donor, looks up the canonical name, and either
renames the donor in place (when no conflict exists) or re-points all
its contributions to the canonical donor and deletes the duplicate.

Reads from `donors` and `contributions`. Writes only the rows that
need to change. Safe to re-run (idempotent — already-canonical donors
short-circuit on the first lookup).

Usage::

    python src/backfill_canonical_donors.py            # dry run
    python src/backfill_canonical_donors.py --apply    # write changes
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)
sys.path.insert(0, str(_ROOT / "src"))

import psycopg2  # noqa: E402

from canonical_donors import canonicalize_donor_name  # noqa: E402

CITY_FIPS = "0660620"


def _normalize_for_db(name: str) -> str:
    """Mirror db._normalize_name's behavior for the unique constraint."""
    import re as _re
    s = (name or "").lower().strip()
    s = _re.sub(r"\s+", " ", s)
    return s


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="Write changes (default is dry-run preview)")
    args = parser.parse_args()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, employer FROM donors WHERE city_fips = %s",
        (CITY_FIPS,),
    )
    all_donors = cur.fetchall()
    print(f"Scanning {len(all_donors)} Richmond donors...")

    plan: list[dict] = []
    canonical_index: dict[str, uuid.UUID] = {}  # norm_name -> id

    # First pass: build an index keyed on canonical name only. Employer
    # is meaningful for individual donor disambiguation (two "John Smith"
    # working at different employers are distinct people), but for the
    # PACs/unions/corporations enumerated in canonical_donors.md, the
    # employer field is irrelevant — we collapse to a single legal-entity
    # row regardless of whatever employer string the original filing
    # carried. Earliest-created row in DB wins as merge target.
    for did, name, _employer in all_donors:
        canonical = canonicalize_donor_name(name)
        norm_canon = _normalize_for_db(canonical)
        if canonical == name and norm_canon not in canonical_index:
            canonical_index[norm_canon] = did

    # Second pass: plan moves for any donor whose canonicalized name differs.
    # When the canonical donor doesn't yet exist in DB but multiple raw rows
    # map to the same canonical target, the first one renames in place and
    # the rest merge into it. The canonical_index is updated in-flight so
    # subsequent rows see the newly-promoted target.
    for did, name, employer in all_donors:
        canonical = canonicalize_donor_name(name)
        if canonical == name:
            continue
        norm_canon = _normalize_for_db(canonical)
        target_id = canonical_index.get(norm_canon)
        if target_id is None:
            # First raw row for this canonical — promote it via rename.
            canonical_index[norm_canon] = did
        plan.append({
            "raw_id": did,
            "raw_name": name,
            "canonical": canonical,
            "employer": employer,
            "target_id": target_id,  # None means rename-in-place
        })

    if not plan:
        print("Nothing to do — all donors are already canonical.")
        return

    print(f"\n{len(plan)} donors will be canonicalized:\n")
    for p in plan:
        if p["target_id"]:
            print(f"  MERGE  {p['raw_name'][:50]:50s} -> {p['canonical']}")
        else:
            print(f"  RENAME {p['raw_name'][:50]:50s} -> {p['canonical']}")

    if not args.apply:
        print("\n(Dry run — pass --apply to execute.)")
        return

    print("\nApplying changes in a single transaction...")

    # Pre-flight: cache the unique-constraint shape so we can re-point
    # contributions safely. The constraint on contributions is
    # (donor_id, amount, contribution_date, committee_id) WHERE
    # contribution_date IS NOT NULL. Re-pointing donor_id can cause a
    # duplicate; in that case we delete the duplicate row instead.

    repointed_contribs = 0
    deleted_dup_contribs = 0
    deleted_donors = 0
    renamed_donors = 0

    for p in plan:
        if p["target_id"]:
            # Merge: re-point contributions, delete duplicates, drop donor.
            cur.execute(
                """SELECT id, amount, contribution_date, committee_id
                     FROM contributions
                    WHERE donor_id = %s""",
                (p["raw_id"],),
            )
            for row_id, amount, cdate, comm_id in cur.fetchall():
                # Check whether the target already has this contribution.
                cur.execute(
                    """SELECT id FROM contributions
                        WHERE donor_id = %s AND amount = %s
                          AND contribution_date = %s
                          AND committee_id IS NOT DISTINCT FROM %s
                          AND id <> %s""",
                    (p["target_id"], amount, cdate, comm_id, row_id),
                )
                if cur.fetchone():
                    # Duplicate — delete this raw row.
                    cur.execute("DELETE FROM contributions WHERE id = %s", (row_id,))
                    deleted_dup_contribs += 1
                else:
                    # Re-point.
                    cur.execute(
                        "UPDATE contributions SET donor_id = %s WHERE id = %s",
                        (p["target_id"], row_id),
                    )
                    repointed_contribs += 1

            # Drop the now-orphaned donor row.
            cur.execute("DELETE FROM donors WHERE id = %s", (p["raw_id"],))
            deleted_donors += 1
        else:
            # Rename in place — no conflicting target exists.
            norm = _normalize_for_db(p["canonical"])
            cur.execute(
                """UPDATE donors
                      SET name = %s, normalized_name = %s
                    WHERE id = %s""",
                (p["canonical"], norm, p["raw_id"]),
            )
            renamed_donors += 1

    conn.commit()

    print(f"\nDone.")
    print(f"  donors renamed:           {renamed_donors}")
    print(f"  donors merged + deleted:  {deleted_donors}")
    print(f"  contributions re-pointed: {repointed_contribs}")
    print(f"  duplicate contribs gone:  {deleted_dup_contribs}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
