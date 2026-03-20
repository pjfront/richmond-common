"""Tests for the standalone NetFile API client.

All tests use mocked HTTP responses — no live API calls.
"""
from unittest.mock import MagicMock, patch

import pytest

from netfile_mcp.client import (
    ALL_TYPES,
    CONTRIBUTION_TYPES,
    EXPENDITURE_TYPES,
    deduplicate_contributions,
    extract_filers,
    normalize_transaction,
)


# --- Fixtures ---

SAMPLE_RAW_TRANSACTION = {
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
}

SAMPLE_RAW_TRANSACTION_2 = {
    "id": "tx-002",
    "name": "John Smith",
    "employer": "City Hospital",
    "occupation": "Doctor",
    "amount": 250.00,
    "date": "2024-07-20T00:00:00",
    "city": "El Cerrito",
    "state": "CA",
    "zip": "94530",
    "filerName": "Willis for Council 2024",
    "transactionType": 1,
    "filerFppcId": "1401999",
    "filerLocalId": "LOC-002",
    "filingId": "FIL-200",
}


class TestNormalizeTransaction:
    def test_basic_normalization(self):
        result = normalize_transaction(SAMPLE_RAW_TRANSACTION)
        assert result["contributor_name"] == "Jane Doe"
        assert result["contributor_employer"] == "Acme Corp"
        assert result["amount"] == 500.00
        assert result["date"] == "2024-06-15"  # Truncated from ISO datetime
        assert result["committee"] == "Martinez for Mayor 2022"
        assert result["transaction_type"] == "F460A"
        assert result["source"] == "netfile"

    def test_null_safe_fields(self):
        tx = {"id": "tx-null", "amount": 100}
        result = normalize_transaction(tx)
        assert result["contributor_name"] == ""
        assert result["contributor_employer"] == ""
        assert result["committee"] == ""
        assert result["date"] == ""

    def test_strips_whitespace(self):
        tx = {**SAMPLE_RAW_TRANSACTION, "name": "  Jane Doe  ", "employer": " Acme "}
        result = normalize_transaction(tx)
        assert result["contributor_name"] == "Jane Doe"
        assert result["contributor_employer"] == "Acme"

    def test_unknown_transaction_type(self):
        tx = {**SAMPLE_RAW_TRANSACTION, "transactionType": 999}
        result = normalize_transaction(tx)
        assert result["transaction_type"] == "unknown"


class TestDeduplicateContributions:
    def test_no_duplicates(self):
        contributions = [
            normalize_transaction(SAMPLE_RAW_TRANSACTION),
            normalize_transaction(SAMPLE_RAW_TRANSACTION_2),
        ]
        result = deduplicate_contributions(contributions)
        assert len(result) == 2

    def test_removes_amended_filing_duplicate(self):
        original = normalize_transaction(SAMPLE_RAW_TRANSACTION)
        amended = {**original, "filing_id": "FIL-200"}  # Higher filing ID
        contributions = [original, amended]
        result = deduplicate_contributions(contributions)
        assert len(result) == 1
        assert result[0]["filing_id"] == "FIL-200"  # Keeps most recent

    def test_case_insensitive_dedup(self):
        c1 = normalize_transaction(SAMPLE_RAW_TRANSACTION)
        c2 = {**c1, "contributor_name": "JANE DOE", "filing_id": "FIL-050"}
        contributions = [c1, c2]
        result = deduplicate_contributions(contributions)
        assert len(result) == 1
        assert result[0]["filing_id"] == "FIL-100"  # Original has higher filing_id


class TestExtractFilers:
    def test_extracts_unique_filers(self):
        contributions = [
            normalize_transaction(SAMPLE_RAW_TRANSACTION),
            normalize_transaction(SAMPLE_RAW_TRANSACTION_2),
        ]
        filers = extract_filers(contributions)
        assert len(filers) == 2
        fppc_ids = {f["fppc_id"] for f in filers}
        assert "1401234" in fppc_ids
        assert "1401999" in fppc_ids

    def test_deduplicates_same_filer(self):
        contributions = [
            normalize_transaction(SAMPLE_RAW_TRANSACTION),
            normalize_transaction(SAMPLE_RAW_TRANSACTION),  # Same filer
        ]
        filers = extract_filers(contributions)
        assert len(filers) == 1

    def test_skips_empty_fppc_id(self):
        tx = {**SAMPLE_RAW_TRANSACTION, "filerFppcId": ""}
        contributions = [normalize_transaction(tx)]
        filers = extract_filers(contributions)
        assert len(filers) == 0


class TestConstants:
    def test_contribution_types_present(self):
        assert 0 in CONTRIBUTION_TYPES  # F460A
        assert 1 in CONTRIBUTION_TYPES  # F460C

    def test_expenditure_types_present(self):
        assert 6 in EXPENDITURE_TYPES  # F460E

    def test_all_types_is_union(self):
        assert ALL_TYPES == {**CONTRIBUTION_TYPES, **EXPENDITURE_TYPES}
