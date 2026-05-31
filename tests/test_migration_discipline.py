"""Migration filename discipline.

Migrations in src/migrations/ are the source of truth for schema. Apply
order on a fresh install is lexicographic by filename, so duplicate
numeric prefixes cause non-deterministic ordering: which `068_*.sql`
runs first depends on filesystem enumeration order.

In practice this has never bitten because all our migrations are
idempotent. But "we've been lucky" is not a guarantee. This test makes
the rule explicit: every migration must have a unique numeric prefix.

Suffix variants (e.g., `103a_*`) are allowed when a migration needs to
land between two existing numbers — the suffix sorts after the bare
prefix lexicographically, which is the intent.

This file also enforces the src/ <-> supabase/ mirror discipline
(D61, 2026-05-18). The mirror gap was the structural hole that
allowed D60: 108_community_comments.sql lived in src/migrations/ for
~7 weeks with frontend code wired up to a table that production
never received, because nobody created the supabase/migrations/
mirror that `supabase db push` actually applies.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_MIGRATIONS_DIR = _ROOT / "src" / "migrations"
_SUPABASE_MIGRATIONS_DIR = _ROOT / "supabase" / "migrations"

# DB-gated tests follow the repo idiom (see test_filing_period_briefing.py):
# CI sets a fake "test" DATABASE_URL, so a live-ledger check must require
# BOTH a real DATABASE_URL and an explicit RICHMOND_RUN_DB_TESTS=1 opt-in.
# In CI these skip; the every-session enforcement lives in
# system_health.collect_risk_summary (real DB) instead.
#
# load_dotenv populates DATABASE_URL from the repo-root .env locally. In CI
# there is no committed .env, so DATABASE_URL stays the fake "test" value
# the workflow sets — _HAS_DB is False and the test skips. The explicit
# RICHMOND_RUN_DB_TESTS=1 second gate prevents prod tests auto-running off
# a stray local .env.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env", override=True)
_DB_URL = os.getenv("DATABASE_URL") or ""
_HAS_DB = bool(_DB_URL) and "test" not in _DB_URL
_RUN_DB_TESTS = os.getenv("RICHMOND_RUN_DB_TESTS") == "1"


def _migration_files() -> list[Path]:
    return sorted(p for p in _MIGRATIONS_DIR.glob("*.sql"))


def _description(filename: str) -> str | None:
    """Extract the descriptive portion of a migration filename.

    src/migrations:      `NNN[suffix]_description.sql` -> `description`
    supabase/migrations: `TIMESTAMP_description.sql`   -> `description`

    Both filename schemes terminate the prefix with `_` followed by the
    same descriptive suffix, so a single regex covers both.
    """
    m = re.match(r"^[0-9]+[a-z]*_(.+)\.sql$", filename, re.IGNORECASE)
    return m.group(1) if m else None


def _src_descriptions() -> dict[str, str]:
    """Map of description -> filename for every src/migrations entry."""
    return {
        _description(p.name): p.name
        for p in _migration_files()
        if _description(p.name) is not None
    }


def _supabase_descriptions() -> dict[str, str]:
    """Map of description -> filename for every supabase/migrations entry."""
    return {
        _description(p.name): p.name
        for p in sorted(_SUPABASE_MIGRATIONS_DIR.glob("*.sql"))
        if _description(p.name) is not None
    }


def test_no_duplicate_numeric_prefixes():
    """Every migration filename has a unique numeric prefix.

    Filename grammar: `NNN[suffix]_description.sql` where NNN is the
    numeric prefix and `suffix` is an optional alphabetic disambiguator
    (e.g., `103a`). The numeric portion plus suffix together must be
    unique across the directory.

    The renumbering on 2026-05-11 cleared three collisions:
      068_community_voice + 068_community_comments
      082_recap_emailed_at + 082_neighborhood_councils
      077b_fix_find_similar_items (variant suffix)
    """
    pattern = re.compile(r"^(\d+)([a-z]*)_")
    groups: dict[str, list[str]] = defaultdict(list)
    for path in _migration_files():
        match = pattern.match(path.name)
        if match is None:
            pytest.fail(
                f"Migration filename does not match `NNN[suffix]_description.sql`: "
                f"{path.name}"
            )
        key = match.group(1) + match.group(2)
        groups[key].append(path.name)

    collisions = {key: names for key, names in groups.items() if len(names) > 1}
    assert not collisions, (
        "Migration prefix collisions (would cause non-deterministic apply order on "
        f"fresh install):\n"
        + "\n".join(
            f"  {key}: {names}" for key, names in sorted(collisions.items())
        )
        + "\n\nRename the later migration forward to the next free slot. The earlier "
        "one (by supabase/migrations/ timestamp) keeps its prefix."
    )


def test_migration_filenames_are_well_formed():
    """Every migration filename matches `NNN[suffix]_lowercase_description.sql`."""
    pattern = re.compile(r"^\d+[a-z]*_[a-z][a-z0-9_]*\.sql$")
    bad = [p.name for p in _migration_files() if not pattern.match(p.name)]
    assert not bad, (
        f"Migration filenames not matching `NNN[suffix]_lowercase_description.sql`: "
        f"{bad}"
    )


def test_prefixes_dense_enough_to_notice_skips():
    """Sanity check: no huge gaps in the numeric sequence.

    A gap of more than 20 between consecutive prefixes usually means
    someone reserved a range and forgot to use it, or a renumbering
    overshot. Flag for review but don't hard-fail — there are legitimate
    reasons (e.g., 110 jumped from 107 after the 2026-05-11 collision
    renumbering used 108/109/110 for the three displaced files).
    """
    pattern = re.compile(r"^(\d+)")
    prefixes = sorted({
        int(pattern.match(p.name).group(1))
        for p in _migration_files()
        if pattern.match(p.name)
    })
    big_gaps = [
        (a, b) for a, b in zip(prefixes, prefixes[1:])
        if b - a > 20
    ]
    if big_gaps:
        # Informational only.
        print(f"\nMigration numeric gaps > 20: {big_gaps}")


# ──────────────────────────────────────────────────────────────────
# D61: src/migrations <-> supabase/migrations mirror discipline
# ──────────────────────────────────────────────────────────────────
#
# Every src/migrations/NNN_*.sql must have a corresponding mirror in
# supabase/migrations/TIMESTAMP_*.sql. `supabase db push` reads only
# the timestamped mirror directory; a src/ migration without a mirror
# is invisible to production, but src/migrations/ alone looks like the
# change shipped.
#
# This is exactly the bug shape that produced D60 (2026-03-28 →
# 2026-05-18): community_comments was committed to src/migrations/ +
# frontend wired up + 7-week silent breakage in public view because no
# one created the supabase/migrations/ mirror.

ALLOWED_UNMIRRORED: dict[str, str] = {
    # Empty by design. Adding an entry means a src/migrations/NNN_*.sql
    # is intentionally NOT in supabase/migrations/ (e.g., destructive
    # operation pending operator review). The default reflex when
    # adding a new src/migrations file is to create the mirror in the
    # same commit; this allowlist is the rare exception.
}


def test_every_src_migration_has_supabase_mirror():
    """Every src/migrations/NNN_*.sql must have a supabase/migrations/
    TIMESTAMP_*.sql mirror with the same descriptive suffix.

    Without the mirror, `supabase db push` skips the migration and
    production never receives the change — but src/migrations/ looks
    complete. This is the D60 bug shape. Catching it at the test layer
    is the structural fix.

    An intentional exception goes in ALLOWED_UNMIRRORED above with a
    documented reason. Default reflex when adding a new src/migrations
    entry: create the mirror in the same commit.
    """
    src_descs = _src_descriptions()
    supabase_descs = _supabase_descriptions()

    unmirrored = {
        desc: filename
        for desc, filename in src_descs.items()
        if desc not in supabase_descs
    }
    unexpected_unmirrored = {
        desc: filename
        for desc, filename in unmirrored.items()
        if filename not in ALLOWED_UNMIRRORED
    }

    assert not unexpected_unmirrored, (
        f"src/migrations entries with no supabase/migrations mirror: "
        f"{sorted(unexpected_unmirrored.values())}.\n\n"
        f"This is the D60 silent-failure shape — the SQL is in the repo "
        f"and may look like it shipped, but `supabase db push` reads only "
        f"the timestamped supabase/migrations/ directory and skips the "
        f"src/ file entirely. Production never receives the schema "
        f"change.\n\n"
        f"Resolution:\n"
        f"  - Default: create supabase/migrations/YYYYMMDDHHMMSS_<desc>.sql "
        f"with identical SQL in the same commit, then `supabase db push`.\n"
        f"  - Intentional exception (rare): add the filename to "
        f"ALLOWED_UNMIRRORED in tests/test_migration_discipline.py with "
        f"a documented reason. The D60 case is the canonical example — "
        f"the migration is intentionally not in supabase/ because the "
        f"feature is operator-gated pending pre-build fixes."
    )


def test_every_supabase_migration_has_src_source():
    """Every supabase/migrations entry must have a matching
    src/migrations source.

    A supabase/ mirror without a src/ source means someone hand-edited
    the timestamped directory directly, bypassing the canonical source.
    The mirror would still be applied by `supabase db push` but the
    schema change wouldn't survive a fresh-install rebuild from
    src/migrations/.
    """
    src_descs = _src_descriptions()
    supabase_descs = _supabase_descriptions()

    orphan_mirrors = {
        desc: filename
        for desc, filename in supabase_descs.items()
        if desc not in src_descs
    }

    assert not orphan_mirrors, (
        f"supabase/migrations entries with no src/migrations source: "
        f"{sorted(orphan_mirrors.values())}.\n\n"
        f"Hand-edited mirror without canonical source. The change "
        f"applies to live Supabase via `supabase db push` but a fresh "
        f"install from src/migrations/ would NOT reproduce it. Copy the "
        f"SQL into src/migrations/NNN_<description>.sql (next free "
        f"prefix per tests/test_migration_discipline.py)."
    )


def test_allowed_unmirrored_only_shrinks():
    """Entries in ALLOWED_UNMIRRORED that no longer match a real
    src/migrations file are stale.

    Either the migration was deleted (then the allowlist entry is dead
    weight) or it was finally mirrored (then the allowlist entry should
    be removed in the same commit that created the mirror, to lock in
    the win).
    """
    src_filenames = {p.name for p in _migration_files()}
    supabase_descs = _supabase_descriptions()

    stale = []
    for filename, reason in ALLOWED_UNMIRRORED.items():
        if filename not in src_filenames:
            stale.append(f"{filename} (no longer in src/migrations/)")
            continue
        desc = _description(filename)
        if desc in supabase_descs:
            stale.append(
                f"{filename} (mirror now exists at "
                f"supabase/migrations/{supabase_descs[desc]} — remove from "
                f"allowlist to lock the win)"
            )

    assert not stale, (
        "Stale ALLOWED_UNMIRRORED entries in "
        "tests/test_migration_discipline.py:\n  "
        + "\n  ".join(stale)
    )


# ──────────────────────────────────────────────────────────────────
# Migration-ledger lockstep (DB-gated)
# ──────────────────────────────────────────────────────────────────
#
# The supabase_migrations.schema_migrations ledger must stay in lockstep
# with the committed supabase/migrations/ filenames. One mismatched row
# HARD-BREAKS `supabase db push` (and the Schema Drift CI gate) for every
# future migration — the failure is global and silent until the next
# migration PR. Root cause every time: a session applies SQL directly to
# Supabase and records a schema_migrations.version that doesn't match the
# committed filename (c157ee3 2026-05-11, the form_summary_cache cluster
# 2026-05-16/17). The logic lives in src/migration_ledger.py; this test
# is the codified invariant. The every-session enforcement is the
# SessionStart detector in system_health (real DB); this gate runs in any
# local `RICHMOND_RUN_DB_TESTS=1` sweep.


@pytest.mark.skipif(
    not (_HAS_DB and _RUN_DB_TESTS),
    reason="Live-ledger check; set RICHMOND_RUN_DB_TESTS=1 with a real "
    "DATABASE_URL to opt in. CI uses a fake DB and skips; the every-session "
    "guard is system_health.collect_risk_summary.",
)
def test_ledger_matches_local_migration_files():
    """The live schema_migrations ledger contains exactly the versions of
    the committed supabase/migrations/ files — no orphan ledger rows
    (would break `supabase db push`) and no unrecorded committed files.

    On failure, the message names the exact drift and the one-command fix:
        python src/migration_ledger.py --fix
    """
    import migration_ledger  # noqa: WPS433 — src/ is on path via conftest

    import db  # local connection helper

    conn = db.get_connection()
    try:
        comparison = migration_ledger.compare(conn, _ROOT)
    finally:
        conn.close()

    assert comparison.clean, (
        "Migration-ledger drift detected (breaks `supabase db push` for ALL "
        "future migrations):\n\n"
        + comparison.describe()
        + "\n\nResolve safe cases with:  python src/migration_ledger.py --fix\n"
        "Then re-run. Orphan/unrecorded cases need the manual step printed above."
    )
