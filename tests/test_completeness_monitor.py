"""Tests for completeness_monitor.py."""
from unittest.mock import MagicMock, call

import pytest

from completeness_monitor import (
    get_meeting_completeness,
    get_document_coverage,
    get_trend_anomalies,
    get_completeness_summary,
    format_text_report,
    WEIGHT_ITEMS,
    WEIGHT_VOTES,
    WEIGHT_ATTENDANCE,
    WEIGHT_URLS,
)


# -- Helpers -----------------------------------------------------------------

def _make_conn(query_results: list[list[tuple]]):
    """Create a mock connection that returns different rows per query.

    query_results is a list of result sets. Each call to cursor.execute()
    followed by fetchall()/fetchone() returns the next result set.
    """
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    # Track which call we're on
    call_index = [0]

    def _fetchall():
        idx = call_index[0]
        if idx < len(query_results):
            return query_results[idx]
        return []

    def _fetchone():
        idx = call_index[0]
        if idx < len(query_results):
            rows = query_results[idx]
            return rows[0] if rows else None
        return None

    def _execute(*args, **kwargs):
        pass

    def _on_fetchall():
        result = _fetchall()
        call_index[0] += 1
        return result

    def _on_fetchone():
        result = _fetchone()
        call_index[0] += 1
        return result

    cursor.execute = _execute
    cursor.fetchall = _on_fetchall
    cursor.fetchone = _on_fetchone

    return conn


# -- Meeting UUIDs for testing -----------------------------------------------

M1 = "00000000-0000-0000-0000-000000000001"
M2 = "00000000-0000-0000-0000-000000000002"
M3 = "00000000-0000-0000-0000-000000000003"


# -- TestMeetingCompleteness --------------------------------------------------

class TestMeetingCompleteness:
    def test_complete_meeting_scores_100(self):
        """Meeting with items, votes, attendance, and all URLs scores 100."""
        rows = [(
            M1, "2026-02-15", "regular",
            "https://example.com/minutes.pdf",
            "https://example.com/agenda.pdf",
            "https://example.com/video",
            25, 14, 7,
        )]
        conn = _make_conn([rows])
        result = get_meeting_completeness(conn, limit=1)

        assert len(result) == 1
        m = result[0]
        assert m["completeness_score"] == 100
        assert m["agenda_item_count"] == 25
        assert m["vote_count"] == 14
        assert m["attendance_count"] == 7
        assert m["has_minutes"] is True
        assert m["has_agenda"] is True
        assert m["has_video"] is True

    def test_meeting_without_votes_partial_score(self):
        """Meeting with items and attendance but no votes gets partial score."""
        rows = [(
            M1, "2026-02-15", "regular",
            "https://example.com/minutes.pdf",
            None, None,
            20, 0, 7,
        )]
        conn = _make_conn([rows])
        result = get_meeting_completeness(conn, limit=1)

        m = result[0]
        # items (30) + attendance (20) + urls (1/3 * 20 = 6) = 56
        expected = WEIGHT_ITEMS + WEIGHT_ATTENDANCE + int(WEIGHT_URLS * (1 / 3))
        assert m["completeness_score"] == expected
        assert m["vote_count"] == 0

    def test_empty_meeting_scores_zero(self):
        """Meeting with nothing scores 0."""
        rows = [(M1, "2026-02-15", "regular", None, None, None, 0, 0, 0)]
        conn = _make_conn([rows])
        result = get_meeting_completeness(conn, limit=1)

        assert result[0]["completeness_score"] == 0

    def test_no_meetings_returns_empty(self):
        conn = _make_conn([[]])
        result = get_meeting_completeness(conn)

        assert result == []

    def test_multiple_meetings_ordered(self):
        """Multiple meetings are returned in order."""
        rows = [
            (M1, "2026-02-15", "regular", None, None, None, 25, 14, 7),
            (M2, "2026-02-01", "regular", None, None, None, 20, 10, 7),
        ]
        conn = _make_conn([rows])
        result = get_meeting_completeness(conn, limit=2)

        assert len(result) == 2
        assert result[0]["meeting_date"] == "2026-02-15"
        assert result[1]["meeting_date"] == "2026-02-01"


# -- TestDocumentCoverage ----------------------------------------------------

class TestDocumentCoverage:
    def test_full_coverage(self):
        """All meetings have all URLs -> 100%."""
        conn = _make_conn([[(10, 10, 10, 10)]])
        result = get_document_coverage(conn)

        assert result["total_meetings"] == 10
        assert result["minutes"]["percentage"] == 100.0
        assert result["agenda"]["percentage"] == 100.0
        assert result["video"]["percentage"] == 100.0

    def test_partial_coverage(self):
        """Mixed URL availability -> correct percentages."""
        conn = _make_conn([[(100, 80, 60, 40)]])
        result = get_document_coverage(conn)

        assert result["total_meetings"] == 100
        assert result["minutes"]["percentage"] == 80.0
        assert result["minutes"]["count"] == 80
        assert result["agenda"]["percentage"] == 60.0
        assert result["video"]["percentage"] == 40.0

    def test_no_meetings(self):
        """Zero meetings -> 0% coverage, no errors."""
        conn = _make_conn([[(0, 0, 0, 0)]])
        result = get_document_coverage(conn)

        assert result["total_meetings"] == 0
        assert result["minutes"]["percentage"] == 0.0

    def test_no_row(self):
        """No row returned -> safe defaults."""
        conn = _make_conn([[]])
        result = get_document_coverage(conn)

        assert result["total_meetings"] == 0


# -- TestTrendAnomalies ------------------------------------------------------

class TestTrendAnomalies:
    def test_no_anomalies_normal_meeting(self):
        """Meeting within baseline range -> no anomaly."""
        # Baseline: avg 25 items, stddev 5, avg 14 votes, stddev 4, 50 meetings
        baseline = [(25.0, 5.0, 14.0, 4.0, 50)]
        recent = [(M1, "2026-02-15", "regular", 24, 13, 7)]
        conn = _make_conn([baseline, recent])

        result = get_trend_anomalies(conn, recent_count=1)
        assert result == []

    def test_low_item_count_flagged(self):
        """Meeting with item count far below average -> warning."""
        baseline = [(25.0, 5.0, 14.0, 4.0, 50)]
        # 10 items is 3 stddevs below mean (25 - 3*5 = 10)
        recent = [(M1, "2026-02-15", "regular", 10, 13, 7)]
        conn = _make_conn([baseline, recent])

        result = get_trend_anomalies(conn, recent_count=1)
        item_anomalies = [a for a in result if "item_count" in a["anomaly_type"]]
        assert len(item_anomalies) == 1
        assert item_anomalies[0]["anomaly_type"] == "low_item_count"
        assert item_anomalies[0]["severity"] == "warning"

    def test_zero_items_is_alert(self):
        """Meeting with 0 items -> alert severity."""
        baseline = [(25.0, 5.0, 14.0, 4.0, 50)]
        recent = [(M1, "2026-02-15", "regular", 0, 0, 7)]
        conn = _make_conn([baseline, recent])

        result = get_trend_anomalies(conn, recent_count=1)
        item_anomalies = [a for a in result if "item" in a["anomaly_type"]]
        assert any(a["severity"] == "alert" for a in item_anomalies)

    def test_no_attendance_flagged(self):
        """Meeting with 0 attendance records -> warning."""
        baseline = [(25.0, 5.0, 14.0, 4.0, 50)]
        recent = [(M1, "2026-02-15", "regular", 25, 14, 0)]
        conn = _make_conn([baseline, recent])

        result = get_trend_anomalies(conn, recent_count=1)
        att_anomalies = [a for a in result if a["anomaly_type"] == "no_attendance"]
        assert len(att_anomalies) == 1
        assert att_anomalies[0]["severity"] == "warning"

    def test_special_meeting_skips_baseline_check(self):
        """Special meetings are not checked against regular meeting baseline."""
        baseline = [(25.0, 5.0, 14.0, 4.0, 50)]
        # Special meeting with 3 items would flag for regular but not special
        recent = [(M1, "2026-02-15", "special", 3, 2, 5)]
        conn = _make_conn([baseline, recent])

        result = get_trend_anomalies(conn, recent_count=1)
        # Should not flag item/vote count anomalies for special meeting
        baseline_anomalies = [
            a for a in result if "item_count" in a["anomaly_type"] or "vote_count" in a["anomaly_type"]
        ]
        assert len(baseline_anomalies) == 0

    def test_not_enough_data_returns_empty(self):
        """Fewer than 3 meetings in history -> empty (no meaningful baseline)."""
        baseline = [(25.0, 5.0, 14.0, 4.0, 2)]  # only 2 meetings
        conn = _make_conn([baseline])

        result = get_trend_anomalies(conn, recent_count=1)
        assert result == []

    def test_zero_stddev_skips_check(self):
        """If all meetings have identical counts (stddev=0), skip that check."""
        baseline = [(25.0, 0.0, 14.0, 0.0, 50)]
        recent = [(M1, "2026-02-15", "regular", 20, 10, 7)]
        conn = _make_conn([baseline, recent])

        result = get_trend_anomalies(conn, recent_count=1)
        # stddev=0 means we can't compute deviation, so no baseline anomalies
        baseline_anomalies = [
            a for a in result if "item_count" in a["anomaly_type"] or "vote_count" in a["anomaly_type"]
        ]
        assert len(baseline_anomalies) == 0


# -- TestCompletenessSummary --------------------------------------------------

class TestCompletenessSummary:
    def _make_summary_conn(self, meetings_rows, coverage_row, baseline_row, recent_rows):
        """Build a conn mock for the full summary which calls 4 queries."""
        return _make_conn([
            meetings_rows,     # get_meeting_completeness
            [coverage_row],    # get_document_coverage
            [baseline_row],    # get_trend_anomalies baseline
            recent_rows,       # get_trend_anomalies recent
        ])

    def test_healthy_when_no_anomalies(self):
        meetings = [(M1, "2026-02-15", "regular", "u", "u", "u", 25, 14, 7)]
        coverage = (10, 10, 10, 10)
        baseline = (25.0, 5.0, 14.0, 4.0, 50)
        recent = [(M1, "2026-02-15", "regular", 25, 14, 7)]

        conn = self._make_summary_conn(meetings, coverage, baseline, recent)
        result = get_completeness_summary(conn)

        assert result["overall_status"] == "healthy"
        assert result["meeting_completeness"]["complete"] == 1

    def test_warning_when_anomalies_exist(self):
        meetings = [(M1, "2026-02-15", "regular", "u", "u", "u", 25, 14, 0)]
        coverage = (10, 10, 10, 10)
        baseline = (25.0, 5.0, 14.0, 4.0, 50)
        recent = [(M1, "2026-02-15", "regular", 25, 14, 0)]

        conn = self._make_summary_conn(meetings, coverage, baseline, recent)
        result = get_completeness_summary(conn)

        assert result["overall_status"] == "warning"

    def test_alert_when_severe_issues(self):
        meetings = [(M1, "2026-02-15", "regular", None, None, None, 0, 0, 0)]
        coverage = (10, 5, 3, 2)
        baseline = (25.0, 5.0, 14.0, 4.0, 50)
        recent = [(M1, "2026-02-15", "regular", 0, 0, 0)]

        conn = self._make_summary_conn(meetings, coverage, baseline, recent)
        result = get_completeness_summary(conn)

        assert result["overall_status"] == "alert"

    def test_checked_at_present(self):
        meetings = [(M1, "2026-02-15", "regular", "u", "u", "u", 25, 14, 7)]
        coverage = (10, 10, 10, 10)
        baseline = (25.0, 5.0, 14.0, 4.0, 50)
        recent = [(M1, "2026-02-15", "regular", 25, 14, 7)]

        conn = self._make_summary_conn(meetings, coverage, baseline, recent)
        result = get_completeness_summary(conn)

        assert "checked_at" in result
        assert "T" in result["checked_at"]  # ISO format


# -- TestFormatTextReport -----------------------------------------------------

class TestFormatTextReport:
    def test_healthy_report(self):
        summary = {
            "overall_status": "healthy",
            "meeting_completeness": {"checked": 10, "complete": 10, "recent_meetings": []},
            "document_coverage": {
                "total_meetings": 100,
                "minutes": {"count": 95, "percentage": 95.0},
                "agenda": {"count": 80, "percentage": 80.0},
                "video": {"count": 60, "percentage": 60.0},
            },
            "anomalies": [],
            "checked_at": "2026-02-28T00:00:00+00:00",
        }
        text = format_text_report(summary)

        assert "HEALTHY" in text
        assert "10/10" in text
        assert "95.0%" in text
        assert "No anomalies" in text

    def test_alert_only_hides_normal_sections(self):
        summary = {
            "overall_status": "healthy",
            "meeting_completeness": {"checked": 10, "complete": 10, "recent_meetings": []},
            "document_coverage": {
                "total_meetings": 100,
                "minutes": {"count": 95, "percentage": 95.0},
                "agenda": {"count": 80, "percentage": 80.0},
                "video": {"count": 60, "percentage": 60.0},
            },
            "anomalies": [],
            "checked_at": "2026-02-28T00:00:00+00:00",
        }
        text = format_text_report(summary, alert_only=True)

        assert "Meeting Completeness" not in text
        assert "Document Coverage" not in text

    def test_anomalies_shown(self):
        summary = {
            "overall_status": "warning",
            "meeting_completeness": {"checked": 10, "complete": 8, "recent_meetings": []},
            "document_coverage": {
                "total_meetings": 10,
                "minutes": {"count": 10, "percentage": 100.0},
                "agenda": {"count": 10, "percentage": 100.0},
                "video": {"count": 10, "percentage": 100.0},
            },
            "anomalies": [
                {
                    "meeting_id": M1,
                    "meeting_date": "2026-02-15",
                    "anomaly_type": "no_attendance",
                    "description": "No attendance records",
                    "severity": "warning",
                },
            ],
            "checked_at": "2026-02-28T00:00:00+00:00",
        }
        text = format_text_report(summary)

        assert "Anomalies (1)" in text
        assert "no_attendance" in text
        assert "2026-02-15" in text
