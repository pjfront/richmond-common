"""Monthly DB maintenance (P1.1a rider, from OD-14 / AI-PL D69).

Reads from and writes to the live DB directly (autocommit — VACUUM cannot
run inside a transaction). Two jobs:

1. Prune superseded conflict-flag history. supersede_flags_for_meeting()
   demotes flags to is_current = FALSE on every rescan; the history regrows
   ~20 MB/month at current cadence. Migration 121 (OD-14) deleted the
   backlog; this keeps it deleted. Same guarded predicate: never touches
   is_current = TRUE rows, never deletes a row another flag's superseded_by
   points at, refuses to run if the current-flag floor looks wrong.

2. VACUUM FULL the pruned table so the space actually returns to the OS —
   plain VACUUM only frees pages for reuse, and Supabase free-tier size
   pressure (909 MB vs 500 MB, plan free-tier addendum) is measured by
   pg_database_size.

Invoked by .github/workflows/alerting.yml on the monthly run; safe to run
manually any time (idempotent; a no-op prune is a no-op VACUUM candidate).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection  # noqa: E402

CURRENT_FLAG_FLOOR = 10_000  # ~18K current flags expected; refuse below this


def main() -> int:
    conn = get_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        size_before = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM conflict_flags WHERE is_current = TRUE")
        current_count = cur.fetchone()[0]
        if current_count < CURRENT_FLAG_FLOOR:
            print(f"REFUSING prune: only {current_count} current flags "
                  f"(< {CURRENT_FLAG_FLOOR}) — scanner state looks wrong; "
                  "investigate before deleting history.")
            return 1

        cur.execute(
            """DELETE FROM conflict_flags
               WHERE is_current = FALSE
                 AND id NOT IN (
                   SELECT superseded_by FROM conflict_flags
                   WHERE superseded_by IS NOT NULL
                 )"""
        )
        pruned = cur.rowcount
        print(f"Pruned {pruned} superseded conflict_flags rows "
              f"({current_count} current rows untouched)")

        if pruned > 0:
            print("VACUUM FULL conflict_flags...")
            cur.execute("VACUUM FULL conflict_flags")

        cur.execute("SELECT pg_database_size(current_database())")
        size_after = cur.fetchone()[0]

    conn.close()
    print(f"Database size: {size_before / 1e6:.0f} MB -> {size_after / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
