import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("basic_refresh_state", Path(__file__).with_name("record_refresh_state.py"))
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


def test_failure_preserves_success_and_counts_without_private_error_details():
    previous = {"sources": {"finance": {"last_success": "2026-10-03", "counts": {"events": 1424}}}}
    report = {"finance": {"status": "failed", "reason": "private donor/address/credential"}}
    result = state.aggregate_state(previous, report, "2026-10-04")
    finance = result["sources"]["finance"]
    assert finance["last_success"] == "2026-10-03"
    assert finance["last_attempt"] == "2026-10-04"
    assert finance["counts"] == {"events": 1424}
    assert finance["outcome"] == "check_failed"
    assert "private" not in json.dumps(result)


def test_success_accepts_only_allowlisted_aggregate_numbers():
    report = {"agenda": {"status": "completed", "modelCalls": 0,
                         "results": [{"items_written": 2, "title": "private", "password": "secret", "events": "untrusted"}]}}
    result = state.aggregate_state({}, report, "2026-10-04")
    assert result["sources"]["agenda"]["counts"] == {"items_written": 2}
    assert result["sources"]["agenda"]["last_success"] == "2026-10-04"
    assert "private" not in json.dumps(result) and "secret" not in json.dumps(result)


def test_unready_local_publisher_never_calls_github(capsys):
    with patch.dict("os.environ", {}, clear=True), patch.object(state, "api", Mock()) as api:
        assert state.main(["unused"]) == 2
        api.assert_not_called()
        assert "blocked" in capsys.readouterr().out
