"""Emit the repair's actual parameterized SQL for isolated PostgreSQL replay."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from psycopg2.extras import Json
from test_finance_legacy_repair import fixture_state
from repair_2026_part2 import make_plan, apply_plan

state = fixture_state()
plan = make_plan(state)
statements = []


class CaptureCursor:
    rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, parameters=()):
        values = [json.dumps(v.adapted, default=str) if isinstance(v, Json) else v for v in parameters]
        statements.append(dict(sql=query, parameters=values))

    def fetchall(self):
        return [("restore-donor",)]


class CaptureConnection:
    def cursor(self):
        return CaptureCursor()


stats = apply_plan(CaptureConnection(), state, plan, plan["state_hash"])
print(json.dumps(dict(state=state, plan=plan, statements=statements, stats=stats), default=str))
