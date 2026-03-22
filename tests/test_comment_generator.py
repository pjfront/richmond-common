"""Tests for comment generator redesign."""
import pytest
from conflict_scanner import ConflictFlag, ScanResult
from comment_generator import generate_comment_from_scan, MissingDocument


def _make_scan_result(flags=None, clean_items=None):
    """Helper to build a ScanResult."""
    return ScanResult(
        meeting_date="2026-02-17",
        meeting_type="regular",
        total_items_scanned=27,
        flags=flags or [],
        vendor_matches=[],
        clean_items=clean_items or [],
        enriched_items=[],
    )


def _make_flag(tier, **overrides):
    """Helper to build a ConflictFlag with sensible defaults."""
    defaults = {
        "agenda_item_number": "V.1.a",
        "agenda_item_title": "Approve Contract with Acme Corp",
        "council_member": "Sue Wilson (sitting council member)",
        "flag_type": "campaign_contribution",
        "description": "John Doe contributed $5,000.00 to Wilson for Richmond 2024 on 2024-01-06",
        "evidence": ["Source: netfile, Filing ID: 211752889"],
        "confidence": 0.7,
        "legal_reference": "Gov. Code SS 87100-87105, 87300",
        "financial_amount": "$500,000",
        "publication_tier": tier,
    }
    defaults.update(overrides)
    return ConflictFlag(**defaults)


class TestTierFiltering:
    """Comment generator should only include Tier 1 and Tier 2 findings."""

    def test_tier1_appears_in_output(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "POTENTIAL CONFLICTS OF INTEREST" in comment
        assert "Acme Corp" in comment

    def test_tier2_appears_in_separate_section(self):
        flag = _make_flag(tier=2, confidence=0.5)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "ADDITIONAL FINANCIAL CONNECTIONS" in comment
        assert "Acme Corp" in comment

    def test_tier3_suppressed_from_output(self):
        flag = _make_flag(
            tier=3,
            confidence=0.3,
            council_member="Oscar Garcia (not a current council member)",
        )
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Oscar Garcia" not in comment
        assert "POTENTIAL CONFLICTS" not in comment

    def test_mixed_tiers_in_correct_sections(self):
        tier1 = _make_flag(tier=1, agenda_item_number="V.1.a",
                           agenda_item_title="Big Contract with AlphaCo")
        tier2 = _make_flag(tier=2, agenda_item_number="V.3.a",
                           agenda_item_title="Small Contract with BetaCo",
                           confidence=0.5)
        tier3 = _make_flag(tier=3, agenda_item_number="V.6",
                           agenda_item_title="Suppressed Item",
                           confidence=0.3)
        result = _make_scan_result(flags=[tier1, tier2, tier3])
        comment = generate_comment_from_scan(result)
        assert "AlphaCo" in comment
        assert "BetaCo" in comment
        assert "Suppressed Item" not in comment


class TestNarrativeFormat:
    """Comment should read as prose, not code output."""

    def test_no_raw_confidence_scores(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Confidence:" not in comment
        assert "70%" not in comment

    def test_no_evidence_bullet_list(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Evidence:" not in comment

    def test_item_title_in_plain_english(self):
        flag = _make_flag(tier=1, agenda_item_title="Approve Contract with Acme Corp for Consulting Services")
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        assert "Approve Contract with Acme Corp for Consulting Services" in comment

    def test_legal_context_in_plain_english(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        comment = generate_comment_from_scan(result)
        # Should contain plain English legal explanation
        assert "Gov. Code" in comment or "Political Reform Act" in comment


class TestCleanItemsSummary:
    """Clean items should show summary count, not item numbers."""

    def test_clean_items_shows_count(self):
        result = _make_scan_result(
            clean_items=["V.1", "V.2", "V.3", "V.4", "V.5"],
        )
        comment = generate_comment_from_scan(result)
        assert "5 additional agenda items were scanned" in comment
        # Should NOT list individual item numbers
        assert "V.1, V.2" not in comment


class TestEmailPlaceholder:
    """Email should be filled in, not placeholder."""

    def test_contact_email_present(self):
        result = _make_scan_result()
        comment = generate_comment_from_scan(result)
        assert "hello@richmondcommon.org" in comment
        assert "[email]" not in comment
