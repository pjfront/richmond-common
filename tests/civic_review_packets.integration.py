"""Execute the real Python packet writer against disposable PostgreSQL WASM.

python tests/civic_review_packets.integration.py /path/to/@electric-sql/pglite/dist/index.js
No external database or credentials are used. Requires Node and PGlite0.5.8.
"""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import civic_review_packets as packets


BRIDGE = r"""
import {PGlite} from 'MODULE';
import {createInterface} from 'node:readline';
const db = new PGlite();
for await (const line of createInterface({input:process.stdin})) {
  try {
    const request=JSON.parse(line);
    const result=request.exec ? await db.exec(request.sql) : await db.query(request.sql,request.params??[]);
    process.stdout.write(JSON.stringify({ok:true,result})+'\n');
  } catch(error) { process.stdout.write(JSON.stringify({ok:false,error:String(error)})+'\n'); }
}
await db.close();
"""


class Database:
    def __init__(self, module):
        self.process = subprocess.Popen(["node", "--input-type=module", "-e", BRIDGE.replace("'MODULE'", json.dumps(Path(module).resolve().as_uri()))],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.active = False

    def call(self, sql, params=(), *, exec=False):
        params = [getattr(value, "adapted", value) for value in params]
        self.process.stdin.write(json.dumps({"sql": sql, "params": params, "exec": exec}, default=str) + "\n")
        self.process.stdin.flush()
        result = json.loads(self.process.stdout.readline())
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return result["result"]

    def cursor(self, **kwargs):
        return Cursor(self)

    def commit(self):
        self.call("COMMIT")
        self.active = False

    def rollback(self):
        self.call("ROLLBACK")
        self.active = False

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=20)


class Cursor:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        if not self.db.active:
            self.db.call("BEGIN")
            self.db.active = True
        for number in range(1, len(params) + 1):
            sql = sql.replace("%s", f"${number}", 1)
        self.rows = self.db.call(sql, params)["rows"]

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return self.rows


def main():
    db = Database(sys.argv[1])
    root = Path(__file__).resolve().parents[1]
    try:
        db.call("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;", exec=True)
        db.call((root / "src/migrations/016_pending_decisions.sql").read_text(encoding="utf-8"), exec=True)
        db.call("CREATE TABLE pipeline_journal(id uuid PRIMARY KEY); CREATE TABLE neighborhood_councils(id uuid PRIMARY KEY); CREATE POLICY neighborhood_councils_public_read ON neighborhood_councils FOR SELECT USING(true);", exec=True)
        for migration in ["147_restrict_operator_table_access.sql", "149_operator_review_inbox.sql"]:
            db.call((root / "src/migrations" / migration).read_text(encoding="utf-8"), exec=True)
        db.call("SET ROLE service_role")
        source = dict(meeting_id="11111111-1111-4111-8111-111111111111", source_meeting_guid="guid1", meeting_date="2026-09-15",
                      agenda_url="https://richmondca.escribemeetings.com/Meeting.aspx?Id=guid1", body_type="city_council",
                      item_number="H-1", title="Flock Safety contract update")
        first = packets.prepare_story_packets([source], date(2026, 9, 6))[0]
        assert packets.persist_packet(db, first) == "created"
        assert packets.persist_packet(db, first) == "unchanged"
        decision = db.call("SELECT * FROM pending_decisions")["rows"][0]
        assert decision["target_content_version"] == 1 and decision["review_version"] == 1
        db.call("RESET ROLE; SET ROLE anon;", exec=True)
        assert db.call("SELECT * FROM civic_brief_candidates")["rows"] == []
        db.call("RESET ROLE; SET ROLE service_role;", exec=True)
        changed = packets.prepare_story_packets([{**source, "title": "Flock Safety contract extension"}], date(2026, 9, 6))[0]
        assert packets.persist_packet(db, changed) == "refreshed"
        decision = db.call("SELECT * FROM pending_decisions")["rows"][0]
        assert decision["review_version"] == 2 and decision["target_content_version"] == 2
        def review(action, version):
            return db.call("SELECT review_decision($1,$2,$3,gen_random_uuid(),NULL,'operator') AS result", [decision["id"], action, version])["rows"][0]["result"]
        assert review("approve", 1)["code"] == "stale_decision"
        assert review("approve", 2)["effect"] == "brief_published"
        assert packets.persist_packet(db, changed) == "unchanged"
        later = packets.prepare_story_packets([{**source, "title": "Flock Safety contract data restrictions"}], date(2026, 9, 6))[0]
        assert packets.persist_packet(db, later) == "created"
        decision = db.call("SELECT * FROM pending_decisions WHERE status='pending'")["rows"][0]
        assert review("reject", 1)["effect"] == "brief_rejected"
        assert packets.persist_packet(db, later) == "unchanged"
        assert db.call("SELECT count(*)::int AS n FROM civic_brief_candidates")["rows"][0]["n"] == 2
        # Actual database insertion failure proves the writer rolls both rows back.
        db.call("RESET ROLE; CREATE FUNCTION reject_packet() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture failure'; END $$; CREATE TRIGGER reject_packet BEFORE INSERT ON pending_decisions FOR EACH ROW EXECUTE FUNCTION reject_packet(); SET ROLE service_role;", exec=True)
        fresh = packets.prepare_story_packets([{**source, "source_meeting_guid": "guid2", "agenda_url": "https://richmondca.escribemeetings.com/Meeting.aspx?Id=guid2"}], date(2026, 9, 6))[0]
        try:
            packets.persist_packet(db, fresh)
            raise AssertionError("Expected database failure")
        except RuntimeError as error:
            assert "fixture failure" in str(error)
        assert db.call("SELECT count(*)::int AS n FROM civic_brief_candidates")["rows"][0]["n"] == 2
        assert db.call("SELECT count(*)::int AS n FROM pending_decisions")["rows"][0]["n"] == 2
        print("Packet writer PostgreSQL integration passed: role grants, private draft, refresh versions, stale approval, publication, rejection suppression, atomic rollback.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
