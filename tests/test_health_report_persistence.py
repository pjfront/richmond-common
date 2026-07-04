"""P0.7 regression tests: health report persistence must be crash-proof.

The 2026-05-10 incident: a truncated/double-written health report
(health_20260510T041714Z.json) crashed load_previous_report on every
subsequent run — BEFORE save_report — so no health report was saved for
~8 weeks and trend comparison was silently dead. These tests pin the two
fixes: corrupt-previous-report tolerance (quarantine + None, never raise)
and atomic saves (no partial file ever visible at the final path).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import system_health
from system_health import (
    HEALTH_REPORTS_DIR,
    format_brief_report,
    load_previous_report,
    save_report,
)


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "src" / HEALTH_REPORTS_DIR).mkdir(parents=True)
    return tmp_path


def _write_report(root: Path, name: str, content: str) -> Path:
    path = root / "src" / HEALTH_REPORTS_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadPreviousReport:
    def test_returns_latest_valid_report(self, project_root):
        _write_report(project_root, "health_20260101T000000Z.json", '{"a": 1}')
        _write_report(project_root, "health_20260201T000000Z.json", '{"a": 2}')
        assert load_previous_report(project_root) == {"a": 2}

    def test_corrupt_report_quarantined_not_raised(self, project_root):
        """The exact 2026-05-10 failure shape: valid JSON + trailing extra
        data ('Extra data' JSONDecodeError). Must not raise; must rename
        the bad file out of the health_*.json glob."""
        bad = _write_report(
            project_root, "health_20260510T041714Z.json", '{"a": 1}{"a": 1}'
        )
        assert load_previous_report(project_root) is None
        assert not bad.exists()
        assert bad.with_name(bad.name + ".corrupt").exists()

    def test_run_after_quarantine_self_heals(self, project_root):
        """Next run finds the newest non-quarantined report."""
        _write_report(project_root, "health_20260401T000000Z.json", '{"a": 1}')
        _write_report(project_root, "health_20260510T041714Z.json", "{bad")
        assert load_previous_report(project_root) is None  # quarantines
        assert load_previous_report(project_root) == {"a": 1}

    def test_empty_dir_returns_none(self, project_root):
        assert load_previous_report(project_root) is None


class TestSaveReport:
    def test_save_and_reload_roundtrip(self, project_root):
        path = save_report({"generated_at": "x", "n": 3}, project_root)
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["n"] == 3

    def test_no_tmp_file_left_behind(self, project_root):
        save_report({"generated_at": "2026-07-04T000000Z", "n": 1}, project_root)
        leftovers = list(
            (project_root / "src" / HEALTH_REPORTS_DIR).glob("*.tmp")
        )
        assert leftovers == []

    def test_failed_write_leaves_no_partial_final_file(self, project_root, monkeypatch):
        """If the dump raises mid-write, the final health_*.json path must
        not exist (os.replace never ran) and the temp file is cleaned up."""

        def exploding_dump(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(system_health.json, "dump", exploding_dump)
        with pytest.raises(OSError):
            save_report({"generated_at": "2026-07-04T000000Z", "n": 1}, project_root)
        reports_dir = project_root / "src" / HEALTH_REPORTS_DIR
        assert list(reports_dir.glob("health_*.json")) == []
        assert list(reports_dir.glob("*.tmp")) == []


class TestBriefReport:
    def test_liveness_failures_never_dropped(self):
        """Priority-1 section prints ALL failures even past the line cap —
        the cap must drop lower sections, never truncate the failure list
        (the head -80 regression this replaces)."""
        failures = [
            {"id": f"exp_{i}", "owner": "o", "count": 1, "severity": "high",
             "status": "failing"}
            for i in range(100)
        ]
        report = {
            "generated_at": "2026-07-04",
            "pipeline_liveness": {
                "status": "ok", "passing": 0, "total": 100,
                "failing": 100, "errored": 0, "failures": failures,
            },
            "risk_summary": {},
        }
        out = format_brief_report(report, max_lines=70)
        for i in range(100):
            assert f"exp_{i}" in out
        assert "Full report:" in out  # lower sections dropped, pointer shown

    def test_brief_fits_cap_when_healthy(self):
        report = {
            "generated_at": "2026-07-04",
            "pipeline_liveness": {
                "status": "ok", "passing": 29, "total": 29,
                "failing": 0, "errored": 0, "failures": [],
            },
            "risk_summary": {"cost_to_date": 1.0, "monthly_cap": 5.0},
            "operator_briefing": {"available": False},
        }
        out = format_brief_report(report)
        assert len(out.splitlines()) <= 70
        assert "unknown (database unavailable)" in out  # honest, not fake zero
