"""Tests for HTML comment generation."""
import pytest
from conflict_scanner import ConflictFlag, ScanResult
from comment_generator import (
    generate_comment_from_scan,
    generate_html_comment_from_scan,
    MissingDocument,
)


def _make_scan_result(flags=None, clean_items=None, enriched_items=None):
    """Helper to build a ScanResult."""
    return ScanResult(
        meeting_date="2026-02-24",
        meeting_type="regular",
        total_items_scanned=9,
        flags=flags or [],
        vendor_matches=[],
        clean_items=clean_items or ["O.1", "O.2", "O.3"],
        enriched_items=enriched_items or [],
    )


def _make_flag(tier, **overrides):
    """Helper to build a ConflictFlag with sensible defaults."""
    defaults = {
        "agenda_item_number": "O.4.b",
        "agenda_item_title": "Contract with ChargePoint, Inc.",
        "council_member": "Sue Wilson (sitting council member)",
        "flag_type": "campaign_contribution",
        "description": "Jane Doe contributed $1,000.00 to Wilson for Richmond 2024 on 2024-03-15",
        "evidence": ["Source: netfile, Filing ID: 211752889"],
        "confidence": 0.7,
        "legal_reference": "Gov. Code SS 87100-87105, 87300",
        "financial_amount": "$32,900",
        "publication_tier": tier,
    }
    defaults.update(overrides)
    return ConflictFlag(**defaults)


# ── HTML Structure Tests ──────────────────────────────────────


class TestHtmlBasicStructure:
    """HTML output should be valid, self-contained HTML."""

    def test_returns_string_with_html_tags(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "<html" in html
        assert "</html>" in html

    def test_has_head_and_body(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "<head>" in html
        assert "<body" in html

    def test_has_meta_charset(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert 'charset="utf-8"' in html.lower() or "charset=utf-8" in html.lower()

    def test_title_contains_meeting_date(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "<title>" in html
        assert "2026-02-24" in html


# ── Content Parity Tests ─────────────────────────────────────


class TestHtmlContentParity:
    """HTML should contain the same information as plain text."""

    def test_methodology_section_present(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "Methodology" in html or "METHODOLOGY" in html

    def test_meeting_date_present(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "2026-02-24" in html

    def test_contribution_count_present(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "27,035" in html

    def test_clean_items_count_present(self):
        result = _make_scan_result(clean_items=["O.1", "O.2", "O.3"])
        html = generate_html_comment_from_scan(result)
        assert "3" in html  # 3 clean items

    def test_contact_email_present(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "pjfront@gmail.com" in html

    def test_legal_disclaimer_present(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "Government Code" in html or "Gov. Code" in html


# ── Tier Filtering in HTML ────────────────────────────────────


class TestHtmlTierFiltering:
    """HTML should respect the same tier filtering as plain text."""

    def test_tier1_flag_appears(self):
        flag = _make_flag(tier=1)
        result = _make_scan_result(flags=[flag])
        html = generate_html_comment_from_scan(result)
        assert "ChargePoint" in html
        assert "Potential Conflict" in html or "POTENTIAL CONFLICT" in html

    def test_tier2_flag_appears(self):
        flag = _make_flag(tier=2, confidence=0.5)
        result = _make_scan_result(flags=[flag])
        html = generate_html_comment_from_scan(result)
        assert "ChargePoint" in html
        assert "Financial Connection" in html or "FINANCIAL CONNECTION" in html

    def test_tier3_flag_suppressed(self):
        flag = _make_flag(tier=3, confidence=0.3,
                          council_member="Oscar Garcia (not a current council member)")
        result = _make_scan_result(flags=[flag])
        html = generate_html_comment_from_scan(result)
        assert "Oscar Garcia" not in html

    def test_findings_count_in_html(self):
        tier1 = _make_flag(tier=1)
        tier3 = _make_flag(tier=3, confidence=0.3)
        result = _make_scan_result(flags=[tier1, tier3])
        html = generate_html_comment_from_scan(result)
        # Should show findings count of 1 (only tier1 counts, not tier3)
        assert "Findings:" in html
        assert "<strong>1</strong>" in html


# ── Missing Documents in HTML ─────────────────────────────────


class TestHtmlMissingDocuments:
    """Missing document warnings should appear in HTML."""

    def test_missing_doc_appears(self):
        result = _make_scan_result()
        missing = [MissingDocument(
            referenced_in="Item O.4.b",
            document_description="Resolution No. 2026-01",
            expected_location="City Clerk's resolution archive",
            recommendation="Full resolution text should be publicly available",
        )]
        html = generate_html_comment_from_scan(result, missing_docs=missing)
        assert "Resolution No. 2026-01" in html
        assert "City Clerk" in html


# ── HTML Styling Tests ────────────────────────────────────────


class TestHtmlStyling:
    """HTML should have inline CSS for email compatibility."""

    def test_uses_inline_styles(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "style=" in html

    def test_no_external_stylesheets(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert '<link rel="stylesheet"' not in html

    def test_max_width_container(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "max-width" in html

    def test_has_professional_header(self):
        result = _make_scan_result()
        html = generate_html_comment_from_scan(result)
        assert "Richmond Common" in html


# ── Enrichment Info in HTML ───────────────────────────────────


class TestHtmlEnrichment:
    """HTML should show enrichment info when items were enhanced."""

    def test_enriched_count_shown(self):
        result = _make_scan_result(enriched_items=["O.2", "O.3", "O.4.a"])
        html = generate_html_comment_from_scan(result)
        assert "enhanced document scanning" in html.lower() or "enhanced" in html.lower()

    def test_no_enrichment_line_when_zero(self):
        result = _make_scan_result(enriched_items=[])
        html = generate_html_comment_from_scan(result)
        # Should not show "Items with enhanced document scanning: 0"
        assert "enhanced document scanning: 0" not in html.lower()
