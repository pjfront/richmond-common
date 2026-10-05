"""Record aggregate successful/failed source checks on a dedicated state branch.

No row payload, private errors, credentials or credential-bearing URLs enter
the audit. Remote writes run only inside the explicitly ready main workflow.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BRANCH = "automation/basic-refresh-state"
FILE = "refresh-status.json"
COUNT_KEYS = frozenset({"meetings_observed", "meetings_written", "items_written", "items_retired", "tags_written", "minutes_preserved", "unmapped_bodies", "awaiting_agenda", "events", "coverage_rows"})


def aggregate_state(previous: dict, reports: dict, now: str) -> dict:
    state = {"schemaVersion": 1, "updated_at": now, "sources": {}}
    for name in ("agenda", "finance"):
        report = reports.get(name)
        report = report if isinstance(report, dict) else {}
        prior = previous.get("sources", {}).get(name, {})
        success = report.get("status") == "completed" and report.get("modelCalls") == 0
        row = {"last_attempt": now, "last_success": now if success else prior.get("last_success"),
               "outcome": "checked" if success else "check_failed",
               "scope": "past-60/next-14-day window" if name == "agenda" else "0660620:calendar-2026:2026-01-01..2026-11-03",
               "pending_new_votes": name == "agenda", "pending_paper_coverage": name == "finance",
               "counts": {}}
        if success:
            for result in report.get("results", []):
                if not isinstance(result, dict):
                    continue
                for key, value in result.items():
                    if key in COUNT_KEYS and type(value) is int and value >= 0:
                        row["counts"][key] = row["counts"].get(key, 0) + value
        else:
            row["counts"] = {key: value for key, value in prior.get("counts", {}).items()
                             if key in COUNT_KEYS and type(value) is int and value >= 0}
        state["sources"][name] = row
    return state


def api(path: str, *, method: str = "GET", body: dict | None = None):
    args = ["gh", "api", path, "--method", method]
    payload = None
    if body is not None:
        args.extend(["--input", "-"])
        payload = json.dumps(body)
    result = subprocess.run(args, input=payload, capture_output=True, text=True, timeout=30)
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("RICHMOND_BASIC_READY") != "true" or not os.environ.get("GH_TOKEN")
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or len(args) != 1):
        print(json.dumps({"status": "blocked", "reason": "Aggregate state publishing requires the ready trusted main workflow"}))
        return 2
    root = Path(args[0])
    reports = {}
    for source in ("agenda", "finance"):
        try:
            reports[source] = json.loads((root / f"{source}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reports[source] = {"status": "failed"}
    prefix = f"repos/{repository}"
    branch = api(prefix + "/git/ref/heads/" + BRANCH)
    if branch is None:
        main_ref = api(prefix + "/git/ref/heads/main")
        if not main_ref or api(prefix + "/git/refs", method="POST", body={"ref": "refs/heads/" + BRANCH, "sha": main_ref["object"]["sha"]}) is None:
            print(json.dumps({"status": "failed", "reason": "Audit branch could not be prepared"}))
            return 1
    existing = api(prefix + "/contents/" + FILE + "?ref=" + BRANCH)
    previous = {}
    if existing:
        try:
            previous = json.loads(base64.b64decode(existing["content"]).decode())
        except (ValueError, KeyError):
            print(json.dumps({"status": "failed", "reason": "Existing audit state is invalid; preserving it for review"}))
            return 1
    now = datetime.now(timezone.utc).isoformat()
    state = aggregate_state(previous, reports, now)
    body = {"message": "Record bounded Richmond basic source check " + now[:10], "branch": BRANCH,
            "content": base64.b64encode((json.dumps(state, indent=2) + "\n").encode()).decode()}
    if existing:
        body["sha"] = existing["sha"]
    if api(prefix + "/contents/" + FILE, method="PUT", body=body) is None:
        print(json.dumps({"status": "failed", "reason": "Aggregate audit state could not be persisted"}))
        return 1
    print(json.dumps({"status": "recorded", "sources": {key: value["outcome"] for key, value in state["sources"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
