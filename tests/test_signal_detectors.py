"""Tests for v3 signal detector functions.

Tests signal_campaign_contribution(), signal_form700_property(),
signal_form700_income(), and helper functions (_compute_temporal_factor,
_compute_financial_factor, _match_type_to_strength, _signals_to_flags).
"""
import pytest
from conflict_scanner import (
    RawSignal,
    ConflictFlag,
    _ScanContext,
    _compute_temporal_factor,
    _compute_financial_factor,
    _match_type_to_strength,
    _GENERIC_BUSINESS_WORDS,
    signal_campaign_contribution,
    signal_form700_property,
    signal_form700_income,
    _signals_to_flags,
    extract_entity_names,
    normalize_text,
    ScanAuditLogger,
)


# ── Helper factories ────────────────────────────────────────


def _make_ctx(**overrides) -> _ScanContext:
    """Build a _ScanContext with sensible defaults."""
    from conflict_scanner import _load_alias_map
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
        meeting_date="2026-03-04",
        city_fips="0660620",
    )
    defaults.update(overrides)
    return _ScanContext(**defaults)


def _make_contribution(**kwargs):
    """Build a contribution dict with defaults."""
    defaults = {
        "donor_name": "", "donor_employer": "", "council_member": "",
        "committee_name": "", "amount": 0, "date": "2026-01-15",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


# ── _compute_temporal_factor ────────────────────────────────


class TestComputeTemporalFactor:
    """Test temporal proximity scoring."""

    def test_within_90_days(self):
        assert _compute_temporal_factor("2026-01-15", "2026-03-04") == 1.0

    def test_within_180_days(self):
        assert _compute_temporal_factor("2025-10-01", "2026-03-04") == 0.8

    def test_within_1_year(self):
        assert _compute_temporal_factor("2025-04-01", "2026-03-04") == 0.6

    def test_within_2_years(self):
        assert _compute_temporal_factor("2024-06-01", "2026-03-04") == 0.4

    def test_beyond_2_years(self):
        assert _compute_temporal_factor("2023-01-01", "2026-03-04") == 0.2

    def test_unparseable_date_returns_neutral(self):
        assert _compute_temporal_factor("not-a-date", "2026-03-04") == 0.5

    def test_empty_date_returns_neutral(self):
        assert _compute_temporal_factor("", "2026-03-04") == 0.5

    def test_alternative_date_format(self):
        # MM/DD/YYYY format
        assert _compute_temporal_factor("01/15/2026", "2026-03-04") == 1.0


# ── _compute_financial_factor ───────────────────────────────


class TestComputeFinancialFactor:
    """Test financial materiality scoring."""

    def test_above_5000(self):
        assert _compute_financial_factor(5000) == 1.0
        assert _compute_financial_factor(10000) == 1.0

    def test_1000_to_4999(self):
        assert _compute_financial_factor(1000) == 0.7
        assert _compute_financial_factor(4999) == 0.7

    def test_500_to_999(self):
        assert _compute_financial_factor(500) == 0.5
        assert _compute_financial_factor(999) == 0.5

    def test_100_to_499(self):
        assert _compute_financial_factor(100) == 0.3
        assert _compute_financial_factor(499) == 0.3

    def test_below_100(self):
        assert _compute_financial_factor(50) == 0.1
        assert _compute_financial_factor(0) == 0.1


# ── _match_type_to_strength ─────────────────────────────────


class TestMatchTypeToStrength:
    """Test match type to strength conversion with specificity penalty."""

    def test_exact_match(self):
        assert _match_type_to_strength("exact") == 1.0

    def test_phrase_match(self):
        assert _match_type_to_strength("phrase") == 0.85

    def test_alias_exact(self):
        assert _match_type_to_strength("alias_exact") == 0.9

    def test_employer_match(self):
        assert _match_type_to_strength("employer_match") == 0.6

    def test_employer_substring(self):
        assert _match_type_to_strength("employer_substring") == 0.5

    def test_unknown_type_defaults_to_half(self):
        assert _match_type_to_strength("unknown_type") == 0.5

    def test_specificity_penalty_all_generic(self):
        """All generic words -> 0.7x penalty."""
        words = {"pacific", "development", "services"}
        strength = _match_type_to_strength("phrase", words)
        # 0.85 * 0.7 = 0.595
        assert strength == pytest.approx(0.595)

    def test_specificity_no_penalty_distinctive(self):
        """50% distinctive words -> no penalty."""
        words = {"rincon", "consultants"}  # rincon is distinctive
        strength = _match_type_to_strength("phrase", words)
        assert strength == 0.85  # no penalty

    def test_specificity_penalty_threshold(self):
        """Exactly 50% distinctive -> no penalty (< 0.5 triggers)."""
        words = {"acme", "services"}  # acme is distinctive, services is generic
        strength = _match_type_to_strength("phrase", words)
        assert strength == 0.85  # 50%, not < 50%, no penalty


# ── signal_campaign_contribution ────────────────────────────


class TestSignalCampaignContribution:
    """Test campaign contribution signal detection."""

    def test_basic_match_produces_signal(self):
        """A donor name appearing in item text produces a signal."""
        ctx = _make_ctx()
        signals = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Contract with Rincon Consultants",
            item_text="Approve Contract with Rincon Consultants for environmental review.",
            original_text="Approve Contract with Rincon Consultants for environmental review.",
            financial="$100,000",
            entities=extract_entity_names("Approve Contract with Rincon Consultants for environmental review."),
            text_words=set(w for w in normalize_text("Approve Contract with Rincon Consultants for environmental review.").split() if len(w) >= 4),
            contributions=[_make_contribution(
                donor_name="Rincon Consultants",
                committee_name="Sue Wilson for Richmond 2024",
                amount=1000.00,
            )],
            ctx=ctx,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "campaign_contribution"
        assert sig.match_strength > 0
        assert sig.temporal_factor > 0
        assert sig.financial_factor > 0
        assert sig.match_details["donor_name"] == "Rincon Consultants"

    def test_government_donor_filtered(self):
        """Government entity donors are filtered out."""
        ctx = _make_ctx()
        signals = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Budget Amendment",
            item_text="Approve Budget Amendment for City of Richmond operations.",
            original_text="Approve Budget Amendment for City of Richmond operations.",
            financial="$500,000",
            entities=["City of Richmond"],
            text_words={"approve", "budget", "amendment", "richmond", "operations"},
            contributions=[_make_contribution(
                donor_name="City of Richmond Finance Department",
                committee_name="Sue Wilson for Richmond 2024",
                amount=5000.00,
            )],
            ctx=ctx,
        )
        assert len(signals) == 0
        assert ctx.filter_counts["filtered_govt_donor"] > 0

    def test_self_donation_filtered(self):
        """Self-donations (donor name in committee name) are filtered."""
        ctx = _make_ctx()
        signals = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Contract with Maier Consulting",
            item_text="Professional services from Cheryl Maier for consulting.",
            original_text="Professional services from Cheryl Maier for consulting.",
            financial="$50,000",
            entities=["Cheryl Maier"],
            text_words={"professional", "services", "cheryl", "maier", "consulting"},
            contributions=[_make_contribution(
                donor_name="Cheryl Maier",
                committee_name="Cheryl Maier for Richmond City Council 2024",
                amount=5000.00,
            )],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_materiality_threshold(self):
        """Contributions below $100 total are filtered out."""
        ctx = _make_ctx()
        signals = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Contract with Rincon Consultants",
            item_text="Contract with Rincon Consultants for review.",
            original_text="Contract with Rincon Consultants for review.",
            financial="$50,000",
            entities=["Rincon Consultants"],
            text_words={"contract", "rincon", "consultants", "review"},
            contributions=[_make_contribution(
                donor_name="Rincon Consultants",
                committee_name="Sue Wilson for Richmond 2024",
                amount=50.00,
            )],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_aggregation_multiple_contributions(self):
        """Multiple contributions from same donor aggregate into one signal."""
        ctx = _make_ctx()
        contribs = [
            _make_contribution(
                donor_name="Rincon Consultants",
                committee_name="Sue Wilson for Richmond 2024",
                amount=200.00,
                date="2026-01-10",
            ),
            _make_contribution(
                donor_name="Rincon Consultants",
                committee_name="Sue Wilson for Richmond 2024",
                amount=300.00,
                date="2026-02-15",
            ),
        ]
        signals = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Contract with Rincon Consultants",
            item_text="Contract with Rincon Consultants for review.",
            original_text="Contract with Rincon Consultants for review.",
            financial="$50,000",
            entities=["Rincon Consultants"],
            text_words={"contract", "rincon", "consultants", "review"},
            contributions=contribs,
            ctx=ctx,
        )
        assert len(signals) == 1
        # Total should be $500
        assert signals[0].match_details["total_amount"] == 500.00

    def test_employer_match(self):
        """Donor employer matching against agenda entities."""
        ctx = _make_ctx()
        signals = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Contract with Gallagher Benefit Services for Benefits",
            item_text="Annual benefits contract with Gallagher Benefit Services.",
            original_text="Annual benefits contract with Gallagher Benefit Services.",
            financial="$200,000",
            entities=extract_entity_names("Annual benefits contract with Gallagher Benefit Services."),
            text_words=set(w for w in normalize_text(
                "Annual benefits contract with Gallagher Benefit Services."
            ).split() if len(w) >= 4),
            contributions=[_make_contribution(
                donor_name="Sarah Whitfield",
                donor_employer="Gallagher Benefit Services",
                committee_name="Sue Wilson for Richmond 2024",
                amount=500.00,
            )],
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].match_details["match_type"] in ("employer_match", "employer_substring")

    def test_dedup_across_items(self):
        """Same contribution shouldn't be flagged twice across items."""
        ctx = _make_ctx()
        contrib = [_make_contribution(
            donor_name="Rincon Consultants",
            committee_name="Sue Wilson for Richmond 2024",
            amount=1000.00,
        )]
        # First call
        signals1 = signal_campaign_contribution(
            item_num="V.1.a",
            item_title="Approve Contract with Rincon Consultants",
            item_text="Contract with Rincon Consultants for review.",
            original_text="Contract with Rincon Consultants for review.",
            financial="$50,000",
            entities=["Rincon Consultants"],
            text_words={"contract", "rincon", "consultants", "review"},
            contributions=contrib,
            ctx=ctx,
        )
        assert len(signals1) == 1
        # Second call with same context (seen_contributions already has it)
        signals2 = signal_campaign_contribution(
            item_num="V.2.a",
            item_title="Approve Additional Work from Rincon Consultants",
            item_text="Additional environmental review from Rincon Consultants.",
            original_text="Additional environmental review from Rincon Consultants.",
            financial="$25,000",
            entities=["Rincon Consultants"],
            text_words={"additional", "environmental", "review", "rincon", "consultants"},
            contributions=contrib,
            ctx=ctx,
        )
        assert len(signals2) == 0  # already seen


# ── signal_form700_property ─────────────────────────────────


class TestSignalForm700Property:
    """Test Form 700 real property signal detection."""

    def test_basic_property_signal(self):
        """Real property interest on land-use item produces signal."""
        form700 = [{
            "council_member": "Cesar Zepeda",
            "interest_type": "real_property",
            "description": "123 Main St, Richmond CA",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        signals = signal_form700_property(
            item_num="V.1.a",
            item_title="Approve Rezoning of 200 Main St",
            item_text="Approve Rezoning of 200 Main St for mixed use development.",
            financial="$0",
            form700_interests=form700,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "form700_real_property"
        assert sig.council_member == "Cesar Zepeda"
        assert sig.match_strength == 0.4  # street-level match
        assert sig.temporal_factor == 0.5  # neutral

    def test_non_property_interest_ignored(self):
        """Income/investment interests not picked up by property detector."""
        form700 = [{
            "council_member": "Sue Wilson",
            "interest_type": "income",
            "description": "Consulting income from ABC Corp",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        signals = signal_form700_property(
            item_num="V.1.a",
            item_title="Approve Rezoning",
            item_text="Approve Rezoning for development.",
            financial="$0",
            form700_interests=form700,
        )
        assert len(signals) == 0


# ── signal_form700_income ───────────────────────────────────


class TestSignalForm700Income:
    """Test Form 700 income/investment signal detection."""

    def test_income_match_produces_signal(self):
        """Income source matching an agenda entity produces signal."""
        form700 = [{
            "council_member": "Sue Wilson",
            "interest_type": "income",
            "description": "Rincon Consultants",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        entities = ["Rincon Consultants"]
        signals = signal_form700_income(
            item_num="V.1.a",
            item_title="Approve Contract with Rincon Consultants",
            item_text="Contract with Rincon Consultants for review.",
            financial="$100,000",
            entities=entities,
            form700_interests=form700,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "form700_income"
        assert sig.council_member == "Sue Wilson"
        assert sig.match_details["matched_entity"] == "Rincon Consultants"

    def test_investment_match_produces_signal(self):
        """Investment source matching an entity also works."""
        form700 = [{
            "council_member": "Cesar Zepeda",
            "interest_type": "investment",
            "description": "Gallagher Benefit Services",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        entities = ["Gallagher Benefit Services"]
        signals = signal_form700_income(
            item_num="V.1.a",
            item_title="Approve Contract with Gallagher Benefit Services",
            item_text="Benefits administration by Gallagher Benefit Services.",
            financial="$200,000",
            entities=entities,
            form700_interests=form700,
        )
        assert len(signals) == 1
        assert signals[0].signal_type == "form700_investment"

    def test_no_match_no_signal(self):
        """Non-matching entities produce no signal."""
        form700 = [{
            "council_member": "Sue Wilson",
            "interest_type": "income",
            "description": "Unrelated Company XYZ",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        entities = ["Rincon Consultants"]
        signals = signal_form700_income(
            item_num="V.1.a",
            item_title="Approve Contract with Rincon Consultants",
            item_text="Contract with Rincon Consultants for review.",
            financial="$100,000",
            entities=entities,
            form700_interests=form700,
        )
        assert len(signals) == 0

    def test_short_description_ignored(self):
        """Very short interest descriptions (<=4 chars) are skipped."""
        form700 = [{
            "council_member": "Sue Wilson",
            "interest_type": "income",
            "description": "ABC",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        entities = ["ABC Corporation"]
        signals = signal_form700_income(
            item_num="V.1.a",
            item_title="Contract with ABC Corporation",
            item_text="Contract with ABC Corporation.",
            financial="$50,000",
            entities=entities,
            form700_interests=form700,
        )
        assert len(signals) == 0


# ── _signals_to_flags ───────────────────────────────────────


class TestSignalsToFlags:
    """Test conversion from RawSignals to ConflictFlags."""

    def test_basic_conversion(self):
        """A single signal converts to one flag."""
        signal = RawSignal(
            signal_type="campaign_contribution",
            council_member="Sue Wilson (sitting council member)",
            agenda_item_number="V.1.a",
            match_strength=0.85,
            temporal_factor=1.0,
            financial_factor=0.7,
            description="Donor X contributed $1000 to committee Y",
            evidence=["Source: netfile, Filing ID: 123"],
            legal_reference="Gov. Code SS 87100",
            financial_amount="$50,000",
            match_details={"is_sitting": True},
        )
        flags = _signals_to_flags(
            signals=[signal],
            item_num="V.1.a",
            item_title="Approve Contract",
            financial="$50,000",
            current_officials={"Sue Wilson"},
            alias_groups={},
        )
        assert len(flags) == 1
        flag = flags[0]
        assert isinstance(flag, ConflictFlag)
        assert flag.scanner_version == 3
        assert flag.confidence_factors is not None
        assert flag.confidence > 0
        assert flag.publication_tier in (1, 2, 3, 4)

    def test_sitting_vs_non_sitting(self):
        """Non-sitting signals get lower confidence via sitting_multiplier."""
        base_kwargs = dict(
            signal_type="campaign_contribution",
            agenda_item_number="V.1.a",
            match_strength=0.85,
            temporal_factor=1.0,
            financial_factor=0.7,
            description="test",
            evidence=[],
            legal_reference="test",
        )
        sitting_sig = RawSignal(
            council_member="Sue Wilson (sitting council member)",
            match_details={"is_sitting": True},
            **base_kwargs,
        )
        non_sitting_sig = RawSignal(
            council_member="Oscar Garcia (not a current council member)",
            match_details={"is_sitting": False},
            **base_kwargs,
        )
        sitting_flags = _signals_to_flags(
            [sitting_sig], "V.1.a", "Test", None, {"Sue Wilson"}, {}
        )
        non_sitting_flags = _signals_to_flags(
            [non_sitting_sig], "V.1.a", "Test", None, {"Sue Wilson"}, {}
        )
        assert sitting_flags[0].confidence > non_sitting_flags[0].confidence

    def test_hedge_clause_applied(self):
        """Flags below 0.85 confidence should include hedge clause."""
        signal = RawSignal(
            signal_type="campaign_contribution",
            council_member="Sue Wilson",
            agenda_item_number="V.1.a",
            match_strength=0.5,
            temporal_factor=0.5,
            financial_factor=0.3,
            description="Some contribution",
            evidence=[],
            legal_reference="test",
            match_details={"is_sitting": True},
        )
        flags = _signals_to_flags(
            [signal], "V.1.a", "Test", None, {"Sue Wilson"}, {}
        )
        assert "Other explanations may exist" in flags[0].description

    def test_form700_signal_conversion(self):
        """Form 700 signals also convert correctly."""
        signal = RawSignal(
            signal_type="form700_real_property",
            council_member="Cesar Zepeda",
            agenda_item_number="V.1.a",
            match_strength=0.4,
            temporal_factor=0.5,
            financial_factor=0.3,
            description="Zepeda Form 700 lists real property",
            evidence=["Form 700, Schedule A-2"],
            legal_reference="Gov. Code S 87100",
            match_details={},
        )
        flags = _signals_to_flags(
            [signal], "V.1.a", "Approve Rezoning", None,
            {"Cesar Zepeda"}, {}
        )
        assert len(flags) == 1
        assert flags[0].flag_type == "form700_real_property"
        assert flags[0].scanner_version == 3
