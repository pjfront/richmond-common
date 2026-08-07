"""Tests for the NextRequest/CPRA scraper.

Transform tests use JSON fixtures matching the client API response format.
No network calls or Playwright needed.
"""
import json
import sys
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── JSON fixtures (matching NextRequest client API format) ────

SAMPLE_LIST_ITEM = {
    "request_date": "01/15/2026",
    "staff_cost": "0.0",
    "visibility": "Published",
    "id": "26-042",
    "request_state": "Closed",
    "department_names": "Police Department",
    "due_date": "01/25/2026",
    "poc_name": "Jane Smith",
    "request_path": "/requests/26-042",
    "request_text": "Police department overtime records for 2025",
    "requester_name": None,
}

SAMPLE_LIST_ITEM_2 = {
    "request_date": "02/01/2026",
    "staff_cost": "0.0",
    "visibility": "Published",
    "id": "26-055",
    "request_state": "In Progress",
    "department_names": "City Manager",
    "due_date": "02/11/2026",
    "poc_name": "Bob Jones",
    "request_path": "/requests/26-055",
    "request_text": "City manager contract details",
    "requester_name": None,
}

SAMPLE_DETAIL_RESPONSE = {
    "pretty_id": "26-042",
    "request_text": "<p>I am requesting all overtime records for the Richmond Police Department for the period of January 2025 through December 2025.</p>",
    "request_state": "Closed",
    "visibility": "published",
    "request_visibility": "Published",
    "request_due_date": "January 25, 2026",
    "request_submit_type": None,
    "request_date": "January 15, 2026",
    "department_names": "Police Department",
    "departments": [{"id": 123, "name": "Police Department"}],
    "request_staff_hours": None,
    "request_staff_cost": None,
    "request_field_values": [
        {
            "id": 1,
            "field_id": 1447,
            "field_type": "text",
            "value": "January 2025 - December 2025",
            "display_name": "Date(s) or Date Range(s) of Records",
        },
    ],
    "poc": {"id": 123, "email_or_name": "Jane Smith", "has_tasks": False},
    "requester": {"id": 456, "name": "John Doe", "email": None},
}

SAMPLE_TIMELINE_RESPONSE = {
    "total_count": 3,
    "timeline": [
        {
            "timeline_id": 100001,
            "timeline_name": "Request Published",
            "timeline_byline": "January 15, 2026, 10:00am by Staff",
        },
        {
            "timeline_id": 100002,
            "timeline_name": "Request Closed",
            "timeline_byline": "January 22, 2026,  3:45pm by Staff",
        },
        {
            "timeline_id": 100003,
            "timeline_name": "Request Opened",
            "timeline_byline": "January 15, 2026,  9:30am by the requester",
        },
    ],
    "pinned": [],
}

SAMPLE_DETAIL_NO_DEPT = {
    "pretty_id": "26-100",
    "request_text": "<p>Simple request</p>",
    "request_state": "Open",
    "visibility": "published",
    "request_visibility": "Published",
    "request_due_date": None,
    "request_submit_type": None,
    "request_date": "March 1, 2026",
    "department_names": "None assigned",
    "departments": [],
    "request_staff_hours": None,
    "request_staff_cost": None,
    "request_field_values": [],
    "poc": {"id": 789, "email_or_name": "Staff Member"},
    "requester": {"id": 999, "name": None, "email": None},
}


# ── Transform tests: list items ──────────────────────────────

class TestTransformListItem:
    """Test _transform_list_item with JSON fixtures."""

    def test_transforms_basic_fields(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert result["request_number"] == "26-042"
        assert result["status"] == "Closed"
        assert result["department"] == "Police Department"
        assert result["submitted_date"] == "2026-01-15"

    def test_transforms_second_item(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM_2)
        assert result["request_number"] == "26-055"
        assert result["status"] == "In Progress"
        assert result["department"] == "City Manager"

    def test_transforms_portal_url(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert result["portal_url"] == "https://cityofrichmondca.nextrequest.com/requests/26-042"

    def test_transforms_due_date(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert result["due_date"] == "2026-01-25"

    def test_empty_department_becomes_none(self):
        from nextrequest_scraper import _transform_list_item
        item = {**SAMPLE_LIST_ITEM, "department_names": ""}
        result = _transform_list_item(item)
        assert result["department"] is None

    def test_request_text_preserved(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert "overtime records" in result["request_text"]


# ── Transform tests: detail ──────────────────────────────────

class TestTransformDetail:
    """Test _transform_detail with JSON fixtures."""

    def test_transforms_basic_metadata(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert result["request_number"] == "26-042"
        assert result["status"] == "Closed"
        assert result["department"] == "Police Department"
        assert result["requester_name"] == "John Doe"

    def test_strips_html_from_request_text(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert "<p>" not in result["request_text"]
        assert "overtime records" in result["request_text"]

    def test_parses_dates(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert result["submitted_date"] == "2026-01-15"
        assert result["due_date"] == "2026-01-25"

    def test_none_assigned_department_becomes_none(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_NO_DEPT)
        assert result["department"] is None

    def test_poc_name_extracted(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert result["poc_name"] == "Jane Smith"

    def test_metadata_includes_field_values(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        field_values = result["metadata"]["field_values"]
        assert len(field_values) == 1
        assert field_values[0]["name"] == "Date(s) or Date Range(s) of Records"
        assert field_values[0]["value"] == "January 2025 - December 2025"

    def test_portal_url_generated(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert "26-042" in result["portal_url"]


# ── Timeline tests ───────────────────────────────────────────

class TestExtractClosedDate:
    """Test _extract_closed_date_from_timeline."""

    def test_extracts_closed_date(self):
        from nextrequest_scraper import _extract_closed_date_from_timeline
        result = _extract_closed_date_from_timeline(SAMPLE_TIMELINE_RESPONSE)
        assert result == "2026-01-22"

    def test_returns_none_when_not_closed(self):
        from nextrequest_scraper import _extract_closed_date_from_timeline
        timeline = {"timeline": [
            {"timeline_name": "Request Opened", "timeline_byline": "Jan 15, 2026"},
        ]}
        result = _extract_closed_date_from_timeline(timeline)
        assert result is None

    def test_returns_none_for_empty_timeline(self):
        from nextrequest_scraper import _extract_closed_date_from_timeline
        result = _extract_closed_date_from_timeline({"timeline": []})
        assert result is None


# ── HTML stripping ───────────────────────────────────────────

class TestStripHtml:
    """Test _strip_html utility."""

    def test_strips_simple_tags(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html("<p>Hello world</p>") == "Hello world"

    def test_handles_none(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html(None) == ""

    def test_handles_empty_string(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html("") == ""

    def test_preserves_plain_text(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html("No HTML here") == "No HTML here"


# ── Date parsing ─────────────────────────────────────────────

class TestDateParsing:
    """Test date parsing and days_to_close computation."""

    def test_parse_mm_dd_yyyy(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date("01/15/2026") == "2026-01-15"

    def test_parse_month_dd_yyyy(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date("January 15, 2026") == "2026-01-15"

    def test_parse_iso(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date("2026-01-15") == "2026-01-15"

    def test_parse_none(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date(None) is None

    def test_compute_days_to_close(self):
        from nextrequest_scraper import _compute_days_to_close
        assert _compute_days_to_close("2026-01-15", "2026-01-22") == 7

    def test_compute_days_to_close_none(self):
        from nextrequest_scraper import _compute_days_to_close
        assert _compute_days_to_close(None, "2026-01-22") is None


# ── Platform profile ──────────────────────────────────────────

class TestPlatformProfile:
    """Test that platform profile constants are correct."""

    def test_profile_has_required_fields(self):
        from nextrequest_scraper import NEXTREQUEST_PLATFORM_PROFILE
        assert "platform" in NEXTREQUEST_PLATFORM_PROFILE
        assert "url_pattern" in NEXTREQUEST_PLATFORM_PROFILE
        assert "spa" in NEXTREQUEST_PLATFORM_PROFILE
        assert NEXTREQUEST_PLATFORM_PROFILE["spa"] is True

    def test_base_url_is_richmond(self):
        from nextrequest_scraper import BASE_URL
        assert "richmond" in BASE_URL.lower()
        assert "nextrequest.com" in BASE_URL

    def test_city_fips_is_richmond(self):
        from nextrequest_scraper import CITY_FIPS
        assert CITY_FIPS == "0660620"


# ── Save to DB ────────────────────────────────────────────────

class TestSaveToDb:
    """Test database save/upsert logic."""

    def test_save_creates_request_record(self):
        from nextrequest_scraper import save_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        # Counter Contract (Phase D-3): fetchone returns (id, was_inserted)
        # where was_inserted comes from RETURNING (xmax = 0).
        mock_cursor.fetchone.return_value = ("fake-uuid-001", True)

        results = {
            "city_fips": "0660620",
            "requests": [{
                "request_number": "26-042",
                "request_text": "Overtime records",
                "status": "Closed",
                "department": "Police Department",
                "requester_name": "John Doe",
                "submitted_date": "2026-01-15",
                "due_date": "2026-01-25",
                "closed_date": "2026-01-22",
                "days_to_close": 7,
                "documents": [],
                "portal_url": "https://cityofrichmondca.nextrequest.com/requests/26-042",
                "metadata": {},
            }],
        }

        stats = save_to_db(mock_conn, results, "0660620")
        assert stats["requests_inserted"] == 1
        assert stats["requests_updated"] == 0
        # Backward-compat alias still works
        assert stats["requests_saved"] == 1
        mock_conn.commit.assert_called()

    def test_save_on_conflict_increments_updated(self):
        """Existing request → RETURNING (xmax = 0) is False → updated += 1."""
        from nextrequest_scraper import save_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        # Two requests: first inserts, second hits ON CONFLICT
        mock_cursor.fetchone.side_effect = [
            ("uuid-001", True),
            ("uuid-002", False),
        ]

        results = {
            "requests": [
                {"request_number": "26-001", "status": "Open", "documents": []},
                {"request_number": "26-002", "status": "Closed", "documents": []},
            ],
        }

        stats = save_to_db(mock_conn, results, "0660620")
        assert stats["requests_inserted"] == 1
        assert stats["requests_updated"] == 1
        # Counter invariant
        assert (
            stats["requests_inserted"] + stats["requests_updated"]
            == len(results["requests"])
        )


def test_timeline_failure_is_reported_while_detail_fallback_is_retained():
    from nextrequest_scraper import get_request_detail

    failures = []
    with patch(
        "nextrequest_scraper._fetch_request_detail",
        return_value=SAMPLE_DETAIL_RESPONSE,
    ), patch(
        "nextrequest_scraper._fetch_request_timeline",
        side_effect=RuntimeError("timeline unavailable"),
    ):
        detail = get_request_detail("26-042", failure_sink=failures)

    assert detail["request_number"] == "26-042"
    assert detail["status"] == "Closed"
    assert detail["closed_date"] is None
    assert failures == [{
        "request_id": "26-042",
        "stage": "timeline",
        "error": "RuntimeError: timeline unavailable",
    }]


def test_detail_failure_keeps_list_summary_and_surfaces_failure_stats():
    from nextrequest_scraper import scrape_all

    summary = {
        "request_number": "26-042",
        "request_text": "Overtime records",
        "status": "Closed",
        "department": "Police Department",
        "submitted_date": "2026-01-15",
        "due_date": "2026-01-25",
        "poc_name": "Jane Smith",
        "portal_url": "https://cityofrichmondca.nextrequest.com/requests/26-042",
    }
    with patch(
        "nextrequest_scraper.list_all_requests",
        return_value=[summary],
    ), patch(
        "nextrequest_scraper.get_request_detail",
        side_effect=RuntimeError("detail unavailable"),
    ), patch("nextrequest_scraper.time.sleep"):
        result = scrape_all()

    assert result["requests"][0]["request_number"] == "26-042"
    assert result["requests"][0]["_incomplete_stages"] == [
        "detail", "timeline", "documents",
    ]
    assert result["stats"]["details_scraped"] == 0
    assert result["stats"]["failure_count"] == 1
    assert result["stats"]["failed_request_ids"] == ["26-042"]
    assert result["stats"]["failure_counts"]["detail"] == 1


def test_summary_fallback_preserves_existing_detail_fields_on_conflict():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("existing-id", False)
    result = {
        "requests": [{
            "request_number": "26-042",
            "status": "Closed",
            "request_text": "list-level text",
            "_incomplete_stages": ["detail", "timeline", "documents"],
        }],
    }

    save_to_db(conn, result, "0660620")

    sql, params = cursor.execute.call_args_list[0].args
    assert "THEN nextrequest_requests.closed_date" in sql
    assert "THEN nextrequest_requests.document_count" in sql
    assert "THEN nextrequest_requests.metadata" in sql
    assert params[-5:] == (True, True, True, True, False)


def test_nextrequest_pipeline_marks_partial_scrape_retryable(monkeypatch):
    from pipelines import nextrequest as pipeline

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (None,)
    scrape = MagicMock(return_value={
        "requests": [{
            "request_number": "26-042",
            "status": "Closed",
            "request_text": "Overtime records",
        }],
        "stats": {
            "total_found": 1,
            "details_scraped": 0,
            "documents_found": 0,
            "failure_count": 1,
            "failed_request_ids": ["26-042"],
            "failures": [{
                "request_id": "26-042",
                "stage": "detail",
                "error": "RuntimeError: detail unavailable",
            }],
        },
    })
    save = MagicMock(return_value={
        "requests_inserted": 1,
        "requests_updated": 0,
        "documents_inserted": 0,
        "documents_skipped_existing": 0,
    })
    monkeypatch.setitem(
        sys.modules,
        "nextrequest_scraper",
        SimpleNamespace(
            scrape_all=scrape,
            save_to_db=save,
            list_recent_document_request_ids=lambda **_kwargs: [],
            scrape_request_ids=MagicMock(return_value={
                "requests": [],
                "stats": {"failures": []},
            }),
        ),
    )

    result = pipeline.sync_nextrequest(conn, "0660620")

    cutoff_sql = next(
        call.args[0]
        for call in cursor.execute.call_args_list
        if "FROM data_sync_log" in call.args[0]
    )
    assert "retryable_incomplete" in cutoff_sql
    assert result["records_new"] == 1
    assert result["failed_request_ids"] == ["26-042"]
    assert result["retryable_incomplete"] is True
    assert result["incomplete_count"] == 1
    assert "26-042 detail" in result["incomplete_reasons"][1]


# ── Destructive reconciliation safety ────────────────────────

def test_visibility_classification_is_explicitly_tri_state():
    from nextrequest_scraper import (
        _combined_visibility_state,
        _visibility_state,
    )

    assert _visibility_state("Published") == "public"
    assert _visibility_state("staff_only") == "private"
    assert _visibility_state("new-enum-from-upstream") == "unknown"
    assert _visibility_state(None) == "unknown"
    assert _combined_visibility_state("Published", "Private") == "unknown"
    assert _combined_visibility_state(None, "Published") == "public"


def test_unknown_request_visibility_cannot_become_authoritative():
    from nextrequest_scraper import list_all_requests

    item = {**SAMPLE_LIST_ITEM, "visibility": "released-v2"}
    with patch(
        "nextrequest_scraper._fetch_request_list",
        return_value={"total_count": 1, "requests": [item]},
    ):
        with pytest.raises(ValueError, match="visibility enum is unknown"):
            list_all_requests()


def test_conflicting_request_visibility_fields_fail_authoritative_list():
    from nextrequest_scraper import list_all_requests

    item = {
        **SAMPLE_LIST_ITEM,
        "visibility": "Published",
        "request_visibility": "Private",
    }
    with patch(
        "nextrequest_scraper._fetch_request_list",
        return_value={"total_count": 1, "requests": [item]},
    ):
        with pytest.raises(ValueError, match="visibility enum is unknown"):
            list_all_requests()


def test_unknown_detail_visibility_is_not_private_evidence():
    from nextrequest_scraper import get_request_detail

    drifted_detail = {
        **SAMPLE_DETAIL_RESPONSE,
        "visibility": "Published",
        "request_visibility": "Private",
    }
    with patch(
        "nextrequest_scraper._fetch_request_detail",
        return_value=drifted_detail,
    ):
        with pytest.raises(ValueError, match="detail visibility.*unknown"):
            get_request_detail("26-042", include_documents=True)


def test_empty_request_listing_cannot_become_authoritative():
    from nextrequest_scraper import list_all_requests

    with patch(
        "nextrequest_scraper._fetch_request_list",
        return_value={"total_count": 0, "requests": []},
    ):
        with pytest.raises(RuntimeError, match="returned zero"):
            list_all_requests()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"total_count": 0, "documents": []}, "returned zero"),
        (
            {
                "total_count": 1,
                "documents": [{"id": 10, "visibility": "released-v2"}],
            },
            "visibility enum is unknown",
        ),
        (
            {
                "total_count": 1,
                "documents": [{
                    "id": 10,
                    "visibility": "Published",
                    "state": "Private",
                }],
            },
            "visibility enum is unknown",
        ),
        (
            {
                "total_count": 1,
                "documents": [{"id": 10, "visibility": "Private"}],
            },
            "visibility set shrank implausibly",
        ),
    ],
)
def test_empty_or_filtered_global_document_index_is_not_authoritative(
    payload,
    message,
):
    from nextrequest_scraper import list_all_public_document_ids

    with patch(
        "nextrequest_scraper._fetch_public_document_list",
        return_value=payload,
    ):
        with pytest.raises((RuntimeError, ValueError), match=message):
            list_all_public_document_ids()


def test_partial_global_document_pagination_is_not_authoritative():
    from nextrequest_scraper import list_all_public_document_ids

    first_page = {
        "total_count": 2,
        "documents": [{"id": 10, "visibility": "Published"}],
    }
    truncated_page = {"total_count": 2, "documents": []}
    with patch(
        "nextrequest_scraper._fetch_public_document_list",
        side_effect=[first_page, truncated_page],
    ), patch("nextrequest_scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="pagination ended early"):
            list_all_public_document_ids()


def test_repeated_global_document_id_is_not_complete_coverage():
    from nextrequest_scraper import list_all_public_document_ids

    repeated = {
        "total_count": 2,
        "documents": [
            {"id": 10, "visibility": "Published"},
            {"id": 10, "visibility": "Published"},
        ],
    }
    with patch(
        "nextrequest_scraper._fetch_public_document_list",
        return_value=repeated,
    ):
        with pytest.raises(RuntimeError, match="repeated a source ID"):
            list_all_public_document_ids()


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def test_zero_document_detail_response_is_preservation_not_completeness():
    from nextrequest_scraper import get_request_detail

    failures = []
    with patch(
        "nextrequest_scraper._fetch_request_detail",
        return_value=SAMPLE_DETAIL_RESPONSE,
    ), patch(
        "nextrequest_scraper._fetch_request_timeline",
        return_value=SAMPLE_TIMELINE_RESPONSE,
    ), patch(
        "nextrequest_scraper.http_client.get",
        return_value=_response({
            "total_documents_count": 0,
            "documents": [],
            "documents_state_timestamp": 100,
        }),
    ):
        detail = get_request_detail(
            "26-042",
            include_documents=True,
            failure_sink=failures,
        )

    assert detail["documents"] == []
    assert detail["_documents_listing_observed"] is True
    assert detail["_documents_listing_complete"] is False
    assert failures == []


def test_filtered_empty_document_detail_preserves_current_files():
    from nextrequest_scraper import get_request_detail

    failures = []
    private_document = {
        "id": 10,
        "visibility": "Private",
        "title": "withdrawn.pdf",
    }
    with patch(
        "nextrequest_scraper._fetch_request_detail",
        return_value=SAMPLE_DETAIL_RESPONSE,
    ), patch(
        "nextrequest_scraper._fetch_request_timeline",
        return_value=SAMPLE_TIMELINE_RESPONSE,
    ), patch(
        "nextrequest_scraper.http_client.get",
        return_value=_response({
            "total_documents_count": 1,
            "documents": [private_document],
            "documents_state_timestamp": 100,
        }),
    ):
        detail = get_request_detail(
            "26-042",
            include_documents=True,
            failure_sink=failures,
        )

    assert detail["documents"] == []
    assert detail["_documents_listing_observed"] is True
    assert detail["_documents_listing_complete"] is False
    assert detail["_private_document_source_ids"] == [10]
    assert failures == []


def test_conflicting_per_request_document_visibility_preserves_current_files():
    from nextrequest_scraper import get_request_detail

    failures = []
    conflicting_document = {
        "id": 10,
        "visibility": "Published",
        "state": "Private",
        "title": "response.pdf",
    }
    with patch(
        "nextrequest_scraper._fetch_request_detail",
        return_value=SAMPLE_DETAIL_RESPONSE,
    ), patch(
        "nextrequest_scraper._fetch_request_timeline",
        return_value=SAMPLE_TIMELINE_RESPONSE,
    ), patch(
        "nextrequest_scraper.http_client.get",
        return_value=_response({
            "total_documents_count": 1,
            "documents": [conflicting_document],
            "documents_state_timestamp": 100,
        }),
    ):
        detail = get_request_detail(
            "26-042",
            include_documents=True,
            failure_sink=failures,
        )

    assert detail["documents"] == []
    assert detail["_documents_listing_observed"] is False
    assert detail["_documents_listing_complete"] is False
    assert failures[0]["stage"] == "documents"
    assert "visibility" in failures[0]["error"]


def test_document_pagination_state_change_fails_closed():
    from nextrequest_scraper import _fetch_request_documents_with_state

    page_one = {
        "total_documents_count": 2,
        "documents_state_timestamp": 100,
        "documents": [{"id": 10, "visibility": "Published"}],
    }
    page_two = {
        "total_documents_count": 2,
        "documents_state_timestamp": 101,
        "documents": [{"id": 11, "visibility": "Published"}],
    }
    with patch(
        "nextrequest_scraper.http_client.get",
        side_effect=[_response(page_one), _response(page_two)],
    ), patch("nextrequest_scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="changed during pagination"):
            _fetch_request_documents_with_state("26-042")


def test_repeated_per_request_document_id_is_not_complete_coverage():
    from nextrequest_scraper import _fetch_request_documents_with_state

    response = {
        "total_documents_count": 2,
        "documents_state_timestamp": 100,
        "documents": [
            {"id": 10, "visibility": "Published"},
            {"id": 10, "visibility": "Published"},
        ],
    }
    with patch(
        "nextrequest_scraper.http_client.get",
        return_value=_response(response),
    ):
        with pytest.raises(RuntimeError, match="repeated an ID"):
            _fetch_request_documents_with_state("26-042")


def test_small_live_request_baseline_still_blocks_destructive_shrink():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (4, 2)
    results = {
        "request_listing_complete": True,
        "authoritative_request_numbers": ["26-001", "26-002"],
        "requests": [],
    }

    with pytest.raises(RuntimeError, match="request shrink"):
        save_to_db(conn, results, "0660620")
    conn.commit.assert_not_called()


def test_small_live_document_baseline_still_blocks_destructive_shrink():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (4, 2)
    results = {
        "public_document_listing_complete": True,
        "authoritative_public_document_ids": [10, 11],
        "requests": [],
    }

    with pytest.raises(RuntimeError, match="document shrink"):
        save_to_db(conn, results, "0660620")
    conn.commit.assert_not_called()


def test_same_size_rekeyed_snapshot_cannot_mass_tombstone_live_documents():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    # Incoming cardinality can match the live corpus while sharing no IDs.
    # The overlap proof, not source-reported size alone, gates reconciliation.
    cursor.fetchone.return_value = (2, 0)
    results = {
        "public_document_listing_complete": True,
        "authoritative_public_document_ids": [900, 901],
        "requests": [],
    }

    with pytest.raises(RuntimeError, match="document shrink"):
        save_to_db(conn, results, "0660620")
    conn.commit.assert_not_called()


def test_global_document_reconciliation_never_retires_legacy_null_ids():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (2, 2)
    results = {
        "public_document_listing_complete": True,
        "authoritative_public_document_ids": [10, 11],
        "requests": [],
    }

    save_to_db(conn, results, "0660620")

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    global_update = next(
        sql for sql in sql_statements
        if "UPDATE nextrequest_documents d" in sql
    )
    assert "d.source_document_id IS NOT NULL" in global_update
    assert "source_document_id IS NULL" not in global_update


def test_per_request_legacy_retirement_requires_explicit_complete_proof():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [("request-id", True), (True,)]
    results = {
        "requests": [{
            "request_number": "26-042",
            "status": "Closed",
            "documents": [{
                "source_document_id": 10,
                "filename": "response.pdf",
            }],
            "_incomplete_stages": ["documents"],
        }],
    }

    save_to_db(conn, results, "0660620")

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any("source_document_id IS NULL" in sql for sql in sql_statements)


def test_per_request_complete_reconciliation_reinserts_before_retiring_legacy():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [("request-id", True), (True,)]
    results = {
        "requests": [{
            "request_number": "26-042",
            "status": "Closed",
            "documents": [{
                "source_document_id": 10,
                "filename": "response.pdf",
            }],
            "_documents_listing_observed": True,
            "_documents_listing_complete": True,
            "_incomplete_stages": [],
        }],
    }

    save_to_db(conn, results, "0660620")

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    document_upsert_index = next(
        index for index, sql in enumerate(sql_statements)
        if "INSERT INTO nextrequest_documents" in sql
    )
    legacy_retirement_index = next(
        index for index, sql in enumerate(sql_statements)
        if "source_document_id IS NULL" in sql
    )
    assert document_upsert_index < legacy_retirement_index


def test_filtered_private_ids_retire_only_exact_managed_rows():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("request-id", True)
    cursor.rowcount = 1
    results = {
        "requests": [{
            "request_number": "26-042",
            "status": "Closed",
            "documents": [],
            "_documents_listing_observed": True,
            "_documents_listing_complete": False,
            "_private_document_source_ids": [10],
            "_incomplete_stages": [],
        }],
    }

    save_to_db(conn, results, "0660620")

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    private_update = next(
        sql for sql in sql_statements
        if "source_document_id = ANY" in sql
    )
    assert "source_document_id IS NULL" not in private_update
    assert not any("source_document_id IS NULL" in sql for sql in sql_statements)


def test_explicit_private_request_tombstones_parent_and_children():
    from nextrequest_scraper import save_to_db

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("request-id",)
    cursor.rowcount = 2
    results = {
        "requests": [{
            "request_number": "26-042",
            "_source_nonpublic": True,
        }],
    }

    stats = save_to_db(conn, results, "0660620")

    sql = "\n".join(
        call.args[0] for call in cursor.execute.call_args_list
    )
    assert "UPDATE nextrequest_requests" in sql
    assert "UPDATE nextrequest_documents" in sql
    assert stats["requests_tombstoned"] == 1
    assert stats["documents_tombstoned"] == 2


def test_every_public_record_query_excludes_removed_requests():
    query_path = (
        Path(__file__).resolve().parents[1]
        / "web" / "src" / "lib" / "queries" / "public_records.ts"
    )
    source = query_path.read_text(encoding="utf-8")

    query_count = source.count(".from('nextrequest_requests')")
    assert query_count > 0
    assert source.count(".is('source_removed_at', null)") == query_count
