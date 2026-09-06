"""Capture the actual batch writer SQL, including an unchanged replay and amendment."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from psycopg2 import sql
from psycopg2.extras import Json
import db.finance as writer
from finance_ledger import FORMS, assertion_from_netfile, reconcile
from finance_sync import save_snapshot
from test_finance_ledger import transaction


def render(value):
    if isinstance(value,sql.Composed): return "".join(render(v) for v in value.seq)
    if isinstance(value,sql.Identifier): return ".".join('"'+v.replace('"','""')+'"' for v in value.strings)
    if isinstance(value,sql.SQL): return value.string
    return value


def parameter(value):
    if isinstance(value,Json): return json.dumps(value.adapted,default=str)
    adapted = getattr(value,"adapted",None)
    if isinstance(adapted,bytes): return "\\x"+adapted.hex()
    return value


class MemoryCursor:
    def __init__(self, conn): self.conn,self.rows = conn,[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,query,parameters=()):
        query=render(query)
        self.conn.commands.append(dict(sql=query,parameters=parameters))
        if query.startswith("SELECT content_hash,id"):
            self.rows=[(key,row["id"]) for key,row in self.conn.documents.items() if key in parameters[0]]
        elif query.startswith("SELECT max(activity_through)"):
            self.rows=[(self.conn.through,)]
        elif query.lstrip().startswith("SELECT id,record_key"):
            self.rows=[tuple(a[k] for k in ("id","record_key","content_hash","is_current","reconciliation_status","canonical_event_key","review_reason")) for a in self.conn.assertions.values()]
        elif query.startswith("UPDATE finance_assertions"):
            for a in self.conn.assertions.values():
                if a["id"] not in parameters[1]:a["is_current"]=False
        else:self.rows=[]
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0]


class MemoryConnection:
    def __init__(self): self.documents,self.assertions,self.commands,self.through={},{},[],None
    def cursor(self):return MemoryCursor(self)


def capture_values(cur,query,argslist,template=None,page_size=100,fetch=False):
    query=render(query)
    table,columns=re.search(r'INSERT INTO "?(\w+)"? \(([^)]+)\)',query).groups()
    columns=[c.strip(' "') for c in columns.split(',')]
    template=template or "("+",".join("%s" for _ in columns)+")"
    results=[]
    # Preserve the real page bound in emitted SQL, rather than hiding a giant
    # roundtrip inside the test adapter.
    for start in range(0,len(argslist),page_size):
        page=argslist[start:start+page_size]
        cur.conn.commands.append(dict(sql=query.replace("VALUES %s","VALUES "+",".join([template]*len(page)),1),
                                      parameters=[parameter(v) for row in page for v in row],batch_size=len(page)))
        for values in page:
            row=dict(zip(columns,values))
            if table=="documents":
                if row["content_hash"] not in cur.conn.documents:
                    cur.conn.documents[row["content_hash"]]=row
                    results.append((row["content_hash"],row["id"]))
            elif table=="finance_assertions":
                key=row["record_key"],row["content_hash"]
                inserted=key not in cur.conn.assertions
                if inserted:cur.conn.assertions[key]=row
                else:
                    for k in ("is_current","reconciliation_status","canonical_event_key","review_reason"):
                        cur.conn.assertions[key][k]=row[k]
                results.append((cur.conn.assertions[key]["id"],*key,inserted))
            elif table=="finance_source_coverage":
                cur.conn.through=date.fromisoformat(row["activity_through"])
    return results if fetch else None


def snapshot(amended=False):
    assertions=[]
    for index in range(503):
        # Exceeds two batches, including equal same-day distinct source gifts.
        tx=transaction(filing=str(100000+index),tx_id=f"gift-{index}",amount=30000)
        if amended and index==0:
            tx=dict(tx,filingId="200000",amount=25000)
        info=dict(filingId=tx["filingId"],agency="RICH")
        if amended and index==0:info.update(amends="100000",amendmentSequenceNumber=1)
        assertions.append(assertion_from_netfile(tx,info,"0660620:calendar-2026"))
    events=reconcile(assertions)
    coverage=[dict(source="netfile",form_type=form,scope_key="0660620:calendar-2026",status="partial",
                   checked_at="2026-09-06T20:00:00Z",activity_from="2026-01-01",activity_through="2026-09-06",
                   filing_count=503 if kind==21 else 0,assertion_count=503 if kind==21 else 0,pending_count=0,
                   limitations=["Fixture source scope only"],source_url="https://public.netfile.com/pub2/?AID=RICH",
                   extracted_at="2026-09-06T20:00:00Z",source_tier=1,confidence_score=1,snapshot_complete=True) for kind,form in FORMS.items()]
    return dict(assertions=assertions,events=events,coverage=coverage,documents={"100000":b"%PDF-fixture-evidence"})


writer.execute_values=capture_values
conn=MemoryConnection()
phases=[]
original=snapshot()
for name,data in (("first",deepcopy(original)),("replay",deepcopy(original)),("amendment",snapshot(True))):
    conn.commands=[]
    stats=save_snapshot(conn,data)
    phases.append(dict(name=name,stats=stats,commands=conn.commands))
print(json.dumps(dict(phases=phases),default=str))
