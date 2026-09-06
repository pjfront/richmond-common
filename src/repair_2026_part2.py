"""Guarded repair of twelve source-verified 2026 Form 497 Part 2 assertions.

Default: read-only preview. --apply requires the exact preview state hash and
runs one transaction. It archives original legacy rows in the immutable finance
ledger before removing their reversed projections. Only a recipient-backed
reconciled event can add a missing legacy receipt; outgoing-only reports remain
in the dedicated source ledger. No donor/committee fuzzy matching or model calls.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import uuid

from psycopg2.extras import Json, RealDictCursor

from finance_ledger import digest, normalized_name

SCOPE = "0660620:calendar-2026"
# Explicit bounded source identities, checked September 6 against the original
# public filings. A superseding amendment or a changed amount/date aborts.
EXPECTED = {
    "216841017:fa1ba819-249c-40e5-9a57-b45a01461217": ("2026-05-29", "30000", "951606", "1490887"),
    "216787856:39796471-9857-425a-87d5-b44f01268316": ("2026-05-18", "30000", "951606", "1490887"),
    "216765092:bf04046a-f719-47a3-8b98-b449012706c0": ("2026-05-12", "30000", "951606", "1490887"),
    "216760474:b2323047-c494-432c-8bc6-b448013413f9": ("2026-05-11", "5000", "951606", "1480025"),
    "216758245:5543133a-75f1-4ad9-a1cf-b448000cec93": ("2026-05-11", "2500", "811678", "1440389"),
    "216736743:e099ee49-fbad-48cd-8262-b44201429149": ("2026-05-06", "30000", "951606", "1490877"),
    "216689753:7dc49ba3-1b06-4b49-aa2b-b43601252f3e": ("2026-04-24", "2500", "951606", "1484818"),
    "216663665:8d3882a8-3bf3-4c63-a70a-b43301219631": ("2026-04-21", "2500", "891677", "1440389"),
    "216663665:1510c537-0ce1-4cec-bd0b-b43301219631": ("2026-04-21", "2500", "891677", "1485224"),
    "216635523:6cc13917-bc31-4bf6-a143-b42d01226783": ("2026-04-15", "2500", "951606", "1440389"),
    "216618902:963d8d21-4170-4ccb-8450-b4290028433b": ("2026-04-10", "2500", "891677", "1488504"),
    "216618889:100759a8-551d-4624-9975-b4290027c850": ("2026-04-10", "2500", "951606", "1481105"),
}


def validate_sources(assertions: list[dict]) -> None:
    if {a["record_key"] for a in assertions} != set(EXPECTED) or len(assertions) != 12:
        raise ValueError("Expected exactly twelve current, retained source assertions; load finance snapshot first")
    for a in assertions:
        expected = EXPECTED[a["record_key"]]
        observed = (str(a["activity_date"])[:10], str(Decimal(str(a["amount"])).normalize()),
                    a["donor_fppc_id"], a["recipient_fppc_id"])
        if (observed[0], Decimal(observed[1]), *observed[2:]) != (expected[0], Decimal(expected[1]), *expected[2:]):
            raise ValueError("Source amount, date or direction changed; bounded repair requires fresh review")
        tx = a["raw_payload"]["transaction"]
        info = a["raw_payload"]["filing_info"]
        if not a["is_current"] or info.get("amendedBy") or tx["transactionType"] != 21:
            raise ValueError("Source was superseded or is not Form 497 Part 2")
        if (a["donor_name"], a["recipient_name"]) != (tx["filerName"], tx["name"]):
            raise ValueError("Normalized names no longer agree with original source direction")
        if (f"{tx['filingId']}:{tx['id']}" != a["record_key"] or Decimal(str(tx["amount"])) != a["amount"]
                or tx["date"][:10] != observed[0] or tx["filerFppcId"] != a["donor_fppc_id"]
                or tx["transactionFppcId"] != a["recipient_fppc_id"] or info.get("agency") != "RICH"):
            raise ValueError("Original Richmond source fields do not support the planned repair")


def read_state(conn, assertions_override: list[dict] | None = None) -> dict:
    """Read only the bounded institutional counterparties and their receipts."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if assertions_override is None:
            cur.execute("SELECT * FROM finance_assertions WHERE source='netfile' AND is_current AND record_key=ANY(%s) ORDER BY record_key", (sorted(EXPECTED),))
            assertions = list(cur.fetchall())
        else:
            assertions = sorted(assertions_override, key=lambda a: a["record_key"])
        validate_sources(assertions)
        event_keys = sorted({a["canonical_event_key"] for a in assertions if a["canonical_event_key"]})
        if assertions_override is None:
            cur.execute("SELECT * FROM finance_assertions WHERE source='netfile' AND is_current AND canonical_event_key=ANY(%s) AND transaction_type IN(0,4,20) ORDER BY record_key", (event_keys,))
            recipient_reports = list(cur.fetchall())
        else:
            recipient_reports = []
        ids = sorted({a[k] for a in assertions for k in ("donor_fppc_id", "recipient_fppc_id")})
        names = sorted({a[k] for a in assertions for k in ("donor_name", "recipient_name")})
        cur.execute("SELECT id::text,name,filer_id,committee_type,status FROM committees WHERE filer_id=ANY(%s) OR name=ANY(%s) ORDER BY id", (ids, names))
        committees = list(cur.fetchall())
        cur.execute("""SELECT to_jsonb(c) before_row,d.name donor_name,d.normalized_name donor_normalized_name,
                              d.employer donor_employer,m.name recipient_name,m.filer_id recipient_fppc_id
                       FROM contributions c JOIN donors d ON d.id=c.donor_id JOIN committees m ON m.id=c.committee_id
                       WHERE c.contribution_date BETWEEN '2026-01-01' AND '2026-12-31'
                         AND (c.committee_id::text=ANY(%s) OR c.filing_id=ANY(%s)) ORDER BY c.id""",
                    ([m["id"] for m in committees], sorted({a["filing_id"] for a in assertions})))
        legacy = list(cur.fetchall())
    return dict(assertions=assertions, recipient_reports=recipient_reports, committees=committees, legacy=legacy)


def make_plan(state: dict) -> dict:
    validate_sources(state["assertions"])
    actions, identity_updates = [], {}
    before_totals = defaultdict(Decimal)
    deltas = defaultdict(Decimal)
    for row in state["legacy"]:
        before_totals[row["before_row"]["committee_id"]] += Decimal(str(row["before_row"]["amount"]))
    for a in state["assertions"]:
        matching_committees = [m for m in state["committees"] if m["filer_id"] == a["recipient_fppc_id"]]
        exact_name = [m for m in state["committees"] if m["name"] == a["recipient_name"]]
        if not matching_committees:
            matching_committees = exact_name
        if len(matching_committees) > 1:
            # Historical cycles may share a legal FPPC identifier. The source
            # must also name the exact committee; never pick the newest year.
            matching_committees = [m for m in matching_committees if normalized_name(m["name"]) == normalized_name(a["recipient_name"])]
        if len(matching_committees) > 1:
            raise ValueError("Multiple committees claim the target identifier; cannot safely repair")
        committee = matching_committees[0] if matching_committees else None
        if committee and committee["filer_id"] != a["recipient_fppc_id"]:
            if committee["filer_id"] not in (None, "", "Pending") or committee["name"] != a["recipient_name"]:
                raise ValueError("Conflicting committee identity must be reviewed")
            identity_updates[committee["id"]] = dict(committee_id=committee["id"], before=committee,
                filer_id=a["recipient_fppc_id"], assertion_id=str(a["id"]), source_url=a["source_url"], filing_id=a["filing_id"])
        reversed_rows = [r for r in state["legacy"] if
            str(r["before_row"].get("filing_id")) == a["filing_id"]
            and Decimal(str(r["before_row"]["amount"])) == a["amount"]
            and str(r["before_row"]["contribution_date"])[:10] == str(a["activity_date"])[:10]
            and normalized_name(r["donor_name"]) == normalized_name(a["recipient_name"])
            and r["recipient_fppc_id"] == a["donor_fppc_id"]]
        if len(reversed_rows) > 1:
            raise ValueError("Multiple legacy rows claim one source transaction; manual review required")
        for r in reversed_rows:
            deltas[r["before_row"]["committee_id"]] -= Decimal(str(r["before_row"]["amount"]))
        # A recipient report gives a source-specific donor spelling and ID for
        # compatibility matching, without guessing an alias from a surname.
        receipts = [p for p in state["recipient_reports"] if p["canonical_event_key"] == a["canonical_event_key"]]
        source_receipt = min(receipts, key=lambda p: ({0:0,20:1,4:2}[p["transaction_type"]], p["record_key"])) if receipts else None
        existing = []
        from canonical_donors import canonicalize_donor_name
        receipt_donor = canonicalize_donor_name(source_receipt["donor_name"]) if source_receipt else None
        if source_receipt and committee:
            target_donor = normalized_name(receipt_donor)
            existing = [r for r in state["legacy"] if r["before_row"]["committee_id"] == committee["id"]
                        and Decimal(str(r["before_row"]["amount"])) == a["amount"]
                        and normalized_name(canonicalize_donor_name(r["donor_name"])) == target_donor
                        and str(r["before_row"]["contribution_date"])[:10] == str(a["activity_date"])[:10]]
        if len(existing) > 1:
            raise ValueError("Ambiguous existing recipient receipts; no automatic collapse")
        disposition = "retain_existing_receipt" if existing else "restore_missing_receipt" if source_receipt else "ledger_only_outgoing_or_pending"
        if source_receipt and not committee:
            raise ValueError("Recipient-backed legacy repair requires an existing verified committee")
        if disposition == "restore_missing_receipt":
            deltas[committee["id"]] += a["amount"]
        actions.append(dict(record_key=a["record_key"], assertion_id=str(a["id"]), source_url=a["source_url"],
            filing_id=a["filing_id"], amount=a["amount"], activity_date=str(a["activity_date"])[:10],
            donor_fppc_id=a["donor_fppc_id"], recipient_fppc_id=a["recipient_fppc_id"],
            reverse_row_ids=[r["before_row"]["id"] for r in reversed_rows],
            existing_receipt_ids=[r["before_row"]["id"] for r in existing],
            disposition=disposition, receipt_assertion_id=str(source_receipt["id"]) if source_receipt else None,
            receipt_donor_name=receipt_donor,
            recipient_committee_id=committee["id"] if committee else None,
            reason=a["review_reason"] or ("separate_outgoing_source_is_not_an_extra_receipt" if not source_receipt else None)))
    balance_changes = []
    for m in state["committees"]:
        amount = before_totals[m["id"]]
        balance_changes.append(dict(committee_id=m["id"], name=m["name"], filer_id=identity_updates.get(m["id"], {}).get("filer_id", m["filer_id"]),
                                    before=amount, change=deltas[m["id"]], after=amount+deltas[m["id"]]))
    # Includes original IDs, raw row values and source-content hashes. Any drift
    # between preview and apply changes this value and blocks all writes.
    fingerprint = dict(assertions=[{k:a[k] for k in ("id","record_key","content_hash","canonical_event_key","reconciliation_status")} for a in state["assertions"]],
                       recipient_reports=[{k:a[k] for k in ("id","record_key","content_hash")} for a in state["recipient_reports"]],
                       committees=state["committees"], legacy=state["legacy"])
    fingerprint.update(actions=actions, committee_identity_updates=list(identity_updates.values()))
    source_evidence_hash = digest(sorted((a["record_key"],a["content_hash"]) for a in state["assertions"]))
    return dict(version=1, scope=SCOPE, source_evidence_hash=source_evidence_hash, state_hash=digest(fingerprint), actions=actions,
                committee_identity_updates=list(identity_updates.values()), committee_balance_changes=balance_changes)


def archive_before(cur, *, source_assertion: dict, record_key: str, transaction_id: str, payload: dict) -> None:
    cur.execute("""INSERT INTO finance_assertions(source,scope_key,record_key,content_hash,filing_id,transaction_id,form_type,
                   reporting_filer_name,event_kind,amount_kind,raw_payload,source_url,source_tier,confidence_score,is_current,review_reason)
                   VALUES('legacy_repair','repair:2026-part2',%s,%s,%s,%s,'legacy_before',%s,'unclassified','legacy_snapshot',
                          %s,%s,1,1,false,'Source evidence retained before bounded legacy repair')
                   ON CONFLICT(source,record_key,content_hash) DO NOTHING""",
                (record_key,digest(payload),source_assertion["filing_id"],transaction_id,source_assertion["reporting_filer_name"],
                 Json(json.loads(json.dumps(payload, default=str))),source_assertion["source_url"]))


def apply_plan(conn, state: dict, plan: dict, expected_state_hash: str) -> dict:
    if plan["state_hash"] != expected_state_hash or make_plan(state) != plan:
        raise ValueError("Preview state changed; no repair was applied")
    by_id = {str(a["id"]):a for a in state["assertions"] + state["recipient_reports"]}
    legacy_by_id = {r["before_row"]["id"]:r for r in state["legacy"]}
    stats = dict(reversed_projections_removed=0, missing_receipts_restored=0, committee_ids_verified=0)
    with conn.cursor() as cur:
        for update in plan["committee_identity_updates"]:
            a = by_id[update["assertion_id"]]
            archive_before(cur, source_assertion=a, record_key=f"committee:{update['committee_id']}:{expected_state_hash}",
                           transaction_id=update["committee_id"], payload=dict(before=update["before"], verified_fppc_id=update["filer_id"],
                           source_assertion_id=update["assertion_id"], operation_state_hash=expected_state_hash))
            cur.execute("UPDATE committees SET filer_id=%s WHERE id=%s AND filer_id IS NOT DISTINCT FROM %s",
                        (update["filer_id"], update["committee_id"], update["before"]["filer_id"]))
            if cur.rowcount != 1:
                raise ValueError("Committee changed after preview")
            stats["committee_ids_verified"] += 1
        for action in plan["actions"]:
            a = by_id[action["assertion_id"]]
            for row_id in action["reverse_row_ids"]:
                archive_before(cur, source_assertion=a, record_key=f"contribution:{row_id}:{expected_state_hash}", transaction_id=row_id,
                               payload=dict(before=legacy_by_id[row_id]["before_row"], source_assertion_id=str(a["id"]),
                                            disposition=action["disposition"], operation_state_hash=expected_state_hash))
                cur.execute("DELETE FROM contributions WHERE id=%s", (row_id,))
                if cur.rowcount != 1:
                    raise ValueError("Legacy row changed after preview")
                stats["reversed_projections_removed"] += 1
            if action["disposition"] != "restore_missing_receipt":
                continue
            receipt = by_id[action["receipt_assertion_id"]]
            from db.officials import _normalize_name
            name = action["receipt_donor_name"]
            cur.execute("SELECT id FROM donors WHERE normalized_name=%s AND COALESCE(employer,'')='' ORDER BY id", (_normalize_name(name),))
            donors = cur.fetchall()
            if len(donors) > 1:
                raise ValueError("Ambiguous legacy donor identity; no repair applied")
            if donors:
                donor_id = donors[0][0]
            else:
                donor_id = str(uuid.uuid4())
                cur.execute("INSERT INTO donors(id,city_fips,name,normalized_name) VALUES(%s,'0660620',%s,%s)",
                            (donor_id,name,_normalize_name(name)))
            cur.execute("""INSERT INTO contributions(id,city_fips,donor_id,committee_id,amount,contribution_date,
                           contribution_type,filing_id,schedule,source,document_id)
                           VALUES(%s,'0660620',%s,%s,%s,%s,'monetary',%s,%s,'city_clerk',%s)""",
                        (str(uuid.uuid4()),donor_id,action["recipient_committee_id"],receipt["amount"],receipt["activity_date"],
                         receipt["filing_id"],receipt["form_type"],receipt.get("document_id")))
            stats["missing_receipts_restored"] += 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-state-hash")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.apply and (not args.expected_state_hash or len(args.expected_state_hash) != 64):
        parser.error("--apply requires --expected-state-hash from the exact read-only preview")
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    from db import get_connection
    conn = get_connection()
    conn.set_session(readonly=not args.apply, isolation_level="SERIALIZABLE")
    try:
        with conn:
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance:netfile'))")
                    cur.execute("LOCK TABLE contributions,donors,committees IN SHARE ROW EXCLUSIVE MODE")
            state = read_state(conn)
            plan = make_plan(state)
            if args.apply:
                plan["applied"] = apply_plan(conn, state, plan, args.expected_state_hash)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(plan, default=str, indent=2), encoding="utf-8")
        print(json.dumps({"state_hash":plan["state_hash"], "mode":"applied" if args.apply else "read_only",
                          "source_evidence_hash":plan["source_evidence_hash"],
                          "reversed_projections":sum(len(a["reverse_row_ids"]) for a in plan["actions"]),
                          "missing_receipts":sum(a["disposition"] == "restore_missing_receipt" for a in plan["actions"]),
                          "committee_identity_updates":len(plan["committee_identity_updates"]),
                          "applied":plan.get("applied")}, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
