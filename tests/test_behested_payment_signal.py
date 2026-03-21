"""Tests for S13.1 signal detector: behested payment (FPPC Form 803).

Tests signal_behested_payment() — detects when a payor or payee in a
behested payment disclosure appears in an agenda item, connecting the
official's fundraising requests to the city's business.

Includes regression tests for the tuple-truthiness bug (ed6390f):
cached_name_in_text() returns (bool, str), and `not (False, "no_match")`
is False because non-empty tuples are always truthy in Python. The fix
unpacks to `payor_in_text, _ = cached_name_in_text(...)`.
"""
import pytest
from conflict_scanner import (
    RawSignal,
    _ScanContext,
    signal_behested_payment,
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


# ══════════════════════════════════════════════════════════════
# signal_behested_payment tests
# ══════════════════════════════════════════════════════════════


class TestBehestedPaymentBasic:
    """Basic signal generation for behested payment connections."""

    def test_payor_in_agenda_text(self):
        """Signal fires when payor name appears in agenda item text."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract Award — Road Resurfacing",
            item_text="Approve contract with Acme Construction LLC for road resurfacing project",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.signal_type == "behested_payment"
        assert "martinez" in s.council_member.lower()
        assert s.match_details["payor_in_text"] is True
        assert s.match_details["payee_in_text"] is False
        assert s.match_strength == 0.85  # Payor match = 0.85

    def test_payee_in_agenda_text(self):
        """Signal fires when payee (beneficiary) appears in agenda text."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Sue Wilson",
                payor_name="Chevron Corporation",
                payee_name="Richmond Youth Center",
                amount=50000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="H.3",
            item_title="Grant Award — Youth Programs",
            item_text="Approve grant allocation to Richmond Youth Center for after-school programs",
            financial="$100,000",
            entities=["Richmond Youth Center"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.match_details["payee_in_text"] is True
        assert s.match_details["match_direction"] == "payee (beneficiary)"
        assert s.match_strength == 0.70  # Payee match = 0.70

    def test_no_signal_when_empty_behested(self):
        """No signal with empty behested payment list."""
        ctx = _make_ctx()
        signals = signal_behested_payment(
            item_num="A.1",
            item_title="Title",
            item_text="Some agenda text about things",
            financial=None,
            entities=[],
            behested_payments=[],
            contributions=[],
            ctx=ctx,
        )
        assert signals == []

    def test_non_official_filtered(self):
        """No signal when official isn't in current or former officials set."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="John Doe",  # Not a known official
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract",
            item_text="Approve contract with Acme Construction LLC for road work",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert signals == []

    def test_short_payor_name_filtered(self):
        """Payor names shorter than 5 chars are skipped."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="ABC",  # Too short
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract",
            item_text="ABC awarded contract for road work with Richmond Youth Center",
            financial="$100,000",
            entities=["ABC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert signals == []

    def test_former_official_detected(self):
        """Signal fires for former officials (historical analysis)."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Ben Choi",
                payor_name="Acme Construction LLC",
                payee_name="Local Nonprofit",
                amount=10000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract",
            item_text="Approve contract with Acme Construction LLC",
            financial="$200,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].match_details["sitting"] is False


class TestBehestedPaymentFinancialFactor:
    """Financial factor scales with behested payment amount."""

    @pytest.mark.parametrize("amount,expected_min", [
        (150000, 1.0),
        (10000, 0.8),
        (5000, 0.6),
        (100, 0.4),
    ])
    def test_financial_factor_tiers(self, amount, expected_min):
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=amount,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract",
            item_text="Approve contract with Acme Construction LLC",
            financial=None,
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].financial_factor == expected_min


class TestBehestedPaymentTupleBugRegression:
    """Regression tests for the tuple-truthiness bug (commit ed6390f).

    cached_name_in_text() returns (bool, str). Before the fix,
    the code did `if not payor_in_text` where payor_in_text was the
    full tuple — and `not (False, "no_match")` is False because
    non-empty tuples are always truthy in Python. This meant EVERY
    payor passed the filter even when their name wasn't in the text.
    """

    def test_no_signal_when_neither_payor_nor_payee_in_text(self):
        """Core regression: payor and payee absent from text must produce
        zero signals. Before the fix, this incorrectly produced a signal
        because `not (False, "no_match")` evaluated to False."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Completely Unrelated Corp",
                payee_name="Another Unrelated Foundation",
                amount=50000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Park Renovation",
            item_text="Approve park renovation project for Miller Knox Regional Shoreline",
            financial="$200,000",
            entities=[],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        # Before the bug fix, this was len(signals) == 1 (false positive)
        assert signals == [], (
            "Tuple truthiness regression: entity not in text should produce "
            "no signal. If this fails, check that cached_name_in_text() "
            "result is being unpacked as (bool, str), not used as a raw tuple."
        )

    def test_only_payor_match_no_payee_leakage(self):
        """When payor IS in text but payee is NOT, only payor should
        register as matched. Verifies independent checking of each."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Totally Different Nonprofit",
                amount=25000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC for road resurfacing",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.match_details["payor_in_text"] is True
        assert s.match_details["payee_in_text"] is False
        assert s.match_details["match_direction"] == "payor"

    def test_only_payee_match_no_payor_leakage(self):
        """When payee IS in text but payor is NOT, only payee should
        register. This was also broken by the tuple bug since
        payor_in_text always appeared truthy."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Sue Wilson",
                payor_name="Totally Different Corp",
                payee_name="Richmond Youth Center",
                amount=50000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="H.3",
            item_title="Grant Award",
            item_text="Approve grant to Richmond Youth Center",
            financial="$100,000",
            entities=["Richmond Youth Center"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.match_details["payor_in_text"] is False
        assert s.match_details["payee_in_text"] is True
        assert s.match_details["match_direction"] == "payee (beneficiary)"

    def test_multiple_payments_only_matching_ones_fire(self):
        """With multiple behested payments, only those whose payor/payee
        appears in text should produce signals. Before the fix, ALL
        payments would pass through."""
        ctx = _make_ctx()
        behested = [
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Acme Construction LLC",
                payee_name="Richmond Youth Center",
                amount=25000,
            ),
            _make_behested(
                official_name="Eduardo Martinez",
                payor_name="Unrelated Pharma Inc",
                payee_name="Unrelated Hospital",
                amount=75000,
            ),
            _make_behested(
                official_name="Sue Wilson",
                payor_name="Mystery Donor Corp",
                payee_name="Invisible Foundation",
                amount=30000,
            ),
        ]
        signals = signal_behested_payment(
            item_num="G.1",
            item_title="Contract Award",
            item_text="Approve contract with Acme Construction LLC for road resurfacing",
            financial="$500,000",
            entities=["Acme Construction LLC"],
            behested_payments=behested,
            contributions=[],
            ctx=ctx,
        )
        # Only the first payment's payor matches the text
        assert len(signals) == 1
        assert signals[0].match_details["payor_name"] == "Acme Construction LLC"
