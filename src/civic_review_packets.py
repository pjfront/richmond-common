"""Prepare bounded source-backed operator packets without generation or delivery.

Reads source-closest agenda_items titles + meetings agenda URLs, and immutable
finance_assertions. Does not read AI recaps, summaries, topic labels, aggregate
contribution totals, or donor addresses. No HTTP, model, email, or publication
calls. The default CLI is a read-only dry run; --apply writes private drafts and
decisions only, using migration149's publication contract (finance requires148).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo


PRODUCER = "civic_review_packets"
MAX_FINANCE_ROWS = 5000
MAX_AGENDA_ROWS = 1000
MAX_OPEN_STORY_PACKETS = 100
MAX_PACKET_ROWS = 8
SUBJECTS = {
    "chevron-settlement-and-city-budget": (
        "Chevron money and the city budget",
        ("chevron", "polluters pay", "settlement funds", "city budget", "operating budget", "proposed budget", "budget amendment", "mid-year budget", "midyear budget"),
    ),
    "fire-stations-and-emergency-response": (
        "The fire-station bond",
        ("fire station", "fire stations", "fire-station", "fire-stations", "fire facilities", "fire bond", "fire infrastructure"),
    ),
    "flock-cameras-and-data-privacy": (
        "Flock cameras and data privacy",
        ("flock", "license plate reader", "licence plate reader", "alpr", "automated license plate"),
    ),
}
ALLOWED_SUBJECTS = {*SUBJECTS, "2026-general"}
OFFICIAL_AGENDA_HOSTS = {
    "www.richmondca.gov", "richmondca.gov", "www.ci.richmond.ca.us", "ci.richmond.ca.us",
    "richmondca.escribemeetings.com",
}
REASONS = {
    "ambiguous_cross_report_multiplicity": "Several entries could describe the same transfer; their number differs across reports.",
    "cross_report_date_disagreement": "Possible counterpart reports give different activity dates within fourteen days.",
    "missing_amount_date_or_reporting_filer": "An amount, activity date, or reporting filer is missing from the extracted record.",
    "missing_reported_counterparty": "A reported donor or recipient is missing from the extracted record.",
    "independent_expenditure_target_or_stance_unverified": "The candidate or measure, or support/opposition checkbox, has not been verified.",
}
FINANCE_COLUMNS = """source,scope_key,record_key,content_hash,filing_id,form_type,transaction_type,
 reporting_filer_name,reporting_filer_fppc_id,donor_name,donor_fppc_id,recipient_name,recipient_fppc_id,
 amount,amount_kind,activity_date,event_kind,support_oppose,candidate_name,measure_name,election_date,
 source_url,source_tier,is_current,reconciliation_status,canonical_event_key,review_reason"""


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def dated(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def official_url(value: Any, *, finance: bool = False) -> str | None:
    if not isinstance(value, str) or re.search(r"[\s\\]", value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            return None
    except ValueError:
        return None
    if finance:
        return value if url.hostname == "netfile.com" and url.path.startswith("/Connect2/api/public/image/") else None
    return value if url.hostname in OFFICIAL_AGENDA_HOSTS else None


@dataclass(frozen=True)
class Packet:
    identity: str
    title: str
    description: str
    evidence: dict[str, Any]
    subject: str
    kind: str | None = None
    body: str | None = None
    sources: tuple[dict[str, Any], ...] = ()

    @property
    def input_fingerprint(self) -> str:
        # Source facts, not template wording, poll times or DB-generated route
        # IDs. A copy edit must not revive an unchanged rejected source packet.
        return fingerprint({"identity": self.identity,
                            "sources": [{key: source.get(key) for key in ("url", "source_tier", "source_date")} for source in self.sources],
                            "source_versions": self.evidence.get("source_versions"),
                            "source_titles": self.evidence.get("source_titles"),
                            "reason_codes": self.evidence.get("reason_codes")})

    @property
    def dedup_key(self) -> str:
        return f"civic-packet:{self.input_fingerprint}"

    @property
    def link(self) -> str:
        return "/elections/2026-general/money" if self.subject == "2026-general" else f"/stories/{self.subject}"


def reported_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """Exact disclosed values only; do not copy raw address-bearing payloads."""
    fields = ("record_key", "filing_id", "form_type", "reporting_filer_name", "reporting_filer_fppc_id",
              "donor_name", "donor_fppc_id", "recipient_name", "recipient_fppc_id", "amount",
              "amount_kind", "activity_date", "candidate_name", "measure_name", "election_date", "support_oppose")
    entry = {key: str(row[key]) if isinstance(row.get(key), (date, Decimal)) else row.get(key) for key in fields}
    entry["source"] = {"url": official_url(row.get("source_url"), finance=True),
                       "title": f"{row.get('form_type')} · filing {row.get('filing_id')}"}
    entry["source_content_hash"] = row.get("content_hash")
    return entry


def possible_counterpart(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Package a comparison, never infer an entity match or economic event."""
    if left.get("transaction_type") not in {0, 4, 20, 21} or right.get("transaction_type") not in {0, 4, 20, 21}:
        return False
    if not left.get("recipient_fppc_id") or left.get("recipient_fppc_id") != right.get("recipient_fppc_id"):
        return False
    if left.get("amount") is None or left.get("amount") != right.get("amount") or left.get("amount_kind") != right.get("amount_kind"):
        return False
    if left.get("donor_fppc_id") and right.get("donor_fppc_id"):
        same_donor = left["donor_fppc_id"] == right["donor_fppc_id"]
    else:
        same_donor = bool(normalized(left.get("donor_name"))) and normalized(left.get("donor_name")) == normalized(right.get("donor_name"))
    left_date, right_date = dated(left.get("activity_date")), dated(right.get("activity_date"))
    return bool(same_donor and left_date and right_date and abs((left_date - right_date).days) <= 14)


def prepare_finance_packets(rows: Sequence[Mapping[str, Any]], today: date) -> list[Packet]:
    current = [row for row in rows if row.get("is_current") and row.get("scope_key") == "0660620:calendar-2026"]
    pending = sorted((row for row in current if row.get("reconciliation_status") == "pending_review"), key=lambda row: str(row["record_key"]))
    if len(pending) > 100:
        raise ValueError("More than 100 pending assertions require a bounded queue triage before another packet run")
    packets, seen = [], set()
    for row in pending:
        if row["record_key"] in seen:
            continue
        counterparts = [other for other in current if other["record_key"] != row["record_key"] and possible_counterpart(row, other)]
        comparisons = sorted([row, *counterparts], key=lambda other: str(other["record_key"]))
        reasons = sorted({reason for other in comparisons for reason in str(other.get("review_reason") or "").split(";") if reason})
        # Include all members in the fingerprint even if the readable packet is capped.
        identities = sorted((other["record_key"], other["content_hash"]) for other in comparisons)
        seen.update(other["record_key"] for other in comparisons if other.get("reconciliation_status") == "pending_review")
        evidence = {
            "reason_codes": reasons,
            "reason": [REASONS.get(reason, f"Source review reason: {reason}") for reason in reasons],
            "recommendation": "Compare the linked source entries and record the supported interpretation. Approval records this judgment only; it does not merge, delete, or change any finance record.",
            "alternatives": ["Keep entries separate if they describe distinct activity.", "Request a source extraction or reconciliation correction with the exact filing IDs.", "Defer if the source does not settle the question."],
            "affected_pages": ["/elections/2026-general/money"],
            "reported_entries": [reported_entry(other) for other in comparisons[:MAX_PACKET_ROWS]],
            "comparison_limit": f"Showing {min(len(comparisons), MAX_PACKET_ROWS)} of {len(comparisons)} candidate entries; resemblance is not proof of duplication.",
            "source_versions": identities,
        }
        packets.append(Packet(
            identity="finance-review:" + fingerprint(sorted(other["record_key"] for other in comparisons)),
            title=f"Compare {len(comparisons)} finance entries: {row.get('recipient_name') or row.get('reporting_filer_name') or 'unidentified counterparty'}",
            description="An engineering review of source reconciliation. Pending assertions stay outside the public ledger until a separately tested source repair.",
            evidence=evidence, subject="2026-general",
        ))

    # Small receipt-only briefs. Do not turn loans, adjustments or uncertain
    # independent-spending attribution into a donation/election total.
    events: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in current:
        day = dated(row.get("activity_date"))
        if (row.get("reconciliation_status") in {"source_reported", "matched_exact"}
                and not row.get("review_reason") and row.get("canonical_event_key")
                and day and today - timedelta(days=14) <= day <= today
                and row.get("event_kind") == "receipt" and row.get("amount_kind") == "monetary"
                and row.get("amount") is not None and Decimal(str(row["amount"])) > 0):
            events[str(row["canonical_event_key"])].append(row)
    groups: dict[str, list[list[Mapping[str, Any]]]] = defaultdict(list)
    for bundle in events.values():
        bundle.sort(key=lambda row: ({0: 0, 20: 1, 4: 2}.get(row.get("transaction_type"), 9), str(row["record_key"])))
        representative = bundle[0]
        if representative.get("transaction_type") not in {0, 20, 4} or not representative.get("recipient_fppc_id"):
            continue
        day = dated(representative["activity_date"])
        groups[f"{representative['recipient_fppc_id']}:{day.isocalendar().year}-W{day.isocalendar().week:02}"].append(bundle)
    for key, bundles in sorted(groups.items()):
        bundles.sort(key=lambda bundle: (str(bundle[0]["activity_date"]), str(bundle[0]["canonical_event_key"])), reverse=True)
        selected = bundles[:5]
        sources = {}
        for bundle in selected:
            for row in bundle:
                url = official_url(row.get("source_url"), finance=True)
                if url and row.get("source_tier") == 1:
                    sources[url] = {"url": url, "title": f"{row['form_type']} · filing {row['filing_id']}", "source_tier": 1, "source_date": None}
        if any(not official_url(row.get("source_url"), finance=True) or row.get("source_tier") != 1 for bundle in selected for row in bundle):
            continue
        recipient = selected[0][0]["recipient_name"]
        lines = [f"- {row['activity_date']}: ${Decimal(str(row['amount'])):,.2f} from {row['donor_name']} (reported name)." for row in (bundle[0] for bundle in selected)]
        body = f"The linked records report these receipts for {recipient}:\n\n" + "\n".join(lines)
        body += "\n\nThis selection shows up to five recently dated receipts from indexed electronic filings. It is not a campaign total or proof of which election the activity concerns. Source-reported names do not establish a corporate, union, or political affiliation."
        if re.search(r"<[^>]*>", body):
            continue
        packets.append(Packet(
            identity=f"finance-brief:{key}", subject="2026-general", kind="finance_brief",
            title=f"Recent receipts reported by {recipient}", body=body,
            description="Review the exact proposed source-backed receipt note before publication.",
            sources=tuple(sources[url] for url in sorted(sources)),
            evidence={"recommendation": "Publish only if the displayed reported names, dates, amounts, and receipt classification match the linked filings.",
                      "alternatives": ["Reject if this adds little useful context.", "Defer for a source correction."],
                      "affected_pages": ["/elections/2026-general", "/elections/2026-general/money"],
                      "reported_entries": [reported_entry(row) for row in (bundle[0] for bundle in selected)],
                      "source_versions": sorted((row["record_key"], row["content_hash"]) for bundle in selected for row in bundle)},
        ))
    return packets


def prepare_story_packets(rows: Sequence[Mapping[str, Any]], today: date, *, enforce_window: bool = True) -> list[Packet]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    seen = set()
    for row in rows:
        day = dated(row.get("meeting_date"))
        url = official_url(row.get("agenda_url"))
        if not day or not url or (enforce_window and not today - timedelta(days=14) <= day <= today + timedelta(days=21)):
            continue
        if row.get("source_cancelled_at") or row.get("agenda_source_retired_at") or row.get("body_type") != "city_council":
            continue
        title = str(row.get("title") or "").strip()
        if not title or len(title) > 1500 or re.search(r"<[^>]*>", title):
            continue
        value = normalized(title).replace("–", "-").replace("—", "-")
        identity = str(row.get("source_meeting_guid") or url)
        for subject, (_, aliases) in SUBJECTS.items():
            key = (subject, identity, normalized(row.get("item_number")))
            if key in seen or not any(re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", value) for alias in aliases):
                continue
            seen.add(key)
            groups[subject, identity].append(row)
    packets = []
    for (subject, identity), items in sorted(groups.items()):
        items.sort(key=lambda row: str(row["item_number"]))
        selected = items[:MAX_PACKET_ROWS]
        day = str(selected[0]["meeting_date"])
        url = selected[0]["agenda_url"]
        body = f"The City Council agenda for {day} lists:\n\n"
        body += "\n".join(f"- Item {row['item_number']}: {row['title']}" for row in selected)
        body += "\n\nThese are agenda listings, not recorded decisions. The linked official agenda contains the proposals and meeting details."
        if len(items) > MAX_PACKET_ROWS:
            body += f" This note shows {MAX_PACKET_ROWS} of {len(items)} matching listings."
        packets.append(Packet(
            identity=f"story-agenda:{subject}:{identity}", subject=subject, kind="story_update",
            title=f"On the {day} council agenda: {SUBJECTS[subject][0]}", body=body,
            description="Review an exact source-title update. Phrase matching suggests relevance; it establishes no outcome or official position.",
            sources=({"url": url, "title": f"City Council agenda · {day}", "source_tier": 1, "source_date": day},),
            evidence={"recommendation": "Confirm that these exact agenda titles advance this story, then publish the short listing or reject routine/irrelevant material.",
                      "alternatives": ["Reject a routine or unrelated listing.", "Defer until source attachments clarify the proposal."],
                      "affected_pages": [f"/stories/{subject}"],
                      "agenda_entries": [{"item": row["item_number"], "title": row["title"], "url": f"/meetings/{row['meeting_id']}/items/{quote(str(row['item_number']).lower(), safe='')}"} for row in selected],
                      "source_titles": [(row["item_number"], row["title"]) for row in items]},
        ))
    return packets


def read_inputs(conn: Any, section: str, today: date) -> tuple[list[dict], list[dict]]:
    from psycopg2.extras import RealDictCursor
    finance, agendas = [], []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if section in {"all", "finance"}:
            cur.execute(f"SELECT {FINANCE_COLUMNS} FROM finance_assertions WHERE is_current AND scope_key=%s ORDER BY record_key LIMIT %s", ("0660620:calendar-2026", MAX_FINANCE_ROWS + 1))
            finance = [dict(row) for row in cur.fetchall()]
            if len(finance) > MAX_FINANCE_ROWS:
                raise ValueError("Finance input exceeds the bounded packet scan; no partial scan will be queued")
        if section in {"all", "stories"}:
            cur.execute("""SELECT a.meeting_id,a.item_number,a.title,a.agenda_source_retired_at,
                m.meeting_date,m.agenda_url,m.source_meeting_guid,m.source_cancelled_at,b.body_type
                FROM agenda_items a JOIN meetings m ON m.id=a.meeting_id JOIN bodies b ON b.id=m.body_id
                WHERE b.body_type='city_council' AND m.source_cancelled_at IS NULL
                  AND a.agenda_source_retired_at IS NULL AND m.meeting_date BETWEEN %s AND %s
                ORDER BY m.meeting_date DESC,m.id,a.item_number LIMIT %s""",
                        (today - timedelta(days=14), today + timedelta(days=21), MAX_AGENDA_ROWS + 1))
            agendas = [dict(row) for row in cur.fetchall()]
            if len(agendas) > MAX_AGENDA_ROWS:
                raise ValueError("Agenda input exceeds the bounded packet scan; no partial scan will be queued")
    return finance, agendas


def read_story_invalidations(conn: Any, today: date) -> list[dict[str, Any]]:
    """Recheck all open source identities, not only today's discovery window.

    Absence is usable evidence only after the entire bounded query succeeds.
    Retired/cancelled rows are deliberately fetched; qualification uses the same
    source/title rules as creation. Merely aging out is not source withdrawal.
    """
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT d.id,d.entity_id,d.review_version,d.target_brief_id,d.target_content_version,c.subject_key
            FROM pending_decisions d JOIN civic_brief_candidates c ON c.id=d.target_brief_id
            WHERE d.source=%s AND d.entity_type='civic_packet' AND d.action_kind='publish_brief'
              AND d.status IN ('pending','deferred') AND c.status='draft' AND c.kind='story_update'
              AND c.subject_key=ANY(%s) ORDER BY d.id LIMIT %s""", (PRODUCER, sorted(SUBJECTS), MAX_OPEN_STORY_PACKETS + 1))
        opened = [dict(row) for row in cur.fetchall()]
        if len(opened) > MAX_OPEN_STORY_PACKETS:
            raise ValueError("Open story proposals exceed the bounded source recheck; no partial scan will be applied")
        identities = set()
        for row in opened:
            prefix = f"story-agenda:{row['subject_key']}:"
            if not str(row["entity_id"]).startswith(prefix) or not row["entity_id"][len(prefix):]:
                raise ValueError("Open story proposal has an unrecognized source identity")
            identities.add(row["entity_id"][len(prefix):])
        if not identities:
            return []
        cur.execute("""SELECT a.meeting_id,a.item_number,a.title,a.agenda_source_retired_at,
            m.meeting_date,m.agenda_url,m.source_meeting_guid,m.source_cancelled_at,b.body_type
            FROM agenda_items a JOIN meetings m ON m.id=a.meeting_id JOIN bodies b ON b.id=m.body_id
            WHERE m.source_meeting_guid=ANY(%s)
               OR (NULLIF(m.source_meeting_guid,'') IS NULL AND m.agenda_url=ANY(%s))
            ORDER BY m.meeting_date DESC,m.id,a.item_number LIMIT %s""",
                    (sorted(identities), sorted(identities), MAX_AGENDA_ROWS + 1))
        rows = [dict(row) for row in cur.fetchall()]
        if len(rows) > MAX_AGENDA_ROWS:
            raise ValueError("Open story source recheck exceeds the bounded agenda scan; no partial scan will be applied")
    supported = {packet.identity for packet in prepare_story_packets(rows, today, enforce_window=False)}
    return [row for row in opened if row["entity_id"] not in supported]


def invalidate_story_packet(conn: Any, observed: Mapping[str, Any]) -> str:
    """Withdraw only an exact still-open publication proposal, never its public content."""
    from psycopg2.extras import Json, RealDictCursor
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (PRODUCER + observed["entity_id"],))
            cur.execute("""SELECT review_version,target_brief_id,target_content_version,evidence
                FROM pending_decisions WHERE id=%s AND source=%s AND entity_id=%s
                  AND action_kind='publish_brief' AND status IN ('pending','deferred') FOR UPDATE""",
                        (observed["id"], PRODUCER, observed["entity_id"]))
            current = cur.fetchone()
            if not current or any(current[key] != observed[key] for key in ("review_version", "target_brief_id", "target_content_version")):
                conn.commit()
                return "unchanged"
            cur.execute("SELECT status,content_version FROM civic_brief_candidates WHERE id=%s FOR UPDATE", (current["target_brief_id"],))
            candidate = cur.fetchone()
            if not candidate or candidate["status"] != "draft" or candidate["content_version"] != current["target_content_version"]:
                conn.commit()
                return "unchanged"
            evidence = {**(current["evidence"] or {}), "source_invalidation": {
                "reason": "No qualifying current agenda evidence remains for this story and source meeting.",
                "previous_draft_id": str(current["target_brief_id"]),
                "previous_content_version": current["target_content_version"],
            }, "recommendation": "Close this withdrawn proposal, or defer while the underlying source is checked. Approval of this engineering note does not publish anything."}
            cur.execute("""UPDATE pending_decisions SET action_kind='resolve_only',review_class='engineering',
                target_brief_id=NULL,target_content_version=NULL,title=%s,description=%s,evidence=%s WHERE id=%s""",
                        ("Agenda publication proposal withdrawn after source change",
                         "The complete source recheck found no eligible council agenda listings for this story. The previous private draft is preserved; it can no longer be approved for publication.",
                         Json(evidence), observed["id"]))
        conn.commit()
        return "invalidated"
    except Exception:
        conn.rollback()
        raise


def persist_packet(conn: Any, packet: Packet) -> str:
    """One advisory-locked transaction owns draft + decision creation/refresh.

    Identical input is suppressed across *all* decision statuses, including
    rejection. A changed unreviewed draft refreshes in place and invalidates an
    open browser's review_version. Published/rejected snapshots stay immutable.
    """
    if packet.subject not in ALLOWED_SUBJECTS or packet.kind not in {None, "story_update", "finance_brief"}:
        raise ValueError("Packet subject or action is outside the source-backed allowlist")
    from psycopg2.extras import Json, RealDictCursor
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (PRODUCER + packet.identity,))
            cur.execute("SELECT id,status FROM pending_decisions WHERE source=%s AND dedup_key=%s LIMIT 1", (PRODUCER, packet.dedup_key))
            previous = cur.fetchone()
            cur.execute("SELECT id,target_brief_id,action_kind,evidence FROM pending_decisions WHERE source=%s AND entity_id=%s AND status IN ('pending','deferred') ORDER BY created_at LIMIT 1 FOR UPDATE", (PRODUCER, packet.identity))
            active = cur.fetchone()
            if (previous and active and active["id"] == previous["id"]
                    and active["action_kind"] == "resolve_only" and (active.get("evidence") or {}).get("source_invalidation")):
                # A withdrawn, still-unjudged proposal's source became eligible
                # again. Refresh the exact review version with a new private
                # candidate; a closed/rejected judgment remains suppressed.
                previous = None
            if previous:
                if (active and active["id"] != previous["id"]
                        and (active.get("evidence") or {}).get("previous_decision_id") != str(previous["id"])):
                    # Source reverted to an already judged version. Do not
                    # recreate it or leave the intervening proposal publishable.
                    cur.execute("""UPDATE pending_decisions SET action_kind='resolve_only',review_class='engineering',
                        target_brief_id=NULL,target_content_version=NULL,title=%s,description=%s,evidence=%s
                        WHERE id=%s""", ("Source reverted to previously reviewed evidence", "This intervening proposal is superseded. Closing this engineering note does not publish or repair anything.",
                                         Json({"previous_decision_id": str(previous["id"]), "recommendation": "Close the superseded packet; the current source version already has a recorded judgment."}), active["id"]))
                    conn.commit()
                    return "refreshed"
                conn.commit()
                return "unchanged"
            target_id, target_version = None, None
            if packet.kind:
                if active and active["target_brief_id"]:
                    cur.execute("SELECT status FROM civic_brief_candidates WHERE id=%s FOR UPDATE", (active["target_brief_id"],))
                    if cur.fetchone()["status"] != "draft":
                        raise ValueError("An open source packet unexpectedly targets non-draft content")
                    cur.execute("""UPDATE civic_brief_candidates SET title=%s,body=%s,sources=%s,input_fingerprint=%s
                        WHERE id=%s RETURNING id,content_version""", (packet.title, packet.body, Json(packet.sources), packet.input_fingerprint, active["target_brief_id"]))
                else:
                    cur.execute("""INSERT INTO civic_brief_candidates(kind,subject_key,title,body,sources,input_fingerprint)
                        VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,content_version""", (packet.kind, packet.subject, packet.title, packet.body, Json(packet.sources), packet.input_fingerprint))
                target = cur.fetchone()
                target_id, target_version = target["id"], target["content_version"]
            values = (packet.title, packet.description, Json(packet.evidence), packet.dedup_key,
                      "publish_brief" if packet.kind else "resolve_only", "editorial" if packet.kind else "engineering",
                      target_id, target_version)
            if active:
                cur.execute("""UPDATE pending_decisions SET title=%s,description=%s,evidence=%s,dedup_key=%s,
                    action_kind=%s,review_class=%s,target_brief_id=%s,target_content_version=%s WHERE id=%s""", (*values, active["id"]))
            else:
                cur.execute("""INSERT INTO pending_decisions(title,description,evidence,dedup_key,action_kind,review_class,
                    target_brief_id,target_content_version,city_fips,decision_type,severity,source,entity_type,entity_id,link)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'0660620','data_quality','medium',%s,'civic_packet',%s,%s)""", (*values, PRODUCER, packet.identity, packet.link))
        conn.commit()
        return "refreshed" if active else "created"
    except Exception:
        conn.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write private review packets; never publish or send email")
    parser.add_argument("--section", choices=("all", "finance", "stories"), default="all")
    parser.add_argument("--max-packets", type=int, default=6, help="Maximum changed packets per run (1–12)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(ZoneInfo("America/Los_Angeles")).date())
    parser.add_argument("--report", type=Path, help="Write aggregate-only diagnostics")
    args = parser.parse_args()
    if not 1 <= args.max_packets <= 12 or args.as_of.year != 2026:
        parser.error("Use 1–12 packets and a 2026 source window")
    from db import get_connection
    conn = get_connection()
    try:
        # Discovery and withdrawal checks must see one source snapshot. A
        # cancellation between those reads must not withdraw then recreate the
        # same proposal from the first, older read in a single invocation.
        conn.set_session(readonly=not args.apply, isolation_level="REPEATABLE READ")
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout='15s'")
        finance, agendas = read_inputs(conn, args.section, args.as_of)
        invalidations = read_story_invalidations(conn, args.as_of) if args.section in {"all", "stories"} else []
        conn.commit()
        conn.set_session(isolation_level="READ COMMITTED")
        prepared = prepare_finance_packets(finance, args.as_of) + prepare_story_packets(agendas, args.as_of)
        # Round-robin subjects so a busy filer cannot starve the three stories.
        groups = defaultdict(list)
        for packet in prepared:
            groups[packet.subject].append(packet)
        ordered = []
        while any(groups.values()):
            for subject in sorted(groups):
                if groups[subject]:
                    ordered.append(groups[subject].pop(0))
        counts = {"created": 0, "refreshed": 0, "unchanged": 0, "invalidated": 0}
        if args.apply:
            # Safety withdrawals run before the discovery budget: leaving the
            # seventh unsupported proposal publishable is not an acceptable cap.
            for observed in invalidations:
                counts[invalidate_story_packet(conn, observed)] += 1
            for packet in ordered:
                disposition = persist_packet(conn, packet)
                counts[disposition] += 1
                if counts["created"] + counts["refreshed"] >= args.max_packets:
                    break
        summary = {"mode": "apply" if args.apply else "dry_run", "prepared": len(prepared),
                   "engineering": sum(packet.kind is None for packet in prepared),
                   "editorial": sum(packet.kind is not None for packet in prepared), **counts,
                   "proposed_invalidations": len(invalidations),
                   "max_changed_packets": args.max_packets, "published": 0, "emails_sent": 0}
        print(json.dumps(summary, sort_keys=True))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
