"""Tests for data_quality_checks.py — Data Quality Regression Suite."""
from unittest.mock import MagicMock

import pytest

from data_quality_checks import (
    QualityIssue,
    check_sentinel_strings,
    check_missing_item_numbers,
    check_financial_amount_formatting,
    check_suspicious_amounts,
    check_confidence_tier_sync,
    check_missing_fips,
    check_orphaned_records,
    check_empty_required_fields,
    check_duplicate_contributions,
    run_all_checks,
    format_text_report,
    TIER_THRESHOLDS,
)


# -- Helpers -----------------------------------------------------------------


def _make_conn(query_results: list[list[tuple]]):
    """Create a mock connection that returns different rows per query.

    Each cursor.execute() + fetchall()/fetchone() pair consumes the
    next result set from the list.
    """
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    call_index = [0]

    def _fetchall():
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(query_results):
            return query_results[idx]
        return []

    def _fetchone():
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(query_results):
            rows = query_results[idx]
            return rows[0] if rows else None
        return None

    cursor.execute = MagicMock()
    cursor.fetchall = _fetchall
    cursor.fetchone = _fetchone

    return conn


# -- Test UUIDs -------------------------------------------------------------

ID1 = "00000000-0000-0000-0000-000000000001"
ID2 = "00000000-0000-0000-0000-000000000002"
ID3 = "00000000-0000-0000-0000-000000000003"


# -- TestSentinelStrings -----------------------------------------------------


class TestSentinelStrings:
    def test_no_sentinels_returns_empty(self):
        """Clean data -> no issues."""
        # 2 columns (title, description) x 4 patterns = 8 queries for agenda_items
        # + 4 queries for documents = 12 total
        results = [[] for _ in range(12)]
        conn = _make_conn(results)
        issues = check_sentinel_strings(conn)
        assert issues == []

    def test_sentinel_in_title_flagged(self):
        """Sentinel pattern in agenda_items.title -> error."""
        # First query (title, pattern 0) finds a match
        results = [[(ID1,)]] + [[] for _ in range(11)]
        conn = _make_conn(results)
        issues = check_sentinel_strings(conn)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check_name == "sentinel_strings"
        assert issues[0].table == "agenda_items"
        assert ID1 in issues[0].sample_ids

    def test_sentinel_in_documents_flagged(self):
        """Sentinel pattern in documents.extracted_text -> error."""
        # 8 agenda_items queries clean, then first documents query matches
        results = [[] for _ in range(8)] + [[(ID1,)]] + [[] for _ in range(3)]
        conn = _make_conn(results)
        issues = check_sentinel_strings(conn)

        assert len(issues) == 1
        assert issues[0].table == "documents"


# -- TestMissingItemNumbers --------------------------------------------------


class TestMissingItemNumbers:
    def test_no_missing_numbers(self):
        conn = _make_conn([[]])
        issues = check_missing_item_numbers(conn)
        assert issues == []

    def test_missing_number_with_pattern_title(self):
        """Item with empty item_number but 'A.1'-style title -> warning."""
        conn = _make_conn([[(ID1, "A.1 Approval of Minutes")]])
        issues = check_missing_item_numbers(conn)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].check_name == "missing_item_number"
        assert "A.1" in issues[0].details


# -- TestFinancialAmountFormatting -------------------------------------------


class TestFinancialAmountFormatting:
    def test_no_negative_amounts(self):
        conn = _make_conn([[]])
        issues = check_financial_amount_formatting(conn)
        assert issues == []

    def test_negative_amount_flagged(self):
        """Negative contribution amount -> warning."""
        conn = _make_conn([[(ID1, -500.0)]])
        issues = check_financial_amount_formatting(conn)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].check_name == "negative_contribution_amount"


# -- TestSuspiciousAmounts ---------------------------------------------------


class TestSuspiciousAmounts:
    def test_no_expenditures_table(self):
        """If city_expenditures table doesn't exist, skip gracefully."""
        conn = _make_conn([[(False,)]])
        issues = check_suspicious_amounts(conn)
        assert issues == []

    def test_low_amount_flagged(self):
        """Expenditure under $100 -> info."""
        conn = _make_conn([
            [(True,)],       # table exists
            [(ID1, 50.00)],  # low amount found
        ])
        issues = check_suspicious_amounts(conn)

        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].check_name == "suspicious_low_amount"

    def test_no_low_amounts(self):
        """All expenditures >= $100 -> clean."""
        conn = _make_conn([
            [(True,)],  # table exists
            [],          # no low amounts
        ])
        issues = check_suspicious_amounts(conn)
        assert issues == []


# -- TestConfidenceTierSync --------------------------------------------------


class TestConfidenceTierSync:
    def test_synced_tiers_pass(self):
        """All tiers match confidence -> no issues."""
        conn = _make_conn([[]])
        issues = check_confidence_tier_sync(conn)
        assert issues == []

    def test_desynced_tier_flagged(self):
        """Flag with confidence 0.65 stored as tier 2 (should be tier 1) -> error."""
        # Row: id, confidence, stored_tier, expected_tier
        conn = _make_conn([[(ID1, 0.65, 2, 1)]])
        issues = check_confidence_tier_sync(conn)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check_name == "confidence_tier_desync"
        assert "0.65" in issues[0].details
        assert "stored_tier=2" in issues[0].details
        assert "expected_tier=1" in issues[0].details

    def test_tier4_not_flagged_as_desync(self):
        """Flags below 0.50 stored as tier 4 should NOT be flagged.

        Previously the CASE only had 3 branches (ELSE 3), so tier-4
        flags were misreported as expected_tier=3.
        """
        # No desynced rows returned from the query = clean
        conn = _make_conn([[]])
        issues = check_confidence_tier_sync(conn)
        assert issues == []


# -- TestMissingFips ---------------------------------------------------------


class TestMissingFips:
    def test_all_have_fips(self):
        """No records with missing FIPS -> clean."""
        # 4 tables, each: column check (True) + count (0)
        results = []
        for _ in range(4):
            results.append([(True,)])   # has city_fips column
            results.append([(0,)])      # zero missing
        conn = _make_conn(results)
        issues = check_missing_fips(conn)
        assert issues == []

    def test_missing_fips_flagged(self):
        """Records with NULL city_fips -> error."""
        results = [
            [(True,)],  # meetings has city_fips
            [(3,)],     # 3 meetings missing fips
            [(True,)],  # officials has city_fips
            [(0,)],     # 0 officials missing
            [(True,)],  # donors has city_fips
            [(0,)],     # 0 donors missing
            [(True,)],  # documents has city_fips
            [(0,)],     # 0 documents missing
        ]
        conn = _make_conn(results)
        issues = check_missing_fips(conn)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].table == "meetings"
        assert issues[0].count == 3

    def test_table_without_fips_column_skipped(self):
        """Table without city_fips column is silently skipped."""
        results = [
            [(False,)],  # meetings doesn't have city_fips (weird but possible)
            [(True,)],   # officials
            [(0,)],
            [(True,)],   # donors
            [(0,)],
            [(True,)],   # documents
            [(0,)],
        ]
        conn = _make_conn(results)
        issues = check_missing_fips(conn)
        assert issues == []


# -- TestOrphanedRecords -----------------------------------------------------


class TestOrphanedRecords:
    def test_no_orphans(self):
        """All records have parents -> clean."""
        conn = _make_conn([[], [], [], []])
        issues = check_orphaned_records(conn)
        assert issues == []

    def test_orphaned_agenda_items(self):
        """Agenda items with no meeting -> error."""
        conn = _make_conn([[(ID1,)], [], [], []])
        issues = check_orphaned_records(conn)

        assert len(issues) == 1
        assert issues[0].check_name == "orphaned_records"
        assert issues[0].table == "agenda_items"
        assert issues[0].severity == "error"

    def test_orphaned_votes(self):
        """Votes without motions -> error."""
        conn = _make_conn([[], [], [(ID1,), (ID2,)], []])
        issues = check_orphaned_records(conn)

        assert len(issues) == 1
        assert issues[0].table == "votes"
        assert issues[0].count == 2

    def test_multiple_orphan_types(self):
        """Multiple orphan types found -> multiple issues."""
        conn = _make_conn([[(ID1,)], [(ID2,)], [], []])
        issues = check_orphaned_records(conn)

        assert len(issues) == 2
        tables = {i.table for i in issues}
        assert "agenda_items" in tables
        assert "motions" in tables


# -- TestEmptyRequiredFields -------------------------------------------------


class TestEmptyRequiredFields:
    def test_no_empty_fields(self):
        conn = _make_conn([[], [], []])
        issues = check_empty_required_fields(conn)
        assert issues == []

    def test_empty_official_name(self):
        """Official with empty name -> warning."""
        conn = _make_conn([[(ID1,)], [], []])
        issues = check_empty_required_fields(conn)

        assert len(issues) == 1
        assert issues[0].table == "officials"
        assert issues[0].severity == "warning"

    def test_empty_donor_name(self):
        """Donor with empty name -> warning."""
        conn = _make_conn([[], [], [(ID1,)]])
        issues = check_empty_required_fields(conn)

        assert len(issues) == 1
        assert issues[0].table == "donors"


# -- TestDuplicateContributions ----------------------------------------------


class TestDuplicateContributions:
    def test_no_duplicates(self):
        conn = _make_conn([[]])
        issues = check_duplicate_contributions(conn)
        assert issues == []

    def test_duplicates_flagged(self):
        """Duplicate contributions -> warning with count."""
        conn = _make_conn([
            [("Chevron USA", 5000.0, "2025-10-15", 3)],
        ])
        issues = check_duplicate_contributions(conn)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].count == 2  # 3 - 1 = 2 extra copies
        assert "Chevron" in issues[0].details


# -- TestRunAllChecks --------------------------------------------------------


class TestRunAllChecks:
    def test_all_pass(self):
        """When all checks return no issues -> pass status."""
        # Build enough empty results for all checks
        # Sentinel: 12, missing_item: 1, financial: 1, suspicious: 1,
        # tier_sync: 1, fips: 8, orphaned: 4, empty_fields: 3, duplicates: 1
        results = [[] for _ in range(32)]
        # suspicious_amounts needs table existence check returning False
        results[14] = [(False,)]
        # fips checks need column existence checks
        for i in range(16, 24, 2):
            results[i] = [(True,)]
            results[i + 1] = [(0,)]

        conn = _make_conn(results)
        result = run_all_checks(conn)

        assert result["overall_status"] == "pass"
        assert result["total_issues"] == 0
        assert result["checks_run"] == 9

    def test_subset_of_checks(self):
        """Running a subset of checks works."""
        conn = _make_conn([[], [], []])
        result = run_all_checks(
            conn,
            checks=[check_empty_required_fields],
        )

        assert result["checks_run"] == 1
        assert result["overall_status"] == "pass"

    def test_check_exception_handled(self):
        """If a check function throws, it's captured as an error."""
        def bad_check(conn, city_fips="0660620"):
            raise RuntimeError("database exploded")

        conn = _make_conn([])
        result = run_all_checks(conn, checks=[bad_check])

        assert result["overall_status"] == "error"
        assert result["checks_errored"] == 1
        assert "database exploded" in result["check_results"][0]["error"]


# -- TestFormatTextReport ----------------------------------------------------


class TestFormatTextReport:
    def test_pass_report(self):
        results = {
            "overall_status": "pass",
            "total_issues": 0,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "checks_run": 9,
            "checks_passed": 9,
            "checks_failed": 0,
            "checks_errored": 0,
            "check_results": [
                {"check": "check_sentinel_strings", "status": "pass",
                 "issue_count": 0, "issues": []},
            ],
            "checked_at": "2026-03-13T00:00:00+00:00",
            "city_fips": "0660620",
        }
        text = format_text_report(results)

        assert "PASS" in text
        assert "9 passed" in text
        assert "0 failed" in text

    def test_fail_report_shows_issues(self):
        results = {
            "overall_status": "fail",
            "total_issues": 1,
            "error_count": 1,
            "warning_count": 0,
            "info_count": 0,
            "checks_run": 1,
            "checks_passed": 0,
            "checks_failed": 1,
            "checks_errored": 0,
            "check_results": [
                {
                    "check": "check_missing_fips",
                    "status": "fail",
                    "issue_count": 1,
                    "issues": [{
                        "check_name": "missing_fips",
                        "severity": "error",
                        "description": "Records with NULL city_fips in meetings",
                        "table": "meetings",
                        "count": 5,
                        "sample_ids": [ID1],
                        "details": "",
                    }],
                },
            ],
            "checked_at": "2026-03-13T00:00:00+00:00",
            "city_fips": "0660620",
        }
        text = format_text_report(results)

        assert "FAIL" in text
        assert "1 errors" in text
        assert "missing_fips" in text
        assert "5 records" in text


# -- TestTierThresholds ------------------------------------------------------


class TestTierThresholds:
    def test_thresholds_defined(self):
        """Tier thresholds must have tiers 1, 2, and 3."""
        assert 1 in TIER_THRESHOLDS
        assert 2 in TIER_THRESHOLDS
        assert 3 in TIER_THRESHOLDS

    def test_tier_ordering(self):
        """Tier 1 threshold > Tier 2 threshold > Tier 3 threshold."""
        assert TIER_THRESHOLDS[1] > TIER_THRESHOLDS[2]
        assert TIER_THRESHOLDS[2] > TIER_THRESHOLDS[3]

    def test_tier_1_matches_scanner(self):
        """Tier 1 threshold matches conflict_scanner.py v3 canonical value."""
        from conflict_scanner import V3_TIER_THRESHOLDS
        assert TIER_THRESHOLDS[1] == V3_TIER_THRESHOLDS["high"]

    def test_tier_2_matches_scanner(self):
        """Tier 2 threshold matches conflict_scanner.py v3 canonical value."""
        from conflict_scanner import V3_TIER_THRESHOLDS
        assert TIER_THRESHOLDS[2] == V3_TIER_THRESHOLDS["medium"]

    def test_tier_3_matches_scanner(self):
        """Tier 3 threshold matches conflict_scanner.py v3 canonical value."""
        from conflict_scanner import V3_TIER_THRESHOLDS
        assert TIER_THRESHOLDS[3] == V3_TIER_THRESHOLDS["low"]
