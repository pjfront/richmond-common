"""Migration ledger reconciliation — keep the Supabase ledger in lockstep
with the committed supabase/migrations/ filenames.

Reads from:  supabase/migrations/*.sql filenames + the live
             supabase_migrations.schema_migrations table (the "ledger").
Writes to:   supabase_migrations.schema_migrations — ONLY under --fix /
             reconcile(apply=True). compare() is pure read.
Verified by: tests/test_migration_discipline.py::test_ledger_matches_local
             (DB-gated) and the every-session SessionStart detector in
             system_health.collect_risk_summary.
Failure mode it prevents: ledger drift silently breaks `supabase db push`
             (and the Schema Drift CI gate) for ALL future migrations.

Why this module exists
----------------------
`supabase db push` and `supabase db push --dry-run` both HARD-REFUSE when
the ledger references a `version` with no matching local file
("Remote migration versions not found in local migrations directory").
So one mismatched ledger row blocks every future migration deploy.

This failure has recurred at least three times with the same root cause:
a session applies migration SQL directly to Supabase (because `db push`
was already broken by prior drift, or for speed) and records a
`schema_migrations.version` that does NOT match the committed
`supabase/migrations/<version>_<name>.sql` filename. Examples:
  - c157ee3 (2026-05-11): three migrations applied with no committed file.
  - form_summary_cache cluster (2026-05-16/17): three migrations recorded
    with apply-time timestamps that didn't match the committed filenames,
    plus two applied-but-unlogged. Surfaced 2026-05-30 when the first
    migration PR in two weeks tripped the Schema Drift gate.

Prompting did not hold — the convention was already written in
.claude/rules/conventions.md and drifted anyway. Per CLAUDE.md Tenet 2
("every architectural rule worth keeping needs tooling enforcement"),
this module is that enforcement: detection runs EVERY SessionStart, and a
guided `--fix` makes the safe reconciliation one command instead of the
hand-written psycopg2 surgery that introduced the drift in the first place.

The ledger contract
-------------------
For every committed `supabase/migrations/<TS>_<desc>.sql`, the live ledger
must contain a row with `version = <TS>`. Two drift directions:

  1. in_ledger_not_local — ledger version with no committed file. BREAKS
     `db push`. If a committed file shares the same `<desc>` (a pure
     timestamp-prefix mismatch), the fix is a safe version remap. If no
     `<desc>` matches, the SQL was applied directly and never committed
     (the c157ee3 shape) — needs human recovery, not auto-fix.

  2. in_local_not_ledger — committed file the ledger has never seen. Either
     genuinely pending (run `supabase db push`) or applied-but-unlogged.
     NOT auto-fixed: recording an unapplied migration as applied would make
     `db push` skip a real schema change. Reported for human decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent
_SUPABASE_MIGRATIONS = "supabase/migrations"
_LEDGER = "supabase_migrations.schema_migrations"


def _parse_filename(name: str) -> tuple[str, str] | None:
    """`<version>_<description>.sql` -> (version, description), else None."""
    if not name.endswith(".sql"):
        return None
    stem = name[: -len(".sql")]
    if "_" not in stem:
        return None
    version, description = stem.split("_", 1)
    if not version:
        return None
    return version, description


def local_migration_versions(project_root: Path | None = None) -> dict[str, str]:
    """Map of {version_prefix -> description} for supabase/migrations/*.sql.

    The supabase/ mirror (not src/migrations/) is the source of truth here:
    its timestamp filenames are exactly what `supabase db push` matches
    against the ledger.
    """
    root = project_root or _DEFAULT_ROOT
    mig_dir = root / _SUPABASE_MIGRATIONS
    out: dict[str, str] = {}
    if not mig_dir.exists():
        return out
    for p in sorted(mig_dir.glob("*.sql")):
        parsed = _parse_filename(p.name)
        if parsed:
            version, description = parsed
            out[version] = description
    return out


def ledger_versions(conn) -> dict[str, str]:
    """Map of {version -> name} from the live schema_migrations ledger."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT version, COALESCE(name, '') FROM {_LEDGER}")
        return {row[0]: row[1] for row in cur.fetchall()}


@dataclass
class LedgerComparison:
    """Result of comparing committed migration files to the live ledger."""

    # ledger versions absent from local files, but whose `name` matches a
    # local file's description whose version is ALSO absent from the ledger
    # — a pure timestamp-prefix mismatch. Safe to auto-remap.
    # Each entry: (ledger_version, local_version, description)
    remappable: list[tuple[str, str, str]] = field(default_factory=list)

    # ledger versions absent from local files with NO matching local
    # description — SQL applied directly and never committed (c157ee3
    # shape). Needs human SQL recovery. Each entry: (version, name)
    orphan_ledger: list[tuple[str, str]] = field(default_factory=list)

    # local files the ledger has never seen and which are NOT one half of
    # a remappable pair. Either pending or applied-but-unlogged. Reported,
    # never auto-fixed. Each entry: (version, description)
    unrecorded_local: list[tuple[str, str]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.remappable or self.orphan_ledger or self.unrecorded_local)

    @property
    def drift_count(self) -> int:
        return len(self.remappable) + len(self.orphan_ledger) + len(self.unrecorded_local)

    def describe(self) -> str:
        if self.clean:
            return "Migration ledger is in sync with supabase/migrations/."
        lines: list[str] = []
        if self.remappable:
            lines.append(
                f"{len(self.remappable)} timestamp-mismatch(es) "
                "(ledger version != committed filename; safe to --fix):"
            )
            for ledger_v, local_v, desc in self.remappable:
                lines.append(f"    {ledger_v} -> {local_v}  {desc}")
        if self.orphan_ledger:
            lines.append(
                f"{len(self.orphan_ledger)} orphan ledger row(s) "
                "(applied directly, no committed file — needs SQL recovery, "
                "NOT auto-fixable):"
            )
            for version, name in self.orphan_ledger:
                lines.append(f"    {version}  {name}")
        if self.unrecorded_local:
            lines.append(
                f"{len(self.unrecorded_local)} committed file(s) not in ledger "
                "(pending OR applied-but-unlogged — run `supabase db push`, or "
                "if already applied, record the version; NOT auto-fixed):"
            )
            for version, desc in self.unrecorded_local:
                lines.append(f"    {version}  {desc}")
        return "\n".join(lines)


def compare(conn, project_root: Path | None = None) -> LedgerComparison:
    """Pure read. Compare committed migration files to the live ledger."""
    local = local_migration_versions(project_root)        # version -> desc
    ledger = ledger_versions(conn)                          # version -> name

    local_versions = set(local)
    ledger_v = set(ledger)

    in_ledger_not_local = ledger_v - local_versions
    in_local_not_ledger = local_versions - ledger_v

    # Index unrecorded-local files by description so we can pair a ledger
    # orphan with a same-description local orphan (pure timestamp mismatch).
    local_desc_to_version: dict[str, str] = {
        local[v]: v for v in in_local_not_ledger
    }

    result = LedgerComparison()
    paired_local_versions: set[str] = set()

    for lv in sorted(in_ledger_not_local):
        name = ledger[lv]
        match_local_version = local_desc_to_version.get(name)
        if match_local_version is not None:
            result.remappable.append((lv, match_local_version, name))
            paired_local_versions.add(match_local_version)
        else:
            result.orphan_ledger.append((lv, name))

    for lv in sorted(in_local_not_ledger):
        if lv in paired_local_versions:
            continue  # already accounted for as the target of a remap
        result.unrecorded_local.append((lv, local[lv]))

    return result


def reconcile(conn, comparison: LedgerComparison, apply: bool = False) -> list[str]:
    """Fix the SAFE drift cases (timestamp remaps). Returns action log.

    Only `remappable` entries are touched — a pure UPDATE of the ledger
    `version` prefix to match the committed filename. The migration body,
    `statements`, `rollback`, etc. are preserved (only the key changes).
    `orphan_ledger` and `unrecorded_local` are intentionally NOT auto-fixed
    (see module docstring) and are returned as advisories.
    """
    actions: list[str] = []
    with conn.cursor() as cur:
        for ledger_v, local_v, desc in comparison.remappable:
            # Guard against colliding with an existing target row.
            cur.execute(
                f"SELECT 1 FROM {_LEDGER} WHERE version = %s", (local_v,)
            )
            if cur.fetchone() is not None:
                actions.append(
                    f"SKIP remap {ledger_v} -> {local_v} ({desc}): "
                    f"target version already present"
                )
                continue
            if apply:
                cur.execute(
                    f"UPDATE {_LEDGER} SET version = %s WHERE version = %s",
                    (local_v, ledger_v),
                )
                actions.append(
                    f"REMAPPED {ledger_v} -> {local_v} ({desc}) "
                    f"[rowcount={cur.rowcount}]"
                )
            else:
                actions.append(f"WOULD remap {ledger_v} -> {local_v} ({desc})")
        if apply:
            conn.commit()

    for version, name in comparison.orphan_ledger:
        actions.append(
            f"MANUAL: ledger row {version} ({name}) has no committed file — "
            f"recover the SQL into supabase/migrations/{version}_{name}.sql "
            f"(c157ee3 shape) or, if truly obsolete, delete the ledger row."
        )
    for version, desc in comparison.unrecorded_local:
        actions.append(
            f"MANUAL: {version}_{desc}.sql not in ledger — run "
            f"`supabase db push` to apply it, OR if it is already applied, "
            f"record it: INSERT INTO {_LEDGER} (version, name) "
            f"VALUES ('{version}', '{desc}')."
        )
    return actions


def summarize(project_root: Path | None = None) -> dict | None:
    """Lightweight summary for the SessionStart brief. Returns None on any
    DB/connection failure so the health report degrades gracefully."""
    try:
        sys.path.insert(0, str((project_root or _DEFAULT_ROOT) / "src"))
        from db import get_connection  # lazy: avoid hard dep at import time

        conn = get_connection()
        try:
            cmp = compare(conn, project_root)
        finally:
            conn.close()
        return {
            "clean": cmp.clean,
            "drift_count": cmp.drift_count,
            "remappable": len(cmp.remappable),
            "orphan_ledger": len(cmp.orphan_ledger),
            "unrecorded_local": len(cmp.unrecorded_local),
            "detail": cmp.describe() if not cmp.clean else "",
        }
    except Exception:
        return None


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Check (and optionally fix) Supabase migration-ledger drift."
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Apply the safe timestamp remaps (advisories still printed).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args()

    sys.path.insert(0, str(_DEFAULT_ROOT / "src"))
    from db import get_connection

    conn = get_connection()
    try:
        cmp = compare(conn, _DEFAULT_ROOT)
        if args.json:
            print(json.dumps({
                "clean": cmp.clean,
                "drift_count": cmp.drift_count,
                "remappable": cmp.remappable,
                "orphan_ledger": cmp.orphan_ledger,
                "unrecorded_local": cmp.unrecorded_local,
            }, indent=2))
        else:
            print(cmp.describe())
        if args.fix and not cmp.clean:
            print("\n--- reconcile ---")
            for line in reconcile(conn, cmp, apply=True):
                print(f"  {line}")
    finally:
        conn.close()

    # Non-zero exit when drift remains that --fix can't safely resolve, so
    # this is usable as a gate. After --fix, remappable drift is gone;
    # orphan/unrecorded still require a human.
    if cmp.clean:
        return 0
    if args.fix and not (cmp.orphan_ledger or cmp.unrecorded_local):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
