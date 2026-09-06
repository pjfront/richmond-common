"""Real Python producer against disposable PostgreSQL; never contacts production."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import paper_finance_review as paper
from test_paper_finance_review import fixture, Sources, PDF, NOW

spec = importlib.util.spec_from_file_location("packet_database_fixture", ROOT / "tests/civic_review_packets.integration.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def main() -> None:
    db = bridge.Database(sys.argv[1])
    checks = 0

    def verify(actual, expected) -> None:
        nonlocal checks
        assert actual == expected, (actual, expected)
        checks += 1

    def scalar(sql):
        return next(iter(db.call(sql)["rows"][0].values()))

    try:
        db.call("""CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
          GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
          CREATE TABLE documents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),city_fips text,
            source_type text,source_url text,source_identifier text,raw_content bytea,
            content_hash text,mime_type text,credibility_tier int,metadata jsonb DEFAULT '{}',
            UNIQUE(city_fips,content_hash));
          ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
          CREATE POLICY public_read ON documents FOR SELECT USING(true);
          CREATE POLICY service_write ON documents FOR ALL TO service_role USING(true) WITH CHECK(true);
          GRANT ALL ON documents TO anon,authenticated,service_role;
          CREATE TABLE pipeline_journal(id uuid PRIMARY KEY);
          CREATE TABLE neighborhood_councils(id uuid PRIMARY KEY);
          CREATE POLICY neighborhood_councils_public_read ON neighborhood_councils FOR SELECT USING(true);
        """, exec=True)
        for name in ["016_pending_decisions.sql", "147_restrict_operator_table_access.sql", "148_finance_assertion_ledger.sql", "149_operator_review_inbox.sql"]:
            db.call((ROOT / "src/migrations" / name).read_text(encoding="utf-8"), exec=True)
        db.call("SET ROLE service_role")
        snapshot, inventory, metadata = fixture()
        pages = {"page_count": 1, "omitted_pages": 0,
                 "prepared_pages": [{"page": 1, "amount_tokens": ["1000.00"], "date_tokens": ["09/02/2026"]}],
                 "private_transcript": [{"page": 1, "tokens": [{"text": "123 Private Street"}]}]}
        with patch.object(paper, "prepare_pages", return_value=pages):
            record = paper.acquire(snapshot, Sources(inventory, metadata, PDF + b"changed"), {}, NOW)[0]
        verify(paper.persist_record(db, record, snapshot), "created")
        verify(scalar("SELECT count(*)::int FROM documents"), 2)
        verify(scalar("SELECT count(*)::int FROM pending_decisions"), 1)
        verify(scalar("SELECT count(*)::int FROM civic_brief_candidates"), 0)
        verify(scalar("SELECT count(*)::int FROM finance_events"), 0)
        first = db.call("SELECT * FROM pending_decisions")["rows"][0]
        verify(first["action_kind"], "resolve_only")
        verify(first["review_class"], "engineering")
        verify(first["target_brief_id"], None)
        verify("Private Street" in str(first["evidence"]), False)
        original_ids = db.call("SELECT id FROM documents ORDER BY id")["rows"]
        original_decision_version = first["review_version"]
        verify(paper.persist_record(db, record, snapshot), "unchanged")
        verify(db.call("SELECT id FROM documents ORDER BY id")["rows"], original_ids)
        verify(scalar("SELECT review_version FROM pending_decisions"), original_decision_version)

        cache = paper.read_existing(db)
        db.commit()
        verify(cache["217094857"]["pdf_sha256"], record["pdf_sha256"])
        sources = Sources(inventory, metadata)
        replay = paper.acquire(snapshot, sources, cache, NOW + timedelta(days=1))[0]
        verify(replay["write_needed"], False)
        verify(any("/image/" in call for call in sources.calls), False)
        verify(paper.persist_record(db, replay, snapshot), "unchanged")

        # Same evidence stays suppressed after a recorded rejection.
        result = db.call("SELECT review_decision($1,'reject',$2,gen_random_uuid(),NULL,'test') AS result", [first["id"], first["review_version"]])["rows"][0]["result"]
        verify(result["effect"], "decision_recorded")
        verify(paper.persist_record(db, record, snapshot), "unchanged")
        verify(scalar("SELECT count(*)::int FROM pending_decisions"), 1)
        verify(scalar("SELECT count(*)::int FROM operator_decision_events"), 1)

        for role in ["anon", "authenticated"]:
            db.call(f"RESET ROLE; SET ROLE {role};", exec=True)
            verify(scalar("SELECT count(*)::int FROM documents"), 0)
            verify(scalar("SELECT count(*)::int FROM civic_brief_candidates"), 0)
            try:
                db.call("SELECT * FROM pending_decisions")
                raise AssertionError("Private queue leaked")
            except RuntimeError as error:
                assert "permission denied" in str(error)
                checks += 1
        db.call("RESET ROLE; SET ROLE service_role;", exec=True)
        verify(scalar("SELECT count(*)::int FROM documents WHERE metadata::text LIKE '%Private Street%'"), 1)

        changed = deepcopy(record)
        changed["pdf"] = PDF + b"second-change"
        changed["pdf_sha256"] = paper.sha(changed["pdf"])
        changed["last_checked_at"] = (NOW + timedelta(days=8)).isoformat()
        verify(paper.persist_record(db, changed, snapshot), "created")
        verify(scalar("SELECT count(*)::int FROM documents"), 4)
        verify(scalar("SELECT count(*)::int FROM pending_decisions"), 2)
        # Approving the replacement still cannot publish numeric content.
        pending = db.call("SELECT * FROM pending_decisions WHERE status='pending'")["rows"][0]
        result = db.call("SELECT review_decision($1,'approve',$2,gen_random_uuid(),NULL,'test') AS result", [pending["id"], pending["review_version"]])["rows"][0]["result"]
        verify(result["effect"], "decision_recorded")
        verify(scalar("SELECT count(*)::int FROM civic_brief_candidates"), 0)

        # Queue failure must roll back both newly inserted evidence rows.
        db.call("RESET ROLE; ALTER TABLE pending_decisions ADD CONSTRAINT test_reject_new CHECK(title NOT LIKE '%217094857%') NOT VALID; SET ROLE service_role;", exec=True)
        failed = deepcopy(record)
        failed["pdf"] = PDF + b"rollback-only"
        failed["pdf_sha256"] = paper.sha(failed["pdf"])
        try:
            paper.persist_record(db, failed, snapshot)
            raise AssertionError("Expected packet insert failure")
        except RuntimeError:
            checks += 1
        verify(scalar("SELECT count(*)::int FROM documents"), 4)
        verify(scalar("SELECT count(*)::int FROM pending_decisions"), 2)
        db.call("RESET ROLE; ALTER TABLE pending_decisions DROP CONSTRAINT test_reject_new;", exec=True)

        # Reusing the public document lake must not create an address side channel.
        collision = deepcopy(record)
        collision["pdf"] = PDF + b"public-collision"
        collision["pdf_sha256"] = paper.sha(collision["pdf"])
        db.call("INSERT INTO documents(city_fips,source_type,content_hash) VALUES('0660620','archive_center',$1)", [collision["pdf_sha256"]])
        db.call("SET ROLE service_role")
        try:
            paper.persist_record(db, collision, snapshot)
            raise AssertionError("Expected private boundary failure")
        except ValueError:
            checks += 1
        verify(scalar("SELECT count(*)::int FROM pending_decisions"), 2)
        verify(scalar("SELECT count(*)::int FROM documents"), 5)
        verify(scalar("SELECT count(*)::int FROM finance_assertions"), 0)
        # Improved preparation for unchanged bytes updates only an open packet,
        # preserving its source dedup key while invalidating an old browser view.
        prepared = deepcopy(record)
        prepared["pdf"] = PDF + b"preparation"
        prepared["pdf_sha256"] = paper.sha(prepared["pdf"])
        verify(paper.persist_record(db, prepared, snapshot), "created")
        before = db.call("SELECT id,review_version FROM pending_decisions WHERE status='pending'")["rows"][0]
        prepared["pages"]["prepared_pages"][0]["amount_tokens"] = ["1000.00", "2500.00"]
        verify(paper.persist_record(db, prepared, snapshot), "refreshed")
        after = db.call("SELECT id,review_version FROM pending_decisions WHERE status='pending'")["rows"][0]
        verify(after["id"], before["id"])
        verify(after["review_version"], before["review_version"] + 1)

        # Exercise actual acquisition -> SQL persistence across OCR recovery.
        # The source fingerprint stays stable, while open evidence advances its
        # review version and a rejected judgment remains closed on later repair.
        unavailable = {"prepared_pages": [{"page": 1, "method": "ocr_unavailable"}], "omitted_pages": 0}
        with patch.object(paper, "prepare_pages", return_value=unavailable):
            failed_ocr = paper.acquire(snapshot, Sources(inventory, metadata, PDF + b"ocr-recovery"), {}, NOW)[0]
        verify(paper.persist_record(db, failed_ocr, snapshot), "refreshed")
        before = db.call("SELECT id,review_version,evidence FROM pending_decisions WHERE status='pending'")["rows"][0]
        verify(before["evidence"]["proposed_change"]["unverified_page_candidates"][0]["method"], "ocr_unavailable")
        recovered = {"prepared_pages": [{"page": 1, "method": "local_tesseract", "amount_tokens": ["1000.00"]}], "omitted_pages": 0}
        with patch.object(paper, "prepare_pages", return_value=recovered):
            repaired = paper.acquire(snapshot, Sources(inventory, metadata, PDF + b"ocr-recovery"),
                {"217094857": failed_ocr}, NOW + timedelta(days=1))[0]
        verify(paper.prepare_packet(failed_ocr, None, snapshot).dedup_key, paper.prepare_packet(repaired, None, snapshot).dedup_key)
        verify(paper.persist_record(db, repaired, snapshot), "refreshed")
        after = db.call("SELECT id,review_version,evidence FROM pending_decisions WHERE status='pending'")["rows"][0]
        verify(after["id"], before["id"])
        verify(after["review_version"], before["review_version"] + 1)
        verify(after["evidence"]["proposed_change"]["unverified_page_candidates"][0]["method"], "local_tesseract")
        db.call("SELECT review_decision($1,'reject',$2,gen_random_uuid(),NULL,'test')", [after["id"], after["review_version"]])
        closed = db.call("SELECT review_version,evidence,status FROM pending_decisions WHERE id=$1", [after["id"]])["rows"][0]
        repaired["pages"]["prepared_pages"][0]["amount_tokens"].append("2500.00")
        verify(paper.persist_record(db, repaired, snapshot), "unchanged")
        verify(db.call("SELECT review_version,evidence,status FROM pending_decisions WHERE id=$1", [after["id"]])["rows"][0], closed)
        print(f"Paper source writer: {checks} PostgreSQL assertions passed; no production access")
    finally:
        db.close()


if __name__ == "__main__":
    main()
