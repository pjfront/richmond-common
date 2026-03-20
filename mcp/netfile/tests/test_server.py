"""Tests for the MCP server tool functions.

Tests the tool functions directly as regular Python functions.
HTTP calls are mocked — no live API traffic.
"""
from unittest.mock import MagicMock, patch

import pytest

from netfile_mcp.server import (
    get_committee_info,
    list_agencies,
    list_transaction_types,
    lookup_city,
    search_contributions,
)

MOCK_TRANSACTIONS = [
    {
        "id": "tx-001",
        "name": "Jane Doe",
        "employer": "Acme Corp",
        "occupation": "Engineer",
        "amount": 500.00,
        "date": "2024-06-15T00:00:00",
        "city": "Richmond",
        "state": "CA",
        "zip": "94801",
        "filerName": "Martinez for Mayor 2022",
        "transactionType": 0,
        "filerFppcId": "1401234",
        "filerLocalId": "LOC-001",
        "filingId": "FIL-100",
    },
    {
        "id": "tx-002",
        "name": "Bob Builder",
        "employer": "Construction Co",
        "occupation": "Contractor",
        "amount": 1000.00,
        "date": "2024-07-01T00:00:00",
        "city": "Richmond",
        "state": "CA",
        "zip": "94801",
        "filerName": "Martinez for Mayor 2022",
        "transactionType": 0,
        "filerFppcId": "1401234",
        "filerLocalId": "LOC-001",
        "filingId": "FIL-101",
    },
]


class TestLookupCity:
    def test_finds_richmond(self):
        result = lookup_city(query="Richmond")
        assert result["matches"] >= 1
        assert any(r["id"] == 163 for r in result["results"])

    def test_no_results(self):
        result = lookup_city(query="Zzzyxville Nonexistent")
        assert result["matches"] == 0

    def test_shortcut_lookup(self):
        result = lookup_city(query="RICH")
        assert result["matches"] >= 1
        assert result["results"][0]["id"] == 163


class TestListTransactionTypes:
    def test_returns_types(self):
        result = list_transaction_types()
        assert "contribution_types" in result
        assert "expenditure_types" in result
        assert "descriptions" in result
        assert "0" in result["contribution_types"]


class TestListAgencies:
    @patch("netfile_mcp.server._get_agencies_raw")
    def test_returns_agencies(self, mock_get):
        mock_get.return_value = [
            {"id": 163, "shortcut": "RICH", "name": "City of Richmond"},
            {"id": 44, "shortcut": "OAK", "name": "City of Oakland"},
        ]
        result = list_agencies()
        assert result["count"] == 2
        assert len(result["agencies"]) == 2


class TestSearchContributions:
    @patch("netfile_mcp.server.fetch_all_transactions")
    def test_search_by_agency_id(self, mock_fetch):
        mock_fetch.return_value = (MOCK_TRANSACTIONS, 2)

        result = search_contributions(agency_id=163, limit=10)
        assert "error" not in result
        assert result["agency"]["id"] == 163
        assert result["returned"] == 2
        assert result["summary"]["total_amount"] == 1500.00
        assert result["summary"]["unique_donors"] == 2

    @patch("netfile_mcp.server.fetch_all_transactions")
    def test_strips_internal_ids(self, mock_fetch):
        mock_fetch.return_value = (MOCK_TRANSACTIONS, 2)

        result = search_contributions(agency_id=163)
        for c in result["contributions"]:
            assert "filing_id" not in c
            assert "transaction_id" not in c
            assert "filer_fppc_id" not in c

    @patch("netfile_mcp.server.fetch_all_transactions")
    def test_limit_caps_output(self, mock_fetch):
        mock_fetch.return_value = (MOCK_TRANSACTIONS, 2)

        result = search_contributions(agency_id=163, limit=1)
        assert result["returned"] == 1
        assert result["total_available"] == 2  # Full count still reported

    def test_no_inputs_returns_error(self):
        result = search_contributions()
        assert "error" in result

    @patch("netfile_mcp.server.fetch_all_transactions")
    def test_amount_max_filter(self, mock_fetch):
        mock_fetch.return_value = (MOCK_TRANSACTIONS, 2)

        result = search_contributions(agency_id=163, amount_max=600.0)
        assert result["total_available"] == 1  # Only the $500 contribution


class TestGetCommitteeInfo:
    @patch("netfile_mcp.server.fetch_all_transactions")
    def test_returns_committees(self, mock_fetch):
        mock_fetch.return_value = (MOCK_TRANSACTIONS, 2)

        result = get_committee_info(agency_id=163)
        assert "error" not in result
        assert result["committee_count"] >= 1
        assert any(c["fppc_id"] == "1401234" for c in result["committees"])

    def test_no_inputs_returns_error(self):
        result = get_committee_info()
        assert "error" in result
