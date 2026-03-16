"""Tests for B.45/B.53 signal detectors: permit-donor and license-donor cross-references.

Tests signal_permit_donor() and signal_license_donor() — the two new detectors
that cross-reference regulatory data (from B.44 Socrata tables) against
campaign contributions to detect political influence patterns.
"""
import pytest
from conflict_scanner import (
    RawSignal,
    _ScanContext,
    signal_permit_donor,
    signal_license_donor,
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
        "committee_name": "", "amount": 0, "date": "2026-01-10",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


def _make_permit(**kwargs):
    """Build a permit dict with defaults."""
    defaults = {
        "applied_by": "",
        "permit_type": "Building",
        "permit_no": "BP-2025-001",
        "job_value": 0.0,
        "applied_date": "2025-06-15",
        "status": "Issued",
        "description": "Commercial renovation",
    }
    defaults.update(kwargs)
    return defaults


def _make_license(**kwargs):
    """Build a business license dict with defaults."""
    defaults = {
        "company": "",
        "normalized_company": "",
        "company_dba": "",
        "business_type": "General",
        "status": "Active",
        "license_issued": "2024-01-01",
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


# ── signal_permit_donor ────────────────────────────────────


class TestSignalPermitDonor:
    """Test permit-applicant → campaign-donor cross-reference detection."""

    def test_basic_match_produces_signal(self):
        """A permit applicant who is also a donor and appears in agenda text."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc", job_value=250000),
        ]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=1000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review Contract",
            item_text="Approve contract with Rincon Consultants Inc for environmental review services.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "permit_donor"
        assert sig.council_member == "Sue Wilson"
        assert sig.match_strength > 0
        assert sig.financial_factor > 0
        assert "Rincon Consultants Inc" in sig.description
        assert "permit" in sig.description.lower()
        assert sig.match_details["is_sitting"] is True
        assert sig.match_details["permit_count"] == 1
        assert sig.match_details["contribution_amount"] == 1000

    def test_no_match_when_applicant_not_in_text(self):
        """No signal when permit applicant doesn't appear in agenda text."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=1000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Park Improvement Project",
            item_text="Approve park improvement project for MLK Park renovation.",
            financial="$50,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_no_match_when_no_contribution(self):
        """No signal when permit applicant is not a campaign donor."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc"),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=[_make_permit(applied_by="Rincon Consultants Inc")],
            contributions=[],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_materiality_threshold(self):
        """Contributions below $100 are filtered out."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=50,  # Below $100 materiality
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_short_applicant_name_filtered(self):
        """Applicant names shorter than 10 chars are excluded from gazetteer."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="ABC Inc"),  # 7 chars
        ]
        contributions = [
            _make_contribution(
                donor_name="ABC Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=5000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Contract with ABC Inc",
            item_text="Approve contract with ABC Inc for services.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_employer_match_cross_reference(self):
        """Permit applicant matched via donor employer field."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc", job_value=500000),
        ]
        contributions = [
            _make_contribution(
                donor_name="John Smith",
                donor_employer="Rincon Consultants Inc",
                council_member="Eduardo Martinez",
                committee_name="Martinez for Richmond 2026",
                amount=2000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review Contract",
            item_text="Approve contract with Rincon Consultants Inc for services.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.council_member == "Eduardo Martinez"
        assert "employer" in sig.match_details["donor_match_type"]

    def test_deduplication(self):
        """Same applicant-council_member-item_num deduplicates to one signal."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc"),
            _make_permit(applied_by="Rincon Consultants Inc", permit_no="BP-2025-002"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=1000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1

    def test_multiple_permits_counted(self):
        """Multiple permits from the same applicant are counted in evidence."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc", permit_no="BP-2025-001", job_value=100000),
            _make_permit(applied_by="Rincon Consultants Inc", permit_no="BP-2025-002", job_value=200000),
        ]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=1000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].match_details["permit_count"] == 2
        assert signals[0].match_details["max_job_value"] == 200000

    def test_job_value_in_financial_factor(self):
        """Job value from permits influences financial factor."""
        ctx = _make_ctx()
        permits = [
            _make_permit(applied_by="Rincon Consultants Inc", job_value=500000),
        ]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=200,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        # Financial factor should use max(contribution, job_value) = $500K -> 1.0
        assert signals[0].financial_factor == 1.0

    def test_legal_reference_includes_ab571(self):
        """Legal reference cites AB 571 (Gov. Code § 84308) for permit seekers."""
        ctx = _make_ctx()
        permits = [_make_permit(applied_by="Rincon Consultants Inc")]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=500,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        assert "84308" in signals[0].legal_reference

    def test_former_official_is_not_sitting(self):
        """Former officials get is_sitting=False."""
        ctx = _make_ctx()
        permits = [_make_permit(applied_by="Rincon Consultants Inc")]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Ben Choi",
                committee_name="Choi for Richmond 2020",
                amount=1000,
            ),
        ]
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Approve contract with Rincon Consultants Inc for review.",
            financial="$100,000",
            permits=permits,
            contributions=contributions,
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].match_details["is_sitting"] is False

    def test_empty_permits_returns_empty(self):
        """Empty permits list returns no signals."""
        ctx = _make_ctx()
        signals = signal_permit_donor(
            item_num="V.1.a",
            item_title="Environmental Review",
            item_text="Some agenda text here.",
            financial="$100,000",
            permits=[],
            contributions=[_make_contribution(donor_name="Acme Corp", amount=1000)],
            ctx=ctx,
        )
        assert len(signals) == 0


# ── signal_license_donor ────────────────────────────────────


class TestSignalLicenseDonor:
    """Test license-holder → campaign-donor/vendor cross-reference detection."""

    def test_basic_match_produces_signal(self):
        """A licensed business that is also a donor and appears in agenda text."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=2000,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvement Contract",
            item_text="Approve contract with Pacific Construction Group for street improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == "license_donor"
        assert sig.council_member == "Sue Wilson"
        assert "Pacific Construction Group" in sig.description
        assert "business license" in sig.description.lower()
        assert sig.match_details["is_sitting"] is True
        assert sig.match_details["license_count"] == 1

    def test_dba_name_match(self):
        """Match on DBA (doing business as) name."""
        ctx = _make_ctx()
        licenses = [
            _make_license(
                company="John Doe Enterprises LLC",
                normalized_company="john doe enterprises llc",
                company_dba="Richmond Auto Repair Center",
            ),
        ]
        contributions = [
            _make_contribution(
                donor_name="Richmond Auto Repair Center",
                council_member="Claudia Jimenez",
                committee_name="Jimenez for Richmond 2024",
                amount=500,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.3.a",
            item_title="Auto Shop Zone Variance",
            item_text="Consider zone variance for Richmond Auto Repair Center at 123 Main St.",
            financial=None,
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 1

    def test_no_match_when_company_not_in_text(self):
        """No signal when licensed company doesn't appear in agenda text."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=2000,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Park Renovation",
            item_text="Approve park renovation at Marina Bay development area.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_vendor_match_boosts_strength(self):
        """When company is also an expenditure vendor, match strength gets a boost."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=2000,
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="pacific construction group",
                vendor_name="Pacific Construction Group",
                amount=150000,
            ),
        ]

        # Without vendor match
        signals_no_vendor = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=_make_ctx(),
        )

        # With vendor match
        signals_with_vendor = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=expenditures,
            ctx=_make_ctx(),
        )

        assert len(signals_no_vendor) == 1
        assert len(signals_with_vendor) == 1
        # Vendor match should boost match strength
        assert signals_with_vendor[0].match_strength >= signals_no_vendor[0].match_strength
        assert signals_with_vendor[0].match_details["vendor_match"] is True
        assert signals_with_vendor[0].match_details["total_expenditure"] == 150000

    def test_vendor_description_includes_expenditure(self):
        """Description mentions city expenditures when vendor match exists."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=2000,
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="pacific construction group",
                vendor_name="Pacific Construction Group",
                amount=150000,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=expenditures,
            ctx=ctx,
        )
        assert len(signals) == 1
        assert "city expenditures" in signals[0].description.lower()

    def test_materiality_threshold(self):
        """Contributions below $100 are filtered out."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=50,  # Below $100
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_short_company_name_filtered(self):
        """Company names shorter than 10 chars are excluded from gazetteer."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Acme Inc", normalized_company="acme inc"),  # 8 chars
        ]
        contributions = [
            _make_contribution(
                donor_name="Acme Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=5000,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Contract with Acme Inc",
            item_text="Approve contract with Acme Inc for services.",
            financial="$100,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_deduplication(self):
        """Same company-council_member-item deduplicates to one signal."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group",
                          business_type="Contractor"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=2000,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 1

    def test_employer_match(self):
        """License holder matched via donor employer field."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Jane Doe",
                donor_employer="Pacific Construction Group",
                council_member="Eduardo Martinez",
                committee_name="Martinez for Richmond 2026",
                amount=1500,
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 1
        assert signals[0].council_member == "Eduardo Martinez"
        assert "employer" in signals[0].match_details["donor_match_type"]

    def test_empty_licenses_returns_empty(self):
        """Empty licenses list returns no signals."""
        ctx = _make_ctx()
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Some Item",
            item_text="Some agenda text here.",
            financial="$100,000",
            licenses=[],
            contributions=[_make_contribution(donor_name="Acme Corp", amount=1000)],
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_empty_contributions_and_expenditures_returns_empty(self):
        """No contributions AND no expenditures returns no signals."""
        ctx = _make_ctx()
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group.",
            financial="$500,000",
            licenses=[_make_license(company="Pacific Construction Group",
                                     normalized_company="pacific construction group")],
            contributions=[],
            expenditures=[],
            ctx=ctx,
        )
        assert len(signals) == 0

    def test_financial_factor_uses_max_amount(self):
        """Financial factor uses max of contribution vs expenditure total."""
        ctx = _make_ctx()
        licenses = [
            _make_license(company="Pacific Construction Group", normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=200,  # Small contribution
            ),
        ]
        expenditures = [
            _make_expenditure(
                normalized_vendor="pacific construction group",
                vendor_name="Pacific Construction Group",
                amount=50000,  # Large expenditure
            ),
        ]
        signals = signal_license_donor(
            item_num="V.2.a",
            item_title="Street Improvements",
            item_text="Approve contract with Pacific Construction Group for improvements.",
            financial="$500,000",
            licenses=licenses,
            contributions=contributions,
            expenditures=expenditures,
            ctx=ctx,
        )
        assert len(signals) == 1
        # $50K -> financial_factor should be 1.0 (>= $5000)
        assert signals[0].financial_factor == 1.0


# ── Integration: scan_meeting_json with new detectors ────────


class TestScanMeetingJsonWithPermitsLicenses:
    """Test that scan_meeting_json correctly integrates the new detectors."""

    def test_permits_wired_into_scan(self):
        """Permits are passed through to signal_permit_donor in scan_meeting_json."""
        from conflict_scanner import scan_meeting_json

        meeting_data = {
            "meeting_date": "2026-01-15",
            "meeting_type": "regular",
            "members_present": [{"name": "Sue Wilson"}, {"name": "Eduardo Martinez"}],
            "consent_calendar": {"items": []},
            "action_items": [
                {
                    "item_number": "H-1",
                    "title": "Approve Contract with Rincon Consultants Inc",
                    "description": "Approve contract with Rincon Consultants Inc for environmental review.",
                    "financial_amount": "$200,000",
                },
            ],
            "housing_authority_items": [],
        }
        permits = [_make_permit(applied_by="Rincon Consultants Inc", job_value=300000)]
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants Inc",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=1000,
            ),
        ]

        result = scan_meeting_json(
            meeting_data=meeting_data,
            contributions=contributions,
            permits=permits,
        )

        # Should produce at least one flag of type permit_donor
        permit_flags = [f for f in result.flags if f.flag_type == "permit_donor"]
        assert len(permit_flags) >= 1

    def test_licenses_wired_into_scan(self):
        """Licenses are passed through to signal_license_donor in scan_meeting_json."""
        from conflict_scanner import scan_meeting_json

        meeting_data = {
            "meeting_date": "2026-01-15",
            "meeting_type": "regular",
            "members_present": [{"name": "Sue Wilson"}, {"name": "Eduardo Martinez"}],
            "consent_calendar": {"items": []},
            "action_items": [
                {
                    "item_number": "H-2",
                    "title": "Approve Contract with Pacific Construction Group",
                    "description": "Approve contract with Pacific Construction Group for road work.",
                    "financial_amount": "$500,000",
                },
            ],
            "housing_authority_items": [],
        }
        licenses = [
            _make_license(company="Pacific Construction Group",
                          normalized_company="pacific construction group"),
        ]
        contributions = [
            _make_contribution(
                donor_name="Pacific Construction Group",
                council_member="Sue Wilson",
                committee_name="Wilson for Richmond 2024",
                amount=2000,
            ),
        ]

        result = scan_meeting_json(
            meeting_data=meeting_data,
            contributions=contributions,
            licenses=licenses,
        )

        license_flags = [f for f in result.flags if f.flag_type == "license_donor"]
        assert len(license_flags) >= 1

    def test_backward_compatible_no_permits_no_licenses(self):
        """Scan works identically without permits or licenses (backward compatible)."""
        from conflict_scanner import scan_meeting_json

        meeting_data = {
            "meeting_date": "2026-01-15",
            "meeting_type": "regular",
            "members_present": [{"name": "Sue Wilson"}],
            "consent_calendar": {"items": []},
            "action_items": [
                {
                    "item_number": "H-1",
                    "title": "Budget Approval",
                    "description": "Approve the 2026 operating budget.",
                    "financial_amount": "$50,000,000",
                },
            ],
            "housing_authority_items": [],
        }
        # No permits, no licenses, no contributions = no flags
        result = scan_meeting_json(
            meeting_data=meeting_data,
            contributions=[],
        )
        assert len(result.flags) == 0
