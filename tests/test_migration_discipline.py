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
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

_MIGRATIONS_DIR = Path(__file__).parent.parent / "src" / "migrations"


def _migration_files() -> list[Path]:
    return sorted(p for p in _MIGRATIONS_DIR.glob("*.sql"))


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
