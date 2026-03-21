"""Tests for S13.5 signal detector: behested payment loop (influence cycle).

Tests signal_behested_payment_loop() — the multi-hop influence cycle detector
that cross-references campaign contributions, FPPC Form 803 behested payments,
and agenda item text (with optional lobbyist registration corroboration).
"""
import pytest
from conflict_scanner import (
    RawSignal,
    _ScanContext,
    signal_behested_payment_loop,
    ScanAuditLogger,
    _load_alias_map,
)


# ── Helper factories ────────────────────────────────────────


def _make_ctx(**overrides) -> _ScanContext:
    """Build a _ScanContext with sensible defaults."""
    defaults = dict(
        council_member_names=set(),
        alias_groups=_load_alias_map("0660620"),
        current_officials={"Sue Wilson", "Claudia Jimenez", "Cesar Zepeda",
                           "Jamelia Brown", "Soheila Bana", "Ahmad Anderson",
                           "Eduardo Martinez"},
        former_officials={"Oscar Garcia", "Ben Choi"},
        seen_contributions=set(),
        audit_logger=ScanAuditLogger(),
        filter_counts={
            "filtered_council_member": 0,
            "filtered_govt_employer": 0,
            "filtered_govt_donor": 0,
            "filtered_dedup": 0,
            "filtered_short_name": 0,
            "passed_to_flag": 0,
            "suppressed_near_miss": 0,
        },
        meeting_date="2026-01-15",
        city_fips="0660620",
    )
    defaults.update(overrides)
    return _ScanContext(**defaults)


def _make_contribution(**kwargs):
    """Build a contribution dict with defaults."""
    defaults = {
        "donor_name": "", "donor_employer": "", "council_member": "",
        "committee_name": "", "amount": 0, "date": "2025-06-10",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


def _make_behested(**kwargs):
    """Build a behested payment dict with defaults."""
    defaults = {
        "official_name": "",
        "payor_name": "",
        "payee_name": "",
        "amount": 0,
        "payment_date": "2025-09-01",
        "filing_date": "2025-10-01",
        "filing_id": "803-TEST-001",
    }
    defaults.update(kwargs)
    return defaults


def _make_lobbyist(**kwargs):
    """Build a lobbyist registration dict with defaults."""
    defaults = {
        "lobbyist_name": "",
        "lobbyist_firm": "",
        "client_name": "",
        "registration_date": "2025-01-01",
        "status": "Active",
    }
    defaults.update(kwargs)
    return defaults


# ══════════════════════════════════════════════════════════════
# signal_behested_payment_loop tests
# ══════════════════════════════════════════════════════════════


class TestBehestedPaymentLoop:
    """Test multi-hop influence cycle detection."""

    def test_basic_loop_payor(self):
        """Full loop: entity donates to official, official behests from entity,
        entity appears in agenda item."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award — Road Resurfacing",
            item_text="Approve contract with Acme Construction LLC for road resurfacing project",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.signal_type == "behested_payment_loop"
        assert "eduardo martinez" in s.council_member.lower()
        assert s.match_details["loop_entity"] == "Acme Construction LLC"
        assert s.match_details["loop_role"] == "payor"
        assert s.match_details["behested_amount"] == 25000
        assert s.match_details["contribution_total"] == 5000
        assert s.match_details["lobbyist_corroboration"] is False
        assert s.match_strength == 0.90

    def test_basic_loop_payee(self):
        """Loop where the payee (beneficiary org) appears in agenda text."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Richmond Youth Center",
                council_member="Sue Wilson",
                amount=2000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Sue Wilson",
                payor_name="Chevron Corporation",
                payee_name="Richmond Youth Center",
                amount=50000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="H.3",
            item_title="Grant Award — Youth Programs",
            item_text="Approve grant allocation to Richmond Youth Center for after-school programs",
            financial="$100,000",
            entities=["Richmond Youth Center"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.match_details["loop_role"] == "payee"
        assert s.match_details["loop_entity"] == "Richmond Youth Center"

    def test_no_signal_without_contribution(self):
        """No loop if the entity hasn't contributed to the official."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC for road work",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=[],  # No contributions
            ctx=ctx,
        )
        assert signals == []

    def test_no_signal_when_entity_not_in_text(self):
        """No loop if the behested entity doesn't appear in agenda text."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Park Renovation",
            item_text="Approve park renovation project for Miller Knox Regional Shoreline",
            financial="$200,000",
            entities=[],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert signals == []

    def test_no_signal_for_non_official(self):
        """No loop if the behested payment official isn't a known council member."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="John Doe",
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="John Doe",  # Not in current/former officials
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert signals == []

    def test_contribution_via_committee_name(self):
        """Loop detected when contribution is to a committee, not directly to official."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Bay Area Builders Inc",
                committee_name="Eduardo Martinez for Richmond 2024",
                amount=3000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Bay Area Builders Inc",
                payee_name="Local Housing Fund",
                amount=15000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="F.2",
            item_title="Housing Development Agreement",
            item_text="Approve development agreement with Bay Area Builders Inc for affordable housing",
            financial="$2,000,000",
            entities=["Bay Area Builders Inc"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].match_details["contribution_count"] == 1

    def test_lobbyist_corroboration_boosts_strength(self):
        """When entity is also a lobbyist client, match_strength increases to 0.95."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="TechCorp Solutions",
                council_member="Claudia Jimenez",
                amount=4500,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Claudia Jimenez",
                payor_name="TechCorp Solutions",
                payee_name="Richmond STEM Initiative",
                amount=20000,
            ),
        ]
        lobbyists = [
            _make_lobbyist(
                lobbyist_name="Smith & Associates",
                client_name="TechCorp Solutions",
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="I.1",
            item_title="Technology Services Contract",
            item_text="Approve IT services contract with TechCorp Solutions",
            financial="$300,000",
            entities=["TechCorp Solutions"],
            behested_payments=behested,
            lobbyist_registrations=lobbyists,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.match_strength == 0.95  # Boosted from 0.90
        assert s.match_details["lobbyist_corroboration"] is True
        assert s.match_details["lobbyist_name"] == "Smith & Associates"
        assert "4th independent source" in s.evidence[-1]

    def test_employer_match_closes_loop(self):
        """Loop closed via donor employer matching the behested entity."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Jane Smith",
                donor_employer="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=1000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Road Work Contract",
            item_text="Approve contract with Acme Construction LLC for road resurfacing",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1

    def test_financial_factor_scales_with_amount(self):
        """Financial factor increases with combined behested + contribution amount."""
        ctx = _make_ctx()
        # Small amounts
        contributions_small = [
            _make_contribution(
                donor_name="SmallCo Inc",
                council_member="Sue Wilson",
                amount=200,
            ),
        ]
        behested_small = [
            _make_behested(
                official_name="Sue Wilson",
                payor_name="SmallCo Inc",
                payee_name="Local Charity",
                amount=500,
            ),
        ]
        signals_small = signal_behested_payment_loop(
            item_num="A.1",
            item_title="Contract",
            item_text="Approve contract with SmallCo Inc",
            financial=None,
            entities=["SmallCo Inc"],
            behested_payments=behested_small,
            lobbyist_registrations=[],
            contributions=contributions_small,
            ctx=ctx,
        )

        # Large amounts
        contributions_large = [
            _make_contribution(
                donor_name="BigCorp International",
                council_member="Sue Wilson",
                amount=50000,
            ),
        ]
        behested_large = [
            _make_behested(
                official_name="Sue Wilson",
                payor_name="BigCorp International",
                payee_name="Local Charity",
                amount=75000,
            ),
        ]
        signals_large = signal_behested_payment_loop(
            item_num="A.2",
            item_title="Contract",
            item_text="Approve contract with BigCorp International",
            financial=None,
            entities=["BigCorp International"],
            behested_payments=behested_large,
            lobbyist_registrations=[],
            contributions=contributions_large,
            ctx=ctx,
        )

        assert len(signals_small) == 1
        assert len(signals_large) == 1
        assert signals_large[0].financial_factor > signals_small[0].financial_factor

    def test_multiple_contributions_aggregate(self):
        """Multiple contributions from entity to same official are summed."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=1000,
                date="2025-03-15",
                filing_id="TEST-001",
            ),
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=2000,
                date="2025-06-20",
                filing_id="TEST-002",
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.match_details["contribution_total"] == 3000
        assert s.match_details["contribution_count"] == 2

    def test_former_official_detected(self):
        """Loop also fires for former officials (historical analysis)."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Ben Choi",
                amount=2000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Ben Choi",
                payor_name="Acme Construction LLC",
                payee_name="Local Nonprofit",
                amount=10000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract",
            item_text="Approve contract with Acme Construction LLC",
            financial="$200,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].match_details["sitting"] is False

    def test_short_entity_names_filtered(self):
        """Entity names shorter than 5 characters are filtered out."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="ABC",
                council_member="Eduardo Martinez",
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="ABC",
                payee_name="XYZ",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract",
            item_text="ABC awarded contract for XYZ program",
            financial="$100,000",
            entities=["ABC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert signals == []

    def test_evidence_chain_complete(self):
        """Evidence array contains all three hops of the loop."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        evidence = signals[0].evidence
        assert len(evidence) >= 3
        assert any("Campaign contribution" in e for e in evidence)
        assert any("Behested payment" in e or "Form 803" in e for e in evidence)
        assert any("Agenda item" in e for e in evidence)

    def test_legal_reference_includes_both_statutes(self):
        """Legal reference cites both behested payment and campaign contribution law."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Eduardo Martinez",
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        ref = signals[0].legal_reference
        assert "82015" in ref  # Behested payments
        assert "84308" in ref  # Campaign contributions
        assert "Form 803" in ref

    def test_no_signal_with_empty_inputs(self):
        """Gracefully returns empty for empty behested or contribution lists."""
        ctx = _make_ctx()
        assert signal_behested_payment_loop(
            "A.1", "Title", "Text about things", None, [],
            [], [], [], ctx,
        ) == []
        assert signal_behested_payment_loop(
            "A.1", "Title", "Text about things", None, [],
            [_make_behested(official_name="X", payor_name="Y", amount=100)],
            [], [], ctx,
        ) == []

    def test_contribution_to_different_official_no_loop(self):
        """No loop when contribution goes to a different official than the one
        who behested the payment."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction LLC",
                council_member="Sue Wilson",  # Different official
                amount=5000,
            ),
        ]
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",  # This official behested
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment_loop(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            lobbyist_registrations=[],
            contributions=contributions,
            ctx=ctx,
        )
        assert signals == []
