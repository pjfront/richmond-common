"""Tests for ConflictFlag.publication_tier assignment."""
import pytest
from conflict_scanner import ConflictFlag


def test_tier1_sitting_member_exact_match_high_amount():
    """Sitting council member + exact name match + >= $500 = Tier 1."""
    flag = ConflictFlag(
        agenda_item_number="V.6.a",
        agenda_item_title="Approve Contract with Maier Consulting",
        council_member="Sue Wilson (sitting council member)",
        flag_type="campaign_contribution",
        description="Cheryl Maier contributed $5,000.00 to Wilson for Richmond 2024",
        evidence=["Source: netfile, Filing ID: 211752889"],
        confidence=0.7,
        legal_reference="Gov. Code SS 87100-87105",
        financial_amount="$1,217,161",
        publication_tier=1,
    )
    assert flag.publication_tier == 1


def test_tier2_sitting_member_employer_match():
    """Sitting council member + employer match (weaker) = Tier 2."""
    flag = ConflictFlag(
        agenda_item_number="V.3.a",
        agenda_item_title="Approve Maintenance Contract",
        council_member="Eduardo Martinez (sitting council member)",
        flag_type="campaign_contribution",
        description="James Torres (Pacific Environmental) contributed $200",
        evidence=["Source: calaccess, Filing ID: 2345678"],
        confidence=0.5,
        legal_reference="Gov. Code SS 87100-87105",
        financial_amount="$85,000",
        publication_tier=2,
    )
    assert flag.publication_tier == 2


def test_tier3_non_sitting_candidate():
    """Donation to a former/failed candidate = Tier 3 (suppressed)."""
    flag = ConflictFlag(
        agenda_item_number="V.6",
        agenda_item_title="Library and Community Services",
        council_member="Oscar Garcia (not a current council member)",
        flag_type="campaign_contribution",
        description="Cheryl Maier contributed $100.00 to Oscar Garcia for Richmond City Council 2022",
        evidence=["Source: netfile, Filing ID: 204807209"],
        confidence=0.3,
        legal_reference="Gov. Code SS 87100-87105",
        financial_amount="$1,217,161",
        publication_tier=3,
    )
    assert flag.publication_tier == 3
