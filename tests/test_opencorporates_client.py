"""Tests for OpenCorporates business entity resolution client.

Covers: name normalization, entity detection, token similarity,
API response parsing, rate limiting, search/detail/officer methods,
and the high-level resolve_entity pipeline.

All tests use mocked API responses — no real API calls.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from opencorporates_client import (
    normalize_entity_name,
    looks_like_entity,
    token_similarity,
    search_company,
    get_company,
    search_officers,
    resolve_entity,
    RateLimitTracker,
    CompanySearchResult,
    CompanyDetail,
    OfficerRecord,
    EntityResolution,
    _parse_company,
    _parse_officer,
)


# --- Fixtures: Mock API Responses ---

MOCK_COMPANY_SEARCH_RESPONSE = {
    "results": {
        "companies": [
            {
                "company": {
                    "name": "CHEVRONTEXACO CORPORATION",
                    "company_number": "C0186725",
                    "jurisdiction_code": "us_ca",
                    "company_type": "Domestic Stock",
                    "current_status": "Active",
                    "incorporation_date": "1926-10-27",
                    "dissolution_date": None,
                    "registered_address_in_full": "6001 BOLLINGER CANYON RD, SAN RAMON, CA 94583",
                    "opencorporates_url": "https://opencorporates.com/companies/us_ca/C0186725",
                    "source": {
                        "publisher": "California Secretary of State",
                        "retrieved_at": "2025-12-15T00:00:00+00:00",
                    },
                }
            },
            {
                "company": {
                    "name": "CHEVRONTEXACO FUNDING CORPORATION",
                    "company_number": "C2476383",
                    "jurisdiction_code": "us_ca",
                    "company_type": "Domestic Stock",
                    "current_status": "Active",
                    "incorporation_date": "2002-09-25",
                    "dissolution_date": None,
                    "registered_address_in_full": "6001 BOLLINGER CANYON RD, SAN RAMON, CA 94583",
                    "opencorporates_url": "https://opencorporates.com/companies/us_ca/C2476383",
                    "source": {
                        "publisher": "California Secretary of State",
                        "retrieved_at": "2025-12-15T00:00:00+00:00",
                    },
                }
            },
        ]
    }
}

MOCK_COMPANY_DETAIL_RESPONSE = {
    "results": {
        "company": {
            "name": "CHEVRONTEXACO CORPORATION",
            "company_number": "C0186725",
            "jurisdiction_code": "us_ca",
            "company_type": "Domestic Stock",
            "current_status": "Active",
            "incorporation_date": "1926-10-27",
            "dissolution_date": None,
            "registered_address_in_full": "6001 BOLLINGER CANYON RD, SAN RAMON, CA 94583",
            "opencorporates_url": "https://opencorporates.com/companies/us_ca/C0186725",
            "agent_name": "CT CORPORATION SYSTEM",
            "agent_address": "818 WEST SEVENTH STREET, LOS ANGELES, CA 90017",
            "officers": [
                {
                    "officer": {
                        "name": "JOHN DOE",
                        "position": "director",
                        "start_date": "2020-01-15",
                        "end_date": None,
                        "inactive": False,
                        "id": 12345,
                    }
                },
                {
                    "officer": {
                        "name": "JANE SMITH",
                        "position": "chief executive officer",
                        "start_date": "2019-06-01",
                        "end_date": None,
                        "inactive": False,
                        "id": 12346,
                    }
                },
            ],
            "previous_names": [
                {"company_name": "CHEVRON CORPORATION", "con_date": "2001-10-09"},
            ],
            "source": {
                "publisher": "California Secretary of State",
                "retrieved_at": "2025-12-15T00:00:00+00:00",
            },
        }
    }
}

MOCK_OFFICER_SEARCH_RESPONSE = {
    "results": {
        "officers": [
            {
                "officer": {
                    "name": "JOHN DOE",
                    "position": "director",
                    "start_date": "2020-01-15",
                    "end_date": None,
                    "inactive": False,
                    "id": 12345,
                    "company": {
                        "name": "CHEVRONTEXACO CORPORATION",
                        "company_number": "C0186725",
                        "jurisdiction_code": "us_ca",
                    },
                }
            }
        ]
    }
}


# =====================================================
# Name Normalization Tests
# =====================================================

class TestNormalizeEntityName:
    def test_strips_llc_suffix(self):
        assert normalize_entity_name("JIA Investments, LLC") == "JIA INVESTMENTS"

    def test_strips_inc_suffix(self):
        assert normalize_entity_name("Holistic Healing Collective, Inc.") == "HOLISTIC HEALING COLLECTIVE"

    def test_strips_corp_suffix(self):
        assert normalize_entity_name("ChevronTexaco Corporation") == "CHEVRONTEXACO"

    def test_strips_llp_suffix(self):
        assert normalize_entity_name("Reed & Davidson, LLP") == "REED & DAVIDSON"

    def test_strips_lp_suffix(self):
        assert normalize_entity_name("EBJ PARTNERS, LP") == "EBJ PARTNERS"

    def test_strips_company_suffix(self):
        assert normalize_entity_name("ConocoPhillips Company") == "CONOCOPHILLIPS"

    def test_normalizes_whitespace(self):
        assert normalize_entity_name("  ABC   Construction   ") == "ABC CONSTRUCTION"

    def test_removes_punctuation(self):
        assert normalize_entity_name("S.E. Owens & Company") == "S E OWENS &"

    def test_uppercases(self):
        assert normalize_entity_name("acme corp") == "ACME"

    def test_empty_after_strip_returns_original(self):
        # If stripping suffix leaves nothing, return original stripped
        result = normalize_entity_name("LLC")
        assert result  # Should not be empty

    def test_dedup_variants_match(self):
        """Key test: variants of the same entity should normalize identically."""
        assert normalize_entity_name("JIA Investments, LLC") == normalize_entity_name("JIA Investments LLC")
        assert normalize_entity_name("Holistic Healing Collective, Inc.") == normalize_entity_name("Holistic Healing Collective Inc.")
        assert normalize_entity_name("Richmond Development Company, LLC") == normalize_entity_name("Richmond Development Company LLC")
        assert normalize_entity_name("Davillier-Sloan, Inc.") == normalize_entity_name("Davillier Sloan Inc")


class TestLooksLikeEntity:
    def test_llc(self):
        assert looks_like_entity("JIA Investments, LLC")

    def test_inc(self):
        assert looks_like_entity("RYSE, Inc.")

    def test_corporation(self):
        assert looks_like_entity("ChevronTexaco Corporation")

    def test_llp(self):
        assert looks_like_entity("Reed & Davidson, LLP")

    def test_delaware_llc(self):
        assert looks_like_entity("Eastshore Properties, A Delaware LLC")

    def test_person_name(self):
        assert not looks_like_entity("John Smith")

    def test_union(self):
        assert not looks_like_entity("SEIU Local 1021")

    def test_association(self):
        assert not looks_like_entity("Richmond Police Officers Association")


class TestTokenSimilarity:
    def test_identical(self):
        assert token_similarity("ABC Corp", "ABC Corp") == 1.0

    def test_same_after_normalization(self):
        score = token_similarity("JIA Investments, LLC", "JIA Investments LLC")
        assert score == 1.0

    def test_partial_overlap(self):
        score = token_similarity("ABC Construction", "ABC Construction Services")
        assert 0.5 < score < 1.0

    def test_no_overlap(self):
        score = token_similarity("ABC Corp", "XYZ Ltd")
        assert score == 0.0

    def test_empty(self):
        score = token_similarity("", "ABC Corp")
        assert score == 0.0


# =====================================================
# API Response Parsing Tests
# =====================================================

class TestParseCompany:
    def test_parses_search_result(self):
        data = MOCK_COMPANY_SEARCH_RESPONSE["results"]["companies"][0]["company"]
        result = _parse_company(data)
        assert result.name == "CHEVRONTEXACO CORPORATION"
        assert result.company_number == "C0186725"
        assert result.jurisdiction_code == "us_ca"
        assert result.company_type == "Domestic Stock"
        assert result.current_status == "Active"
        assert result.source_publisher == "California Secretary of State"

    def test_handles_missing_source(self):
        data = {"name": "Test", "jurisdiction_code": "us_ca"}
        result = _parse_company(data)
        assert result.name == "Test"
        assert result.source_publisher is None


class TestParseOfficer:
    def test_parses_officer(self):
        data = MOCK_OFFICER_SEARCH_RESPONSE["results"]["officers"][0]["officer"]
        result = _parse_officer(data)
        assert result.name == "JOHN DOE"
        assert result.position == "director"
        assert result.company_name == "CHEVRONTEXACO CORPORATION"
        assert result.company_number == "C0186725"
        assert result.is_inactive is False


# =====================================================
# Rate Limiter Tests
# =====================================================

class TestRateLimitTracker:
    def test_allows_when_under_limit(self):
        tracker = RateLimitTracker(daily_limit=50, monthly_limit=200)
        allowed, reason = tracker.can_call()
        assert allowed is True

    def test_blocks_at_daily_limit(self):
        tracker = RateLimitTracker(daily_limit=3, monthly_limit=200)
        for _ in range(3):
            tracker.record_call("test")
        allowed, reason = tracker.can_call()
        assert allowed is False
        assert "Daily" in reason

    def test_blocks_at_monthly_limit(self):
        tracker = RateLimitTracker(daily_limit=50, monthly_limit=3)
        for _ in range(3):
            tracker.record_call("test")
        allowed, reason = tracker.can_call()
        assert allowed is False
        assert "Monthly" in reason

    def test_budget_status_format(self):
        tracker = RateLimitTracker(daily_limit=50, monthly_limit=200)
        tracker.record_call("test")
        status = tracker.budget_status()
        assert "1/50 daily" in status
        assert "1/200 monthly" in status

    def test_usage_counts(self):
        tracker = RateLimitTracker()
        tracker.record_call("companies/search")
        tracker.record_call("companies/search")
        daily, monthly = tracker.get_usage()
        assert daily == 2
        assert monthly == 2


# =====================================================
# API Method Tests (Mocked)
# =====================================================

class TestSearchCompany:
    @patch("opencorporates_client._api_get")
    def test_returns_results(self, mock_get):
        mock_get.return_value = MOCK_COMPANY_SEARCH_RESPONSE
        results = search_company("ChevronTexaco")
        assert len(results) == 2
        assert results[0].name == "CHEVRONTEXACO CORPORATION"
        assert results[0].company_number == "C0186725"

    @patch("opencorporates_client._api_get")
    def test_returns_empty_on_none(self, mock_get):
        mock_get.return_value = None
        results = search_company("NonexistentCorp")
        assert results == []

    @patch("opencorporates_client._api_get")
    def test_passes_jurisdiction(self, mock_get):
        mock_get.return_value = {"results": {"companies": []}}
        search_company("Test", jurisdiction="us_tx")
        call_params = mock_get.call_args[1].get("params") or mock_get.call_args[0][1]
        assert call_params["jurisdiction_code"] == "us_tx"


class TestGetCompany:
    @patch("opencorporates_client._api_get")
    def test_returns_detail(self, mock_get):
        mock_get.return_value = MOCK_COMPANY_DETAIL_RESPONSE
        detail = get_company("C0186725")
        assert detail is not None
        assert detail.name == "CHEVRONTEXACO CORPORATION"
        assert detail.agent_name == "CT CORPORATION SYSTEM"
        assert len(detail.officers) == 2
        assert detail.officers[0].name == "JOHN DOE"
        assert detail.officers[1].position == "chief executive officer"

    @patch("opencorporates_client._api_get")
    def test_returns_none_on_not_found(self, mock_get):
        mock_get.return_value = None
        detail = get_company("INVALID")
        assert detail is None


class TestSearchOfficers:
    @patch("opencorporates_client._api_get")
    def test_returns_officers(self, mock_get):
        mock_get.return_value = MOCK_OFFICER_SEARCH_RESPONSE
        results = search_officers("John Doe")
        assert len(results) == 1
        assert results[0].name == "JOHN DOE"
        assert results[0].company_name == "CHEVRONTEXACO CORPORATION"

    @patch("opencorporates_client._api_get")
    def test_returns_empty_on_none(self, mock_get):
        mock_get.return_value = None
        results = search_officers("Nobody")
        assert results == []


# =====================================================
# Resolve Entity Tests (Full Pipeline)
# =====================================================

class TestResolveEntity:
    @patch("opencorporates_client.get_company")
    @patch("opencorporates_client.search_company")
    def test_exact_match(self, mock_search, mock_detail):
        mock_search.return_value = [
            CompanySearchResult(
                name="CHEVRONTEXACO CORPORATION",
                company_number="C0186725",
                jurisdiction_code="us_ca",
                company_type="Domestic Stock",
                current_status="Active",
                incorporation_date="1926-10-27",
                dissolution_date=None,
                registered_address=None,
                opencorporates_url="https://opencorporates.com/companies/us_ca/C0186725",
            ),
        ]
        mock_detail.return_value = CompanyDetail(
            name="CHEVRONTEXACO CORPORATION",
            company_number="C0186725",
            jurisdiction_code="us_ca",
            company_type="Domestic Stock",
            current_status="Active",
            incorporation_date="1926-10-27",
            dissolution_date=None,
            registered_address=None,
            opencorporates_url="https://opencorporates.com/companies/us_ca/C0186725",
            agent_name="CT CORPORATION SYSTEM",
            officers=[],
        )

        result = resolve_entity("ChevronTexaco Corporation")
        assert result.matched is True
        assert result.confidence == 0.95
        assert result.match_method == "exact"
        assert result.company.company_number == "C0186725"

    @patch("opencorporates_client.search_company")
    def test_no_match(self, mock_search):
        mock_search.return_value = []
        result = resolve_entity("Totally Fake Company LLC")
        assert result.matched is False

    @patch("opencorporates_client.search_company")
    def test_low_confidence_no_match(self, mock_search):
        mock_search.return_value = [
            CompanySearchResult(
                name="COMPLETELY DIFFERENT NAME INC",
                company_number="C9999999",
                jurisdiction_code="us_ca",
                company_type=None,
                current_status=None,
                incorporation_date=None,
                dissolution_date=None,
                registered_address=None,
                opencorporates_url=None,
            ),
        ]
        result = resolve_entity("ABC Construction LLC")
        assert result.matched is False
        assert result.confidence < 0.50

    @patch("opencorporates_client.get_company")
    @patch("opencorporates_client.search_company")
    def test_fuzzy_match_above_threshold(self, mock_search, mock_detail):
        mock_search.return_value = [
            CompanySearchResult(
                name="JIA INVESTMENTS LLC",
                company_number="C1234567",
                jurisdiction_code="us_ca",
                company_type="Domestic LLC",
                current_status="Active",
                incorporation_date=None,
                dissolution_date=None,
                registered_address=None,
                opencorporates_url=None,
            ),
        ]
        mock_detail.return_value = CompanyDetail(
            name="JIA INVESTMENTS LLC",
            company_number="C1234567",
            jurisdiction_code="us_ca",
            company_type="Domestic LLC",
            current_status="Active",
            incorporation_date=None,
            dissolution_date=None,
            registered_address=None,
            opencorporates_url=None,
            officers=[],
        )

        # "JIA Investments, LLC" vs "JIA INVESTMENTS LLC" — should match
        result = resolve_entity("JIA Investments, LLC")
        assert result.matched is True
        assert result.confidence >= 0.80

    @patch("opencorporates_client.search_company")
    def test_rate_limit_respected(self, mock_search):
        tracker = RateLimitTracker(daily_limit=0, monthly_limit=0)
        mock_search.return_value = []  # Won't be called anyway

        result = resolve_entity("Test Corp", rate_tracker=tracker)
        # Should still work but with no API results (rate limited)
        assert result.matched is False


# =====================================================
# Integration: Name Dedup Validation
# =====================================================

class TestEntityNameDedup:
    """Validates that known duplicate entity names from NetFile data
    normalize to the same value and would produce high similarity scores."""

    KNOWN_DUPES = [
        ("JIA Investments, LLC", "JIA Investments LLC"),
        ("Holistic Healing Collective, Inc.", "Holistic Healing Collective Inc."),
        ("Richmond Development Company, LLC", "Richmond Development Company LLC"),
        ("Davillier-Sloan, Inc.", "Davillier Sloan Inc"),
        ("AWIN Management Inc.", "LE03-AWIN Management Inc"),
    ]

    @pytest.mark.parametrize("name_a,name_b", KNOWN_DUPES[:4])
    def test_exact_normalization_match(self, name_a, name_b):
        """These pairs should normalize to identical strings."""
        assert normalize_entity_name(name_a) == normalize_entity_name(name_b)

    def test_awin_partial_match(self):
        """AWIN variants have a prefix difference — should still score high."""
        score = token_similarity("AWIN Management Inc.", "LE03-AWIN Management Inc")
        assert score >= 0.50  # Partial overlap due to LE03 prefix
