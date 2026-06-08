"""Tests for src/cost_digest.py — the Anthropic cost digest aggregation.

compute_digest is a pure function (no DB), so these tests feed it synthetic
api_cost rows and assert the rollups by call site, day, and model.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import cost_digest as cd  # noqa: E402


def _row(caller, cost, day="2026-06-01", model="claude-sonnet-4-5", batch=False):
    return {
        "target_artifact": caller,
        "approx_cost": cost,
        "created_at": day,
        "model": model,
        "batch": batch,
    }


class TestCoerceDate:
    def test_datetime(self):
        dt = datetime(2026, 6, 1, 13, 45, tzinfo=timezone.utc)
        assert cd._coerce_date(dt) == "2026-06-01"

    def test_iso_string(self):
        assert cd._coerce_date("2026-06-01T13:45:00+00:00") == "2026-06-01"

    def test_plain_date_string(self):
        assert cd._coerce_date("2026-06-01") == "2026-06-01"


class TestComputeDigest:
    def test_totals(self):
        rows = [
            _row("netfile_paper_extractor", 6.46),
            _row("plain_language_summarizer", 3.01),
            _row("minutes_extraction", 2.00, batch=True),
        ]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30)
        assert d["total"] == pytest.approx(11.47)
        assert d["call_count"] == 3
        assert d["batch_total"] == pytest.approx(2.00)
        assert d["sync_total"] == pytest.approx(9.47)

    def test_by_caller_sorted_desc(self):
        rows = [
            _row("a", 1.0),
            _row("b", 5.0),
            _row("a", 2.0),
            _row("c", 4.0),
        ]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30)
        callers = [c["caller"] for c in d["by_caller"]]
        # b=5.0, c=4.0, a=3.0 (1.0+2.0 aggregated)
        assert callers == ["b", "c", "a"]
        a = next(c for c in d["by_caller"] if c["caller"] == "a")
        assert a["cost"] == pytest.approx(3.0)
        assert a["calls"] == 2

    def test_by_day_sorted_asc(self):
        rows = [
            _row("a", 1.0, day="2026-06-03"),
            _row("a", 2.0, day="2026-06-01"),
            _row("a", 0.5, day="2026-06-01"),
        ]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30)
        assert [x["day"] for x in d["by_day"]] == ["2026-06-01", "2026-06-03"]
        assert d["by_day"][0]["cost"] == pytest.approx(2.5)

    def test_by_model(self):
        rows = [
            _row("a", 1.0, model="claude-sonnet-4-5"),
            _row("a", 2.0, model="claude-sonnet-4-20250514"),
            _row("a", 0.5, model="claude-sonnet-4-5"),
        ]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30)
        top_model = d["by_model"][0]
        assert top_model["model"] == "claude-sonnet-4-20250514"
        assert top_model["cost"] == pytest.approx(2.0)

    def test_empty_rows(self):
        d = cd.compute_digest([], cap_usd=5.0, days=30)
        assert d["total"] == 0.0
        assert d["by_caller"] == []
        assert d["by_day"] == []
        assert d["call_count"] == 0

    def test_null_cost_treated_as_zero(self):
        rows = [_row("a", None), _row("b", 1.5)]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30)
        assert d["total"] == pytest.approx(1.5)

    def test_missing_caller_bucketed_unknown(self):
        rows = [{"approx_cost": 1.0, "created_at": "2026-06-01"}]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30)
        assert d["by_caller"][0]["caller"] == "unknown"

    def test_mtd_passthrough(self):
        d = cd.compute_digest([], cap_usd=5.0, days=30, mtd_total=4.25)
        assert d["mtd_total"] == pytest.approx(4.25)
        assert d["cap_usd"] == 5.0


class TestFormatDigest:
    def test_renders_over_cap_flag(self):
        rows = [_row("netfile_paper_extractor", 6.0)]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30, mtd_total=6.0)
        text = cd.format_digest(d)
        assert "OVER CAP" in text
        assert "netfile_paper_extractor" in text

    def test_renders_under_cap_no_flag(self):
        rows = [_row("a", 1.0)]
        d = cd.compute_digest(rows, cap_usd=5.0, days=30, mtd_total=1.0)
        text = cd.format_digest(d)
        assert "OVER CAP" not in text
