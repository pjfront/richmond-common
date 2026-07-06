"""Tests for apify_sos_client.py — Apify CA SOS entity resolution client."""

import json
import pytest
from unittest import mock

# Module under test imports from opencorporates_client, which needs env setup.
# Patch before importing.
with mock.patch.dict("os.environ", {"APIFY_API_TOKEN": "test-token"}):
    from apify_sos_client import (
        run_sos_search,
        is_found,
        normalize_result,
        match_entity,
        format_cost_estimate,
    )


# ── Sample Apify responses ─────────────────────────────────────

FOUND_RESULT = {
    "entityName": "CHEVRON CORPORATION",
    "entityNumber": "117531",
    "url": "https://bizfileonline.sos.ca.gov/search/business",
    "searchTerm": "Chevron Corporation",
    "entityType": "Stock Corporation - Out of State - Stock",
    "status": "Active",
    "riskLevel": "low",
    "formationDate": "02/02/1926",
    "registeredAgent": "1505 Corporation",
    "principalAddress": "1400 SMITH STREET, HOUSTON, TX 77002",
    "signals": [
        {
            "type": "entity_active",
            "severity": "low",
            "description": 'Entity status is "Active"',
        }
    ],
    "scrapedAt": "2026-07-06T18:37:31.739Z",
}

NOT_FOUND_RESULT = {
    "entityName": None,
    "entityNumber": None,
    "url": None,
    "searchTerm": "SEIU Local 1021",
    "entityType": None,
    "status": None,
    "riskLevel": "medium",
    "formationDate": None,
    "registeredAgent": None,
    "principalAddress": None,
    "signals": [
        {
            "type": "not_found",
            "severity": "medium",
            "description": 'No business entity found for "SEIU Local 1021"',
        }
    ],
    "scrapedAt": "2026-07-06T18:39:10.024Z",
}


# ── is_found ────────────────────────────────────────────────────

def test_is_found_returns_true_for_valid_result():
    assert is_found(FOUND_RESULT) is True


def test_is_found_returns_false_for_null_entity_name():
    assert is_found(NOT_FOUND_RESULT) is False


def test_is_found_returns_false_for_not_found_signal():
    item = dict(FOUND_RESULT)
    item["signals"] = [{"type": "not_found", "severity": "medium"}]
    assert is_found(item) is False


# ── normalize_result ────────────────────────────────────────────

def test_normalize_result_maps_core_fields():
    result = normalize_result(FOUND_RESULT)
    assert result["entity_name"] == "CHEVRON CORPORATION"
    assert result["entity_number"] == "117531"
    assert result["entity_type"] == "Stock Corporation - Out of State - Stock"
    assert result["current_status"] == "Active"
    assert result["agent_name"] == "1505 Corporation"
    assert result["registered_address"] == "1400 SMITH STREET, HOUSTON, TX 77002"
    assert result["source_publisher"] == "California Secretary of State"
    assert result["jurisdiction_code"] == "us_ca"
    assert result["confidence_score"] == 0.95


def test_normalize_result_parses_formation_date():
    result = normalize_result(FOUND_RESULT)
    assert result["incorporation_date"] == "1926-02-02"


def test_normalize_result_includes_raw_response():
    result = normalize_result(FOUND_RESULT)
    raw = json.loads(result["raw_response"])
    assert raw["entityName"] == "CHEVRON CORPORATION"


def test_normalize_result_constructs_source_url():
    result = normalize_result(FOUND_RESULT)
    assert "117531" in result["source_url"]
    assert "bizfileonline.sos.ca.gov" in result["source_url"]


def test_normalize_result_handles_minimal_result():
    minimal = {"entityName": "Test Corp", "entityNumber": "123"}
    result = normalize_result(minimal)
    assert result["entity_name"] == "Test Corp"
    assert result["entity_number"] == "123"
    assert result["source_publisher"] == "California Secretary of State"  # always set


# ── match_entity ────────────────────────────────────────────────

def test_match_entity_exact_chevron():
    result, confidence, method = match_entity(
        [FOUND_RESULT], "Chevron Corporation",
    )
    assert result is not None
    assert confidence == 0.95
    assert method == "exact"
    assert result["entity_number"] == "117531"


def test_match_entity_skips_not_found():
    result, confidence, method = match_entity(
        [NOT_FOUND_RESULT], "SEIU Local 1021",
    )
    assert result is None
    assert method == "none"


def test_match_entity_fuzzy_similar_name():
    similar = dict(FOUND_RESULT)
    similar["entityName"] = "CHEVRON CORPORATION"  # same as before
    result, confidence, method = match_entity(
        [similar], "Chevron Corp",  # abbreviated
    )
    # "Chevron Corporation" vs "Chevron Corp" — after normalization both
    # become something like "CHEVRON", so this might be exact or very high fuzzy
    assert result is not None
    assert confidence >= 0.80


def test_match_entity_below_threshold():
    unrelated = dict(FOUND_RESULT)
    unrelated["entityName"] = "CHEVRON CORPORATION"
    result, confidence, method = match_entity(
        [unrelated], "XYZ Unrelated Services LLC", threshold=0.80,
    )
    # Should be below threshold or "none"
    if result is not None:
        assert method == "fuzzy"
        assert confidence < 0.80
    else:
        assert method == "none"


def test_match_entity_custom_threshold():
    result, confidence, method = match_entity(
        [FOUND_RESULT], "Chevron Corporation", threshold=0.99,
    )
    assert result is not None
    assert method == "exact"
    assert confidence == 0.95


# ── format_cost_estimate ────────────────────────────────────────

def test_format_cost_estimate():
    s = format_cost_estimate(100)
    assert "~$0.80" in s
    assert "100 results" in s


def test_format_cost_estimate_zero():
    s = format_cost_estimate(0)
    assert "~$0.00" in s


# ── run_sos_search (mocked) ─────────────────────────────────────

@mock.patch("apify_sos_client.requests.post")
def test_run_sos_search_success(mock_post):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [FOUND_RESULT]
    mock_post.return_value = mock_response

    with mock.patch.dict("os.environ", {"APIFY_API_TOKEN": "test-token"}):
        results = run_sos_search(["Chevron Corporation"], max_items=5)
    assert len(results) == 1
    assert results[0]["entityName"] == "CHEVRON CORPORATION"
    # Verify URL and headers in the POST
    call_args = mock_post.call_args
    assert "parseforge~sos-scraper" in str(call_args)


@mock.patch("apify_sos_client.requests.post")
def test_run_sos_search_401(mock_post):
    mock_response = mock.Mock()
    mock_response.status_code = 401
    mock_post.return_value = mock_response

    with mock.patch.dict("os.environ", {"APIFY_API_TOKEN": "test-token"}):
        results = run_sos_search(["Chevron Corporation"])
    assert results == []


@mock.patch("apify_sos_client.requests.post")
def test_run_sos_search_empty_input(mock_post):
    results = run_sos_search([])
    assert results == []
    mock_post.assert_not_called()
