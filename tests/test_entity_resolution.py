"""Tests for B.46 Entity Resolution Infrastructure.

Tests cover:
- ProPublica client search and matching
- db.py entity resolution helpers
- data_sync.py propublica sync registration
- Conflict scanner entity graph integration
- signal_llc_ownership_chain detector
"""
import json
import uuid
from datetime import date, datetime
from unittest.mock import patch, MagicMock

import pytest


# ── ProPublica Client Tests ──────────────────────────────────

class TestProPublicaClient:
    """Test the ProPublica Nonprofit Explorer API client."""

    def test_normalize_name(self):
        from propublica_client import _normalize_name
        assert _normalize_name("  ACME  Corp  ") == "acme corp"
        assert _normalize_name("Richmond Community Foundation") == "richmond community foundation"

    @patch("propublica_client.requests.get")
    def test_search_organizations(self, mock_get):
        from propublica_client import search_organizations

        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "total_results": 1,
                "organizations": [
                    {"ein": 943337754, "name": "Richmond Community Foundation", "city": "Richmond", "state": "CA"}
                ],
                "num_pages": 1,
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()

        result = search_organizations("Richmond Community Foundation", state="CA")
        assert result["total_results"] == 1
        assert result["organizations"][0]["ein"] == 943337754

    @patch("propublica_client.requests.get")
    def test_search_404_returns_empty(self, mock_get):
        """ProPublica returns 404 for no-match searches — should return empty, not raise."""
        from propublica_client import search_organizations

        mock_get.return_value = MagicMock(status_code=404)
        result = search_organizations("Nonexistent Org XYZ", state="CA")
        assert result["organizations"] == []
        assert result["total_results"] == 0

    @patch("propublica_client.requests.get")
    def test_fetch_organization_not_found(self, mock_get):
        from propublica_client import fetch_organization

        mock_get.return_value = MagicMock(status_code=404)
        result = fetch_organization("000000000")
        assert result is None

    @patch("propublica_client.requests.get")
    def test_fetch_organization_success(self, mock_get):
        from propublica_client import fetch_organization

        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "organization": {
                    "id": 123,
                    "ein": 943337754,
                    "name": "Richmond Community Foundation",
                }
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()

        result = fetch_organization("94-3337754")
        assert result["ein"] == 943337754

    @patch("propublica_client.search_organizations")
    def test_resolve_employer_exact_match(self, mock_search):
        from propublica_client import resolve_employer_to_nonprofit

        mock_search.return_value = {
            "organizations": [
                {"ein": 943337754, "name": "Richmond Community Foundation",
                 "city": "Richmond", "state": "CA", "ntee_code": "T20",
                 "have_filings": True, "strein": "94-3337754"},
            ],
        }

        result = resolve_employer_to_nonprofit("Richmond Community Foundation", state="CA")
        assert result is not None
        assert result["ein"] == 943337754
        assert result["confidence"] >= 0.9

    @patch("propublica_client.search_organizations")
    def test_resolve_employer_no_match(self, mock_search):
        from propublica_client import resolve_employer_to_nonprofit

        mock_search.return_value = {"organizations": []}
        result = resolve_employer_to_nonprofit("Chevron Corporation", state="CA")
        assert result is None

    def test_resolve_employer_skip_government(self):
        from propublica_client import resolve_employer_to_nonprofit
        # Prefix filters
        assert resolve_employer_to_nonprofit("City of Richmond") is None
        assert resolve_employer_to_nonprofit("State of California") is None
        assert resolve_employer_to_nonprofit("retired") is None
        assert resolve_employer_to_nonprofit("") is None
        assert resolve_employer_to_nonprofit("ab") is None  # too short
        # Suffix filters (e.g. "Alameda County" format)
        assert resolve_employer_to_nonprofit("Alameda County") is None
        assert resolve_employer_to_nonprofit("West Contra Costa Unified School District") is None
        assert resolve_employer_to_nonprofit("Albany School District") is None
        # Keyword filters
        assert resolve_employer_to_nonprofit("Richmond Police Department") is None
        assert resolve_employer_to_nonprofit("Alameda County Behavioral Health") is None

    @patch("propublica_client.search_organizations")
    def test_resolve_html_entities_in_employer(self, mock_search):
        """HTML entities like &amp; should be decoded before querying."""
        from propublica_client import resolve_employer_to_nonprofit

        mock_search.return_value = {
            "organizations": [{
                "ein": 123456789, "name": "Zuckerman & McQuiller",
                "city": "Richmond", "state": "CA", "ntee_code": "T20",
                "have_filings": True, "strein": "12-3456789",
            }],
        }

        result = resolve_employer_to_nonprofit("Zuckerman &amp; McQuiller", state="CA")
        # Should have decoded &amp; to & before searching
        mock_search.assert_called_once_with("Zuckerman & McQuiller", state="CA")
        assert result is not None
        assert result["ein"] == 123456789

    @patch("propublica_client.resolve_employer_to_nonprofit")
    def test_batch_resolve_deduplicates(self, mock_resolve):
        from propublica_client import batch_resolve_employers

        mock_resolve.return_value = {"ein": 123, "name": "Test Org", "confidence": 0.9}
        results = batch_resolve_employers(
            ["Test Org", "test org", "TEST ORG"],  # duplicates
            delay=0,
        )
        # Should only call resolve once (deduplicated by normalized name)
        assert mock_resolve.call_count == 1
        assert len(results) == 1


# ── Data Sync Registration Tests ─────────────────────────────

class TestSyncRegistration:
    """Test that propublica sync is properly registered."""

    def test_propublica_in_sync_sources(self):
        from data_sync import SYNC_SOURCES
        assert "propublica" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_propublica_sync_dispatches(self, mock_complete, mock_create, mock_conn):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()

        fake_sync = MagicMock(return_value={
            "records_fetched": 50,
            "records_new": 5,
            "records_updated": 2,
            "entity_links_created": 10,
            "entities_resolved": 3,
        })

        with patch.dict(SYNC_SOURCES, {"propublica": fake_sync}):
            result = run_sync(source="propublica", sync_type="full", triggered_by="test")

        assert result["status"] == "completed"
        assert result["records_fetched"] == 50


# ── Scanner Match Type Tests ─────────────────────────────────

class TestRegistryMatchTypes:
    """Test that registry match types produce correct strengths."""

    def test_registry_match_strength(self):
        from conflict_scanner import _match_type_to_strength
        assert _match_type_to_strength("registry_match") == 0.95
        assert _match_type_to_strength("registry_officer") == 0.90
        assert _match_type_to_strength("registry_agent") == 0.85
        assert _match_type_to_strength("registry_employee") == 0.80

    def test_registry_match_ranks_correctly(self):
        """Registry match should rank between exact and phrase."""
        from conflict_scanner import _match_type_to_strength
        exact = _match_type_to_strength("exact")
        registry = _match_type_to_strength("registry_match")
        phrase = _match_type_to_strength("phrase")
        assert exact > registry > phrase


# ── Signal LLC Ownership Chain Tests ──────────────────────────

class TestSignalLLCOwnershipChain:
    """Test the LLC ownership chain signal detector (B.46)."""

    def _make_ctx(self, org_reverse_map=None):
        from conflict_scanner import _ScanContext, ScanAuditLogger
        return _ScanContext(
            council_member_names=set(),
            alias_groups={},
            current_officials={"Jane Smith"},
            former_officials=set(),
            seen_contributions=set(),
            audit_logger=ScanAuditLogger(),
            filter_counts={
                "filtered_council_member": 0, "filtered_govt_employer": 0,
                "filtered_govt_donor": 0, "filtered_dedup": 0,
                "filtered_short_name": 0, "passed_to_flag": 0,
                "suppressed_near_miss": 0,
            },
            meeting_date="2025-03-01",
            city_fips="0660620",
            name_in_text_cache={},
            entity_graph={},
            org_reverse_map=org_reverse_map or {},
        )

    def test_no_signals_without_entity_graph(self):
        from conflict_scanner import signal_llc_ownership_chain
        ctx = self._make_ctx()
        signals = signal_llc_ownership_chain(
            item_num="H-1",
            item_title="Contract with ABC Corp",
            item_text="Approve contract with ABC Corp for services",
            financial="$50,000",
            entities=["ABC Corp"],
            contributions=[{
                "donor_name": "John Doe",
                "committee_name": "Jane Smith for Council 2024",
                "amount": 500,
                "date": "2024-11-01",
            }],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_detects_llc_ownership_chain(self):
        from conflict_scanner import signal_llc_ownership_chain

        org_reverse_map = {
            "abc corp": [{
                "person_name": "John Doe",
                "normalized_person_name": "john doe",
                "role": "officer",
                "confidence": 0.95,
                "donor_id": None,
                "official_id": None,
                "org_name": "ABC Corp",
                "entity_type": "corporation",
            }],
        }
        ctx = self._make_ctx(org_reverse_map=org_reverse_map)

        signals = signal_llc_ownership_chain(
            item_num="H-1",
            item_title="Contract with ABC Corp",
            item_text="Approve contract with ABC Corp for services",
            financial="$50,000",
            entities=["ABC Corp"],
            contributions=[{
                "donor_name": "John Doe",
                "_norm_donor": "john doe",
                "committee_name": "Jane Smith for Council 2024",
                "amount": 500,
                "date": "2024-11-01",
            }],
            ctx=ctx,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "llc_ownership_chain"
        assert sig.match_strength == 0.90  # registry_officer
        assert "John Doe" in sig.description
        assert "ABC Corp" in sig.description
        assert sig.match_details["role"] == "officer"
        assert sig.match_details["sitting"] is True

    def test_skips_non_sitting_members(self):
        from conflict_scanner import signal_llc_ownership_chain

        org_reverse_map = {
            "abc corp": [{
                "person_name": "John Doe",
                "normalized_person_name": "john doe",
                "role": "officer",
                "confidence": 0.95,
                "donor_id": None,
                "official_id": None,
                "org_name": "ABC Corp",
                "entity_type": "corporation",
            }],
        }
        ctx = self._make_ctx(org_reverse_map=org_reverse_map)

        signals = signal_llc_ownership_chain(
            item_num="H-1",
            item_title="Contract with ABC Corp",
            item_text="Approve contract with ABC Corp for services",
            financial="$50,000",
            entities=["ABC Corp"],
            contributions=[{
                "donor_name": "John Doe",
                "_norm_donor": "john doe",
                # Not a sitting council member's committee
                "committee_name": "Bob Jones for Mayor 2020",
                "amount": 500,
                "date": "2024-11-01",
            }],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_skips_small_amounts(self):
        from conflict_scanner import signal_llc_ownership_chain

        org_reverse_map = {
            "abc corp": [{
                "person_name": "John Doe",
                "normalized_person_name": "john doe",
                "role": "officer",
                "confidence": 0.95,
                "donor_id": None,
                "official_id": None,
                "org_name": "ABC Corp",
                "entity_type": "corporation",
            }],
        }
        ctx = self._make_ctx(org_reverse_map=org_reverse_map)

        signals = signal_llc_ownership_chain(
            item_num="H-1",
            item_title="Contract with ABC Corp",
            item_text="Approve contract with ABC Corp for services",
            financial="$50,000",
            entities=["ABC Corp"],
            contributions=[{
                "donor_name": "John Doe",
                "_norm_donor": "john doe",
                "committee_name": "Jane Smith for Council 2024",
                "amount": 25,  # Below $100 threshold
                "date": "2024-11-01",
            }],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_role_determines_match_type(self):
        """Different roles should produce different match types."""
        from conflict_scanner import signal_llc_ownership_chain

        for role, expected_type in [
            ("officer", "registry_officer"),
            ("director", "registry_officer"),
            ("agent", "registry_agent"),
            ("employee", "registry_employee"),
        ]:
            org_reverse_map = {
                "test org": [{
                    "person_name": "John Doe",
                    "normalized_person_name": "john doe",
                    "role": role,
                    "confidence": 0.95,
                    "donor_id": None,
                    "official_id": None,
                    "org_name": "Test Org",
                    "entity_type": "nonprofit",
                }],
            }
            ctx = self._make_ctx(org_reverse_map=org_reverse_map)
            signals = signal_llc_ownership_chain(
                item_num="H-1",
                item_title="Contract with Test Org",
                item_text="Approve contract with Test Org",
                financial=None,
                entities=["Test Org"],
                contributions=[{
                    "donor_name": "John Doe",
                    "_norm_donor": "john doe",
                    "committee_name": "Jane Smith for Council 2024",
                    "amount": 1000,
                    "date": "2024-11-01",
                }],
                ctx=ctx,
            )
            assert len(signals) == 1, f"Expected 1 signal for role={role}"
            assert signals[0].match_details["match_type"] == expected_type


# ── Scanner Integration Tests (scan_meeting_json with entity graph) ──

class TestScannerEntityGraphIntegration:
    """Test that scan_meeting_json correctly accepts and uses entity graph."""

    def test_scan_meeting_json_accepts_entity_graph(self):
        """scan_meeting_json should accept entity_graph and org_reverse_map without error."""
        from conflict_scanner import scan_meeting_json

        meeting_data = {
            "meeting_date": "2025-03-01",
            "meeting_type": "Regular",
            "members_present": [{"name": "Jane Smith"}],
            "consent_calendar": {"items": [], "votes": []},
            "action_items": [{
                "item_number": "H-1",
                "title": "Approve contract with XYZ Inc",
                "description": "Approve contract with XYZ Inc for consulting.",
                "financial_amount": "$25,000",
            }],
            "housing_authority_items": [],
        }

        result = scan_meeting_json(
            meeting_data=meeting_data,
            contributions=[],
            entity_graph={},
            org_reverse_map={},
        )
        assert result is not None
        assert result.total_items_scanned == 1

    def test_scan_meeting_json_entity_graph_produces_signals(self):
        """Entity graph data should produce LLC ownership chain signals.

        Uses a real Richmond council member name so that is_sitting_council_member()
        works correctly (it checks against city_config, not members_present).
        """
        from conflict_scanner import scan_meeting_json

        org_reverse_map = {
            "xyz inc": [{
                "person_name": "Alice Donor",
                "normalized_person_name": "alice donor",
                "role": "officer",
                "confidence": 0.95,
                "donor_id": None,
                "official_id": None,
                "org_name": "XYZ Inc",
                "entity_type": "corporation",
            }],
        }

        meeting_data = {
            "meeting_date": "2025-03-01",
            "meeting_type": "Regular",
            "members_present": [{"name": "Eduardo Martinez"}],
            "consent_calendar": {"items": [], "votes": []},
            "action_items": [{
                "item_number": "H-1",
                "title": "Approve contract with XYZ Inc for fifty thousand",
                "description": "Approve consulting contract with XYZ Inc.",
                "financial_amount": "$50,000",
            }],
            "housing_authority_items": [],
        }

        contributions = [{
            "donor_name": "Alice Donor",
            "_norm_donor": "alice donor",
            "committee_name": "Eduardo Martinez for Mayor 2022",
            "amount": 1000,
            "date": "2024-11-01",
            "source": "netfile",
            "filing_id": "123",
        }]

        result = scan_meeting_json(
            meeting_data=meeting_data,
            contributions=contributions,
            entity_graph={},
            org_reverse_map=org_reverse_map,
        )

        # Should produce at least one flag from LLC ownership chain
        llc_flags = [f for f in result.flags if f.flag_type == "llc_ownership_chain"]
        assert len(llc_flags) >= 1
        assert "Alice Donor" in llc_flags[0].description
        assert "XYZ Inc" in llc_flags[0].description
