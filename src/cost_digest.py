"""
LLM cost digest — the observability half of the PR #26 rails.

Reads entry_type='api_cost' rows from pipeline_journal (written by the
centralized gate in llm_budget_lock.py for synchronous calls, and by
batch collectors via log_batch_cost/log_batch_results_cost) and summarizes
spend by day, by call site, and by model. Makes ongoing spend visible
without a paid dashboard or a new scheduled workflow — it runs on demand and
a compact version is surfaced in the SessionStart health brief.

Reads from: pipeline_journal (entry_type='api_cost'), the source-closest
persisted record of per-call spend. Does NOT read the provider billing CSV
(lagged, batched, no per-call-site attribution — the blind spot that let the
PR #26 leak run for days undetected).

Usage:
  python cost_digest.py                 # last 30 days, text
  python cost_digest.py --days 7
  python cost_digest.py --json
  python cost_digest.py --since 2026-05-01
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

RICHMOND_FIPS = "0660620"


def _coerce_date(value: Any) -> str:
    """Normalize a created_at value (datetime/date/str) to 'YYYY-MM-DD'."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value)
    # Take the leading date portion of an ISO timestamp.
    return s[:10]


def compute_digest(
    rows: list[dict[str, Any]],
    *,
    cap_usd: float,
    days: int,
    mtd_total: float | None = None,
) -> dict[str, Any]:
    """Aggregate raw api_cost rows into a structured digest.

    Pure function (no DB) so it is unit-testable with synthetic rows. Each
    row is a dict with keys: target_artifact, created_at, approx_cost,
    model, batch (optional bool).

    Returns a dict with: total, by_caller (sorted desc), by_day (sorted
    asc), by_model (sorted desc), batch_total, sync_total, call_count,
    cap_usd, mtd_total, days.
    """
    total = 0.0
    batch_total = 0.0
    by_caller_cost: dict[str, float] = defaultdict(float)
    by_caller_calls: dict[str, int] = defaultdict(int)
    by_day: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)

    for r in rows:
        cost = float(r.get("approx_cost") or 0.0)
        total += cost
        caller = r.get("target_artifact") or "unknown"
        by_caller_cost[caller] += cost
        by_caller_calls[caller] += 1
        by_day[_coerce_date(r.get("created_at"))] += cost
        by_model[r.get("model") or "unknown"] += cost
        if r.get("batch"):
            batch_total += cost

    by_caller = [
        {"caller": k, "cost": round(v, 4), "calls": by_caller_calls[k]}
        for k, v in sorted(by_caller_cost.items(), key=lambda kv: kv[1], reverse=True)
    ]
    by_day_sorted = [
        {"day": k, "cost": round(v, 4)} for k, v in sorted(by_day.items())
    ]
    by_model_sorted = [
        {"model": k, "cost": round(v, 4)}
        for k, v in sorted(by_model.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "days": days,
        "call_count": len(rows),
        "total": round(total, 4),
        "batch_total": round(batch_total, 4),
        "sync_total": round(total - batch_total, 4),
        "by_caller": by_caller,
        "by_day": by_day_sorted,
        "by_model": by_model_sorted,
        "cap_usd": round(cap_usd, 2),
        "mtd_total": round(mtd_total, 4) if mtd_total is not None else None,
    }


def _fetch_cost_rows(conn, since: date) -> list[dict[str, Any]]:
    """Fetch api_cost rows since a cutoff date. Bounded by the date window
    (pipeline_journal grows indefinitely — never scan it unbounded)."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT target_artifact,
                      created_at,
                      (metrics->>'approx_cost')::numeric AS approx_cost,
                      metrics->>'model' AS model,
                      COALESCE((metrics->>'batch')::boolean, false) AS batch
               FROM pipeline_journal
               WHERE entry_type = 'api_cost'
                 AND created_at >= %s
               ORDER BY created_at""",
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]


def _query_mtd_total(conn) -> float | None:
    """Current calendar-month spend (matches the cap-enforcement query in
    llm_budget_lock so the digest and the cap agree)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(SUM((metrics->>'approx_cost')::numeric), 0)
                   FROM pipeline_journal
                   WHERE entry_type = 'api_cost'
                     AND date_trunc('month', created_at) = date_trunc('month', NOW())"""
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return None


def gather_digest(conn, *, days: int = 30, since: date | None = None) -> dict[str, Any]:
    """Fetch and aggregate the cost digest from the live journal."""
    from llm_budget_lock import _monthly_cap_usd

    if since is None:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    rows = _fetch_cost_rows(conn, since)
    mtd_total = _query_mtd_total(conn)
    return compute_digest(
        rows, cap_usd=_monthly_cap_usd(), days=days, mtd_total=mtd_total
    )


def format_digest(digest: dict[str, Any], *, top_n: int = 12) -> str:
    """Render the digest as a scannable text report."""
    lines: list[str] = []
    lines.append("=" * 56)
    lines.append("  LLM COST DIGEST")
    lines.append("=" * 56)
    lines.append("")
    lines.append(
        f"  Window: last {digest['days']} days  "
        f"({digest['call_count']} calls, ${digest['total']:.2f} total)"
    )
    if digest.get("batch_total"):
        lines.append(
            f"  Split:  ${digest['sync_total']:.2f} sync + "
            f"${digest['batch_total']:.2f} batch"
        )

    mtd = digest.get("mtd_total")
    cap = digest.get("cap_usd")
    if mtd is not None and cap:
        pct = (mtd / cap * 100) if cap else 0.0
        flag = "  ⚠ OVER CAP" if mtd >= cap else ""
        lines.append(f"  Month-to-date: ${mtd:.2f} / ${cap:.2f} cap ({pct:.0f}%){flag}")
    lines.append("")

    lines.append("  By call site:")
    if digest["by_caller"]:
        for row in digest["by_caller"][:top_n]:
            lines.append(
                f"    {row['caller']:<32s} ${row['cost']:>8.2f}  ({row['calls']} calls)"
            )
        if len(digest["by_caller"]) > top_n:
            lines.append(f"    ... and {len(digest['by_caller']) - top_n} more")
    else:
        lines.append("    (no spend in window)")
    lines.append("")

    lines.append("  By model:")
    for row in digest["by_model"]:
        lines.append(f"    {row['model']:<32s} ${row['cost']:>8.2f}")
    lines.append("")

    # Recent daily trend (last 14 entries to keep it scannable)
    if digest["by_day"]:
        lines.append("  Daily (most recent 14):")
        for row in digest["by_day"][-14:]:
            bar = "█" * min(40, int(row["cost"] / max(0.05, digest["total"] / 40)))
            lines.append(f"    {row['day']}  ${row['cost']:>7.2f}  {bar}")
    lines.append("")
    return "\n".join(lines)


def compact_mtd_summary(conn=None, *, top_n: int = 3) -> dict[str, Any] | None:
    """Small MTD summary for the SessionStart brief: total vs cap + top
    spenders this calendar month. Opens its own DB connection if one isn't
    passed. Returns None on any DB error so the brief degrades silently
    rather than printing noise."""
    own_conn = False
    try:
        from llm_budget_lock import _monthly_cap_usd

        if conn is None:
            from db import get_connection
            conn = get_connection()
            own_conn = True

        since = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).date()
        rows = _fetch_cost_rows(conn, since)
        digest = compute_digest(
            rows, cap_usd=_monthly_cap_usd(), days=0,
            mtd_total=sum(float(r.get("approx_cost") or 0.0) for r in rows),
        )
        return {
            "mtd_total": digest["mtd_total"],
            "cap_usd": digest["cap_usd"],
            "top": digest["by_caller"][:top_n],
        }
    except Exception:
        return None
    finally:
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM cost digest")
    parser.add_argument("--days", type=int, default=30, help="Lookback window (default 30)")
    parser.add_argument("--since", help="Explicit start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    from db import get_connection

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()

    conn = get_connection()
    try:
        digest = gather_digest(conn, days=args.days, since=since)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(digest, indent=2, default=str))
    else:
        print(format_digest(digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
