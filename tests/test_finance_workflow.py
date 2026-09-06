from pathlib import Path

import yaml


def test_daily_finance_is_independent_no_model_and_preserves_workflow_alert_name():
    root = Path(__file__).resolve().parent.parent
    workflow = yaml.safe_load((root / ".github/workflows/data-sync.yml").read_text())
    assert workflow["name"] == "Data Sync"
    job = workflow["jobs"]["daily-finance-ledger"]
    assert "needs" not in job
    assert "refs/heads/main" in job["if"] and "30 7 * * *" in job["if"]
    refresh = next(s for s in job["steps"] if "finance_sync.py" in s.get("run", ""))
    assert set(refresh["env"]) == {"DATABASE_URL"}
    assert "--apply" in refresh["run"] and "data_sync.py" not in refresh["run"]
    assert "continue-on-error" not in refresh
    assert any(s.get("if") == "always()" and "previous source snapshot" in s.get("run", "") for s in job["steps"])


def test_legacy_receipt_loader_cannot_reintroduce_outgoing_reports():
    from unittest.mock import MagicMock
    from db.contributions import load_contributions_to_db
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
    stats = load_contributions_to_db(conn, [{"transaction_type": "F497P2", "amount": 30000}], commit=False)
    assert stats["skipped"] == 1 and stats["contributions"] == 0
    statements = [str(c.args[0]) for c in conn.cursor.return_value.__enter__.return_value.execute.call_args_list]
    assert not any("INSERT" in s or "DELETE" in s for s in statements)
