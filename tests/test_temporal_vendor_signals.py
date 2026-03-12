"""Tests for S9.3 signal detectors: temporal correlation and donor-vendor-expenditure.

Tests signal_temporal_correlation(), signal_donor_vendor_expenditure(),
and the updated _signals_to_flags() corroboration grouping.
"""
import pytest
from datetime import date
from conflict_scanner import (
    RawSignal,
    ConflictFlag,
    _ScanContext,
    signal_temporal_correlation,
    signal_donor_vendor_expenditure,
    _signals_to_flags,
    compute_composite_confidence,
    extract_entity_names,
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
        "committee_name": "", "amount": 0, "date": "2026-02-15",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


def _make_expenditure(**kwargs):
    """Build an expenditure dict with defaults."""
    defaults = {
        "normalized_vendor": "", "vendor_name": "",
        "amount": 0, "fiscal_year": "2025-2026", "department": "City Manager",
    }
    defaults.update(kwargs)
    return defaults


# ── signal_temporal_correlation ─────────────────────────────


class TestSignalTemporalCorrelation:
    """Test post-vote donation signal detection."""

    def test_basic_post_vote_donation(self):
        """Detect donation from entity in agenda item after official voted Aye."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        post_vote = [
            (_make_contribution(
                donor_name="John Smith",
                donor_employer="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
                date="2026-02-15",
            ), date(2026, 2, 15)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Approve contract with Acme Corp"},
            item_num="H-5",
            item_title="Approve contract with Acme Corp",
            item_text="Approve contract with Acme Corp for consulting services",
            financial="$50,000",
            entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez", "Sue Wilson"},
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official,
            ctx=ctx,
        )

        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "temporal_correlation"
        assert sig.council_member == "Eduardo Martinez"
        assert sig.agenda_item_number == "H-5"
        assert sig.temporal_factor == 1.0  # 31 days after
        assert sig.financial_factor > 0  # $5000 donation

    def test_no_match_when_donor_not_in_entities(self):
        """No signal when donor doesn't match any entity in the item."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        post_vote = [
            (_make_contribution(
                donor_name="Jane Doe",
                donor_employer="Other Corp",
                committee_name="Martinez for Richmond 2026",
                amount=1000,
                date="2026-02-15",
            ), date(2026, 2, 15)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Approve contract with Acme Corp"},
            item_num="H-5",
            item_title="Approve contract with Acme Corp",
            item_text="Approve contract with Acme Corp",
            financial=None,
            entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official,
            ctx=ctx,
        )

        assert len(signals) == 0

    def test_no_signal_when_official_did_not_vote_aye(self):
        """No signal when the recipient official didn't vote Aye."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        post_vote = [
            (_make_contribution(
                donor_name="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
                date="2026-02-15",
            ), date(2026, 2, 15)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Approve contract with Acme Corp"},
            item_num="H-5",
            item_title="Approve contract with Acme Corp",
            item_text="Approve contract with Acme Corp",
            financial=None,
            entities=["Acme Corp"],
            aye_voters={"Sue Wilson"},  # Martinez NOT in aye voters
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official,
            ctx=ctx,
        )

        assert len(signals) == 0

    def test_employer_match(self):
        """Detect signal when donor's employer matches entity."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        post_vote = [
            (_make_contribution(
                donor_name="John Smith",
                donor_employer="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=2500,
                date="2026-03-01",
            ), date(2026, 3, 1)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Approve contract with Acme Corp"},
            item_num="H-5",
            item_title="Approve contract with Acme Corp",
            item_text="Approve contract with Acme Corp for services",
            financial=None,
            entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official,
            ctx=ctx,
        )

        assert len(signals) == 1
        assert "employer" in signals[0].match_details.get("match_type", "")

    def test_temporal_decay_scoring(self):
        """Temporal factor decays with longer delays after vote."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        # 30 days after -> 1.0
        post_vote_30 = [
            (_make_contribution(
                donor_name="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=1000,
                date="2026-02-14",
            ), date(2026, 2, 14)),
        ]
        sigs_30 = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Acme Corp contract"},
            item_num="H-5", item_title="Acme Corp contract",
            item_text="Acme Corp contract", financial=None,
            entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote_30,
            committee_to_official=committee_to_official, ctx=ctx,
        )

        # 200 days after -> 0.7
        post_vote_200 = [
            (_make_contribution(
                donor_name="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=1000,
                date="2026-08-03",
            ), date(2026, 8, 3)),
        ]
        sigs_200 = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Acme Corp contract"},
            item_num="H-5", item_title="Acme Corp contract",
            item_text="Acme Corp contract", financial=None,
            entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote_200,
            committee_to_official=committee_to_official, ctx=ctx,
        )

        assert sigs_30[0].temporal_factor > sigs_200[0].temporal_factor

    def test_skips_government_donors(self):
        """Government entity donors are filtered out."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        post_vote = [
            (_make_contribution(
                donor_name="City of Richmond",
                committee_name="Martinez for Richmond 2026",
                amount=10000,
                date="2026-02-15",
            ), date(2026, 2, 15)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "City budget allocation"},
            item_num="H-5", item_title="City budget allocation",
            item_text="City of Richmond budget", financial=None,
            entities=["City of Richmond"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official, ctx=ctx,
        )

        assert len(signals) == 0

    def test_deduplication(self):
        """Same donor+committee+item only produces one signal."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        # Two contributions from same donor to same committee
        post_vote = [
            (_make_contribution(
                donor_name="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=1000,
                date="2026-02-15",
            ), date(2026, 2, 15)),
            (_make_contribution(
                donor_name="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=2000,
                date="2026-03-01",
            ), date(2026, 3, 1)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Acme Corp contract"},
            item_num="H-5", item_title="Acme Corp contract",
            item_text="Acme Corp contract", financial=None,
            entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official, ctx=ctx,
        )

        assert len(signals) == 1

    def test_empty_inputs(self):
        """Returns empty list for missing inputs."""
        ctx = _make_ctx(meeting_date="")
        assert signal_temporal_correlation(
            item={}, item_num="H-1", item_title="Test",
            item_text="Test", financial=None, entities=[],
            aye_voters=set(), post_vote_contributions=[],
            committee_to_official={}, ctx=ctx,
        ) == []

    def test_signal_metadata(self):
        """Signal includes is_sitting and match details."""
        ctx = _make_ctx(meeting_date="2026-01-15")
        post_vote = [
            (_make_contribution(
                donor_name="Acme Corp",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
                date="2026-02-15",
            ), date(2026, 2, 15)),
        ]
        committee_to_official = {"Martinez for Richmond 2026": "Eduardo Martinez"}

        signals = signal_temporal_correlation(
            item={"item_number": "H-5", "title": "Acme Corp contract"},
            item_num="H-5", item_title="Acme Corp contract",
            item_text="Approve contract with Acme Corp",
            financial=None, entities=["Acme Corp"],
            aye_voters={"Eduardo Martinez"},
            post_vote_contributions=post_vote,
            committee_to_official=committee_to_official, ctx=ctx,
        )

        assert len(signals) == 1
        md = signals[0].match_details
        assert md["is_sitting"] is True  # Eduardo Martinez is in current_officials
        assert md["donor_name"] == "Acme Corp"
        assert md["amount"] == 5000
        assert md["days_after_vote"] > 0


# ── signal_donor_vendor_expenditure ─────────────────────────


class TestSignalDonorVendorExpenditure:
    """Test vendor-donor-expenditure cross-reference detection (gazetteer-based)."""

    def test_basic_vendor_donor_match(self):
        """Vendor in gazetteer found in text AND matches a donor -> signal."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
                date="2025-11-01",
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="Acme Construction",
                amount=150000,
            ),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Approve Acme Construction contract",
            item_text="Approve contract with Acme Construction for road repair",
            financial="$150,000",
            vendor_gazetteer=["Acme Construction"],
            contributions=contributions,
            expenditures=expenditures,
            ctx=ctx,
        )

        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "donor_vendor_expenditure"
        assert sig.council_member == "Eduardo Martinez"
        assert "Acme Construction" in sig.description

    def test_no_signal_when_vendor_not_in_text(self):
        """No signal when vendor is in gazetteer but NOT in item text."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Construction",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="Acme Construction",
                amount=100000,
            ),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Approve road repair project",
            item_text="Approve road repair project for downtown streets",
            financial=None,
            vendor_gazetteer=["Acme Construction"],
            contributions=contributions,
            expenditures=expenditures,
            ctx=ctx,
        )

        assert len(signals) == 0

    def test_no_signal_without_donor_match(self):
        """No signal when vendor is in text but NOT a donor."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Totally Different Donor",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="Acme Construction",
                amount=100000,
            ),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Approve Acme Construction contract",
            item_text="Approve contract with Acme Construction",
            financial=None,
            vendor_gazetteer=["Acme Construction"],
            contributions=contributions,
            expenditures=expenditures,
            ctx=ctx,
        )

        assert len(signals) == 0

    def test_employer_match_on_donor_side(self):
        """Signal when vendor matches donor's employer, not donor name."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="John Smith",
                donor_employer="Acme Construction",
                committee_name="Martinez for Richmond 2026",
                amount=2500,
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="Acme Construction",
                amount=200000,
            ),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Approve Acme Construction contract",
            item_text="Approve contract with Acme Construction",
            financial=None,
            vendor_gazetteer=["Acme Construction"],
            contributions=contributions,
            expenditures=expenditures,
            ctx=ctx,
        )

        assert len(signals) == 1
        assert "employer" in signals[0].match_details.get("donor_match_type", "")

    def test_financial_factor_uses_larger_amount(self):
        """Financial factor based on max(contribution, expenditure)."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Corporation Services",
                committee_name="Martinez for Richmond 2026",
                amount=500,
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="Acme Corporation Services",
                amount=500000,
            ),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Approve Acme Corporation Services contract",
            item_text="Approve contract with Acme Corporation Services",
            financial=None, vendor_gazetteer=["Acme Corporation Services"],
            contributions=contributions,
            expenditures=expenditures, ctx=ctx,
        )

        assert len(signals) == 1
        # Financial factor should be high (based on $500K expenditure)
        assert signals[0].financial_factor >= 0.8

    def test_deduplication(self):
        """Same vendor + official only produces one signal."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Corporation Services",
                committee_name="Martinez for Richmond 2026",
                amount=1000,
            ),
            _make_contribution(
                donor_name="Acme Corporation Services",
                committee_name="Martinez for Richmond 2026",
                amount=2000,
            ),
        ]
        expenditures = [
            _make_expenditure(normalized_vendor="Acme Corporation Services", amount=100000),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Approve Acme Corporation Services contract",
            item_text="Approve contract with Acme Corporation Services",
            financial=None, vendor_gazetteer=["Acme Corporation Services"],
            contributions=contributions,
            expenditures=expenditures, ctx=ctx,
        )

        assert len(signals) == 1

    def test_empty_inputs(self):
        """Returns empty list when no gazetteer, contributions, or expenditures."""
        ctx = _make_ctx()
        assert signal_donor_vendor_expenditure(
            item_num="H-1", item_title="Test", item_text="Test",
            financial=None, vendor_gazetteer=[],
            contributions=[], expenditures=[], ctx=ctx,
        ) == []

    def test_multiple_vendors_multiple_signals(self):
        """Different vendors in text can produce separate signals."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="Acme Corporation Services",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
            ),
            _make_contribution(
                donor_name="Beta Industries Inc",
                committee_name="Wilson for Richmond 2026",
                council_member="Sue Wilson",
                amount=3000,
            ),
        ]
        expenditures = [
            _make_expenditure(normalized_vendor="Acme Corporation Services", amount=100000),
            _make_expenditure(normalized_vendor="Beta Industries Inc", amount=50000),
        ]

        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Joint contract Acme and Beta",
            item_text="Contract with Acme Corporation Services and Beta Industries Inc for city services",
            financial=None,
            vendor_gazetteer=["Acme Corporation Services", "Beta Industries Inc"],
            contributions=contributions,
            expenditures=expenditures, ctx=ctx,
        )

        assert len(signals) >= 1  # At least one, possibly two

    def test_short_vendor_name_skipped(self):
        """Vendor names shorter than 10 chars are not matched by name_in_text."""
        ctx = _make_ctx()
        contributions = [
            _make_contribution(
                donor_name="ABC Co",
                committee_name="Martinez for Richmond 2026",
                amount=5000,
            ),
        ]
        expenditures = [
            _make_expenditure(normalized_vendor="ABC Co", amount=100000),
        ]

        # "ABC Co" is only 6 chars, name_in_text requires >= 10
        signals = signal_donor_vendor_expenditure(
            item_num="H-5",
            item_title="Contract with ABC Co",
            item_text="Approve contract with ABC Co for services",
            financial=None, vendor_gazetteer=["ABC Co"],
            contributions=contributions,
            expenditures=expenditures, ctx=ctx,
        )

        assert len(signals) == 0


# ── _signals_to_flags corroboration ─────────────────────────


class TestSignalsToFlagsCorroboration:
    """Test that _signals_to_flags groups signals for corroboration."""

    def _make_signal(self, signal_type="campaign_contribution", council_member="Eduardo Martinez", **kwargs):
        defaults = dict(
            signal_type=signal_type,
            council_member=council_member,
            agenda_item_number="H-5",
            match_strength=0.8,
            temporal_factor=0.7,
            financial_factor=0.6,
            description="Test signal",
            evidence=["test"],
            legal_reference="Test ref",
            financial_amount="$1,000",
            match_details={"is_sitting": True},
        )
        defaults.update(kwargs)
        return RawSignal(**defaults)

    def test_single_signal_no_boost(self):
        """One signal type -> corroboration boost is 1.0."""
        signals = [self._make_signal()]
        flags = _signals_to_flags(
            signals, "H-5", "Test item", None,
            {"Eduardo Martinez"}, {},
        )
        assert len(flags) == 1
        assert flags[0].confidence_factors is not None

    def test_two_signal_types_boost(self):
        """Two different signal types -> corroboration boost of 1.15x."""
        sig1 = self._make_signal(signal_type="campaign_contribution")
        sig2 = self._make_signal(signal_type="temporal_correlation")

        # With corroboration (2 signal types)
        flags_corroborated = _signals_to_flags(
            [sig1, sig2], "H-5", "Test", None,
            {"Eduardo Martinez"}, {},
        )

        # Without corroboration (single signal)
        flags_single = _signals_to_flags(
            [sig1], "H-5", "Test", None,
            {"Eduardo Martinez"}, {},
        )

        # Both flags should have the same corroborated confidence
        assert flags_corroborated[0].confidence == flags_corroborated[1].confidence
        # Corroborated should be higher than single
        assert flags_corroborated[0].confidence > flags_single[0].confidence

    def test_three_signal_types_max_boost(self):
        """Three+ different signal types -> 1.30x boost."""
        sig1 = self._make_signal(signal_type="campaign_contribution")
        sig2 = self._make_signal(signal_type="temporal_correlation")
        sig3 = self._make_signal(signal_type="donor_vendor_expenditure")

        flags = _signals_to_flags(
            [sig1, sig2, sig3], "H-5", "Test", None,
            {"Eduardo Martinez"}, {},
        )

        # All three flags should share the same boosted confidence
        assert flags[0].confidence == flags[1].confidence == flags[2].confidence
        assert len(flags) == 3

    def test_different_officials_independent(self):
        """Signals for different officials don't corroborate each other."""
        sig_martinez = self._make_signal(
            signal_type="campaign_contribution",
            council_member="Eduardo Martinez",
        )
        sig_wilson = self._make_signal(
            signal_type="temporal_correlation",
            council_member="Sue Wilson",
        )

        flags = _signals_to_flags(
            [sig_martinez, sig_wilson], "H-5", "Test", None,
            {"Eduardo Martinez", "Sue Wilson"}, {},
        )

        # Each official gets independent scoring (no cross-official corroboration)
        assert len(flags) == 2
        martinez_flag = [f for f in flags if f.council_member == "Eduardo Martinez"][0]
        wilson_flag = [f for f in flags if f.council_member == "Sue Wilson"][0]
        # Both should have single-signal confidence (no boost)
        assert martinez_flag.confidence == wilson_flag.confidence

    def test_all_flags_scanner_version_3(self):
        """All output flags have scanner_version=3."""
        signals = [self._make_signal()]
        flags = _signals_to_flags(
            signals, "H-5", "Test", None,
            {"Eduardo Martinez"}, {},
        )
        for f in flags:
            assert f.scanner_version == 3

    def test_empty_signals(self):
        """Empty signal list returns empty flags."""
        flags = _signals_to_flags([], "H-5", "Test", None, set(), {})
        assert flags == []


# ── Integration: scan_meeting_json with new detectors ───────


class TestScanMeetingJsonIntegration:
    """Test that new detectors integrate into the main scan loop."""

    def test_expenditures_parameter_accepted(self):
        """scan_meeting_json accepts the new expenditures parameter."""
        from conflict_scanner import scan_meeting_json
        result = scan_meeting_json(
            meeting_data={
                "meeting_date": "2026-01-15",
                "meeting_type": "Regular",
                "consent_calendar": {"items": []},
                "action_items": [],
                "housing_authority_items": [],
                "members_present": [],
            },
            contributions=[],
            expenditures=[],
        )
        assert result.total_items_scanned == 0

    def test_temporal_signals_in_main_scan(self):
        """Temporal signals are detected in the main scan loop."""
        from conflict_scanner import scan_meeting_json
        result = scan_meeting_json(
            meeting_data={
                "meeting_date": "2026-01-15",
                "meeting_type": "Regular",
                "consent_calendar": {"items": []},
                "action_items": [
                    {
                        "item_number": "H-5",
                        "title": "Approve contract with Acme Corp",
                        "description": "Contract for consulting services with Acme Corp",
                        "financial_amount": "$50,000",
                        "motions": [
                            {
                                "result": "passed",
                                "votes": [
                                    {"council_member": "Eduardo Martinez", "vote": "aye"},
                                    {"council_member": "Sue Wilson", "vote": "aye"},
                                ],
                            }
                        ],
                    },
                ],
                "housing_authority_items": [],
                "members_present": [
                    {"name": "Eduardo Martinez"},
                    {"name": "Sue Wilson"},
                ],
            },
            contributions=[
                {
                    "donor_name": "Acme Corp",
                    "donor_employer": "",
                    "committee_name": "Martinez for Richmond 2026",
                    "amount": 5000,
                    "date": "2026-02-15",
                    "filing_id": "TC-001",
                    "source": "netfile",
                },
            ],
        )

        temporal_flags = [f for f in result.flags if f.flag_type == "temporal_correlation"]
        assert len(temporal_flags) >= 1

    def test_vendor_expenditure_signals_in_main_scan(self):
        """Vendor-expenditure signals are detected in the main scan loop."""
        from conflict_scanner import scan_meeting_json
        # Use "Acme Construction LLC" which extract_entity_names() cleanly extracts
        result = scan_meeting_json(
            meeting_data={
                "meeting_date": "2026-01-15",
                "meeting_type": "Regular",
                "consent_calendar": {"items": []},
                "action_items": [
                    {
                        "item_number": "H-5",
                        "title": "APPROVE a contract with Acme Construction LLC for road repairs",
                        "description": "Staff recommends approval of contract with Acme Construction LLC",
                        "financial_amount": "$150,000",
                    },
                ],
                "housing_authority_items": [],
                "members_present": [],
            },
            contributions=[
                {
                    "donor_name": "Acme Construction LLC",
                    "donor_employer": "",
                    "committee_name": "Martinez for Richmond 2026",
                    "amount": 5000,
                    "date": "2025-12-01",
                    "filing_id": "VD-001",
                    "source": "netfile",
                },
            ],
            expenditures=[
                {
                    "normalized_vendor": "Acme Construction LLC",
                    "vendor_name": "Acme Construction LLC",
                    "amount": 150000,
                    "fiscal_year": "2025-2026",
                    "department": "Public Works",
                },
            ],
        )

        vendor_flags = [f for f in result.flags if f.flag_type == "donor_vendor_expenditure"]
        assert len(vendor_flags) >= 1
