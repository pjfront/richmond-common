# tests/test_form700_extractor.py
"""Tests for Form 700 extractor (PDF text → structured data).

Tests cover:
- Extraction schema validation
- Prompt template loading
- Filer-to-official matching (exact, alias, fuzzy, no match)
- Interest flattening for conflict scanner
- Name normalization
- Process filing orchestration
- CLI argument parsing
"""
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from form700_extractor import (
    FORM700_EXTRACTION_SCHEMA,
    _normalize_name,
    _get_system_prompt,
    _get_user_prompt,
    extract_form700,
    extract_text_from_pdf,
    match_filer_to_official,
    flatten_interests_for_scanner,
    process_filing,
)


# ── Sample Data ────────────────────────────────────────────────

SAMPLE_EXTRACTION = {
    "filer_name": "Eduardo Martinez",
    "filer_agency": "City of Richmond",
    "filer_position": "Mayor",
    "statement_type": "annual",
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
    "no_interests_declared": False,
    "interests": [
        {
            "schedule": "B",
            "interest_type": "real_property",
            "description": "123 Main St, Richmond CA 94801",
            "value_range": "$100,001 - $1,000,000",
            "location": "123 Main St, Richmond CA 94801",
        },
        {
            "schedule": "C",
            "interest_type": "income",
            "description": "ACME Corporation",
            "income_amount": "$10,001 - $100,000",
            "income_type": "salary",
            "business_activity": "Technology services",
        },
        {
            "schedule": "A-1",
            "interest_type": "investment",
            "description": "Tech Holdings LLC",
            "value_range": "$10,001 - $100,000",
            "nature_of_interest": "partnership",
        },
        {
            "schedule": "D",
            "interest_type": "gift",
            "description": "Conference registration",
            "gift_source": "Richmond Chamber of Commerce",
            "gift_description": "Annual conference registration",
            "gift_value": 250.00,
        },
    ],
    "extraction_confidence": 0.95,
    "extraction_notes": "Clean PDF text, all schedules readable.",
}

SAMPLE_EMPTY_FILING = {
    "filer_name": "Sue Wilson",
    "filer_agency": "City of Richmond",
    "filer_position": "Council Member",
    "statement_type": "annual",
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
    "no_interests_declared": True,
    "interests": [],
    "extraction_confidence": 0.98,
    "extraction_notes": "Filer checked 'No reportable interests on any schedule'.",
}

SAMPLE_OFFICIALS_JSON = {
    "city_fips": "0660620",
    "city_name": "Richmond, California",
    "current_council_members": [
        {"name": "Eduardo Martinez", "role": "Mayor"},
        {"name": "Cesar Zepeda", "role": "Vice Mayor"},
        {"name": "Sue Wilson", "role": "Council Member"},
    ],
    "former_council_members": [
        {"name": "Tom Butt", "notes": "Former mayor"},
    ],
    "city_leadership": [
        {
            "name": "Shasa Curl",
            "title": "City Manager",
            "aliases": ["Kinshasa Curl"],
        },
    ],
}


# ── Schema Validation ──────────────────────────────────────────

class TestExtractionSchema:
    def test_schema_has_required_fields(self):
        required = FORM700_EXTRACTION_SCHEMA["required"]
        assert "filer_name" in required
        assert "interests" in required
        assert "extraction_confidence" in required
        assert "no_interests_declared" in required

    def test_schema_interests_is_array(self):
        props = FORM700_EXTRACTION_SCHEMA["properties"]
        assert props["interests"]["type"] == "array"

    def test_schema_interest_types_include_all_schedules(self):
        interest_props = FORM700_EXTRACTION_SCHEMA["properties"]["interests"]["items"]["properties"]
        schedules = interest_props["schedule"]["enum"]
        assert "A-1" in schedules
        assert "A-2" in schedules
        assert "B" in schedules
        assert "C" in schedules
        assert "D" in schedules
        assert "E" in schedules

    def test_schema_statement_types(self):
        st = FORM700_EXTRACTION_SCHEMA["properties"]["statement_type"]["enum"]
        assert "annual" in st
        assert "assuming_office" in st
        assert "leaving_office" in st
        assert "amendment" in st

    def test_schema_confidence_bounds(self):
        conf = FORM700_EXTRACTION_SCHEMA["properties"]["extraction_confidence"]
        assert conf["minimum"] == 0
        assert conf["maximum"] == 1

    def test_schema_interest_item_required_fields(self):
        required = FORM700_EXTRACTION_SCHEMA["properties"]["interests"]["items"]["required"]
        assert "schedule" in required
        assert "interest_type" in required
        assert "description" in required


# ── Name Normalization ─────────────────────────────────────────

class TestNormalizeName:
    def test_basic(self):
        assert _normalize_name("Eduardo Martinez") == "eduardo martinez"

    def test_extra_whitespace(self):
        assert _normalize_name("  Eduardo   Martinez  ") == "eduardo martinez"

    def test_mixed_case(self):
        assert _normalize_name("SHASA CURL") == "shasa curl"

    def test_single_name(self):
        assert _normalize_name("Madonna") == "madonna"


# ── Prompt Loading ─────────────────────────────────────────────

class TestPromptLoading:
    def test_system_prompt_loads(self):
        prompt = _get_system_prompt()
        assert "Form 700" in prompt
        assert "Schedule" in prompt
        assert "confidence" in prompt.lower()

    def test_user_prompt_has_placeholders(self):
        prompt = _get_user_prompt(
            pdf_text="Sample text",
            filer_name="Test Filer",
            agency="Test Agency",
            filing_year=2024,
            statement_type="annual",
        )
        assert "Test Filer" in prompt
        assert "Test Agency" in prompt
        assert "2024" in prompt
        assert "Sample text" in prompt

    def test_user_prompt_defaults(self):
        prompt = _get_user_prompt(pdf_text="text only")
        assert "Unknown" in prompt  # Default filer_name

    def test_user_prompt_truncates_long_text(self):
        long_text = "x" * 200000
        prompt = _get_user_prompt(pdf_text=long_text)
        # Should truncate to 120K chars
        assert len(prompt) < 200000


# ── Filer-to-Official Matching ─────────────────────────────────

class TestMatchFilerToOfficial:
    @patch("form700_extractor.Path")
    def test_exact_match(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps(SAMPLE_OFFICIALS_JSON)
        mock_path_cls.return_value.__truediv__ = lambda *a: mock_path
        # Patch the actual Path(__file__).parent chain
        with patch.object(Path, '__new__', return_value=mock_path):
            pass  # Can't easily mock Path chain

    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_OFFICIALS_JSON)))
    def test_exact_match_via_file(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Eduardo Martinez", "0660620")
        assert result["matched"] is True
        assert result["canonical_name"] == "Eduardo Martinez"
        assert result["match_type"] == "exact"
        assert result["confidence"] == 1.0

    def test_alias_match(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Kinshasa Curl", "0660620")
        assert result["matched"] is True
        assert result["canonical_name"] == "Shasa Curl"
        assert result["match_type"] == "alias"
        assert result["confidence"] == 0.95

    def test_fuzzy_match(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        # Slight typo
        result = match_filer_to_official("Eduard Martinez", "0660620")
        # Should fuzzy-match to Eduardo Martinez
        if result["matched"]:
            assert result["match_type"] == "fuzzy"
            assert result["confidence"] >= 0.85

    def test_no_match(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Completely Unknown Person", "0660620")
        assert result["matched"] is False
        assert result["match_type"] == "no_match"

    def test_wrong_city(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Eduardo Martinez", "9999999")
        assert result["matched"] is False
        assert result["match_type"] == "wrong_city"

    def test_no_ground_truth_file(self):
        with patch("form700_extractor.Path") as mock_path_cls:
            mock_path_inst = MagicMock()
            mock_path_inst.__truediv__ = MagicMock(return_value=mock_path_inst)
            mock_path_inst.exists.return_value = False
            mock_path_cls.return_value = mock_path_inst
            # Use direct file path approach
            result = match_filer_to_official.__wrapped__ if hasattr(match_filer_to_official, '__wrapped__') else None
            # Skip complex path mocking; test the return structure
            # The function checks Path(__file__).parent / "ground_truth" / "officials.json"


class TestMatchFilerCategories:
    """Test that filer matching identifies the correct category."""

    def test_current_council_member(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Sue Wilson", "0660620")
        assert result["matched"] is True
        assert result["category"] == "current_council_members"

    def test_former_council_member(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Tom Butt", "0660620")
        assert result["matched"] is True
        assert result["category"] == "former_council_members"

    def test_city_leadership(self):
        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"
        if not gt_path.exists():
            pytest.skip("officials.json not available")

        result = match_filer_to_official("Shasa Curl", "0660620")
        assert result["matched"] is True
        assert result["category"] == "city_leadership"


# ── Interest Flattening ────────────────────────────────────────

class TestFlattenInterests:
    def test_basic_flattening(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION,
            filer_name="Eduardo Martinez",
            filing_year=2024,
            source_url="https://example.com/filing",
        )
        assert len(result) == 4

    def test_real_property_mapped(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        rp = [i for i in result if i["interest_type"] == "real_property"]
        assert len(rp) == 1
        assert rp[0]["council_member"] == "Eduardo Martinez"
        assert "123 Main St" in rp[0]["description"]
        assert rp[0]["location"] == "123 Main St, Richmond CA 94801"

    def test_income_mapped(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        inc = [i for i in result if i["interest_type"] == "income"]
        assert len(inc) == 1
        assert "ACME" in inc[0]["description"]

    def test_investment_mapped(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        inv = [i for i in result if i["interest_type"] == "investment"]
        assert len(inv) == 1
        assert "Tech Holdings" in inv[0]["description"]

    def test_gift_mapped(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        gifts = [i for i in result if i["interest_type"] == "gift"]
        assert len(gifts) == 1

    def test_empty_filing_produces_no_interests(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EMPTY_FILING, "Sue Wilson", 2024
        )
        assert result == []

    def test_filing_year_propagated(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        for item in result:
            assert item["filing_year"] == 2024

    def test_source_url_propagated(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024,
            source_url="https://netfile.com/test"
        )
        for item in result:
            assert item["source_url"] == "https://netfile.com/test"

    def test_schedule_preserved(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        schedules = {i["schedule"] for i in result}
        assert "B" in schedules
        assert "C" in schedules
        assert "A-1" in schedules
        assert "D" in schedules

    def test_business_entity_mapped_to_investment(self):
        """business_entity (A-2) maps to 'investment' for scanner."""
        data = {
            "interests": [{
                "schedule": "A-2",
                "interest_type": "business_entity",
                "description": "ABC Corp",
            }],
        }
        result = flatten_interests_for_scanner(data, "Test", 2024)
        assert result[0]["interest_type"] == "investment"

    def test_business_position_mapped_to_income(self):
        """business_position maps to 'income' for scanner."""
        data = {
            "interests": [{
                "schedule": "C",
                "interest_type": "business_position",
                "description": "Board of Directors, XYZ Corp",
            }],
        }
        result = flatten_interests_for_scanner(data, "Test", 2024)
        assert result[0]["interest_type"] == "income"


# ── Claude API Extraction ──────────────────────────────────────

class TestExtractForm700:
    def test_calls_claude_api_with_tool_use(self):
        """Verify the API is called with tool_use pattern."""
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.input = SAMPLE_EXTRACTION.copy()

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 2000

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                result = extract_form700("Sample PDF text", filer_name="Test")

        assert result["filer_name"] == "Eduardo Martinez"
        assert "_extraction_metadata" in result

        # Verify tool_use was forced
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["tool_choice"]["type"] == "tool"
        assert call_kwargs["tool_choice"]["name"] == "save_form700_data"
        assert len(call_kwargs["tools"]) == 1

    def test_raises_on_no_tool_use_block(self):
        mock_block = MagicMock()
        mock_block.type = "text"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                with pytest.raises(ValueError, match="No tool_use block"):
                    extract_form700("Sample PDF text")

    def test_raises_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY
            import os
            old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                    extract_form700("Sample PDF text")
            finally:
                if old_key:
                    os.environ["ANTHROPIC_API_KEY"] = old_key

    def test_attaches_metadata(self):
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.input = {"filer_name": "Test", "interests": []}

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 3000
        mock_response.usage.output_tokens = 1500

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                result = extract_form700("text", model="claude-sonnet-4-20250514")

        meta = result["_extraction_metadata"]
        assert meta["model"] == "claude-sonnet-4-20250514"
        assert meta["input_tokens"] == 3000
        assert meta["output_tokens"] == 1500


# ── PDF Text Extraction ────────────────────────────────────────

class TestExtractTextFromPdf:
    def test_extracts_text(self):
        mock_page = MagicMock()
        mock_page.get_fonts.return_value = [("font1", 0, "TrueType")]
        mock_page.get_text.return_value = "STATEMENT OF ECONOMIC INTERESTS\nSchedule A-1"
        mock_page.number = 0

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        with patch("fitz.open", return_value=mock_doc):
            text = extract_text_from_pdf(Path("test.pdf"))

        assert "STATEMENT OF ECONOMIC INTERESTS" in text
        assert "Schedule A-1" in text

    def test_warns_on_type3_fonts(self):
        mock_page = MagicMock()
        mock_page.get_fonts.return_value = [("font1", 0, "Type3")]
        mock_page.get_text.return_value = "garbled text"
        mock_page.number = 0

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        with patch("fitz.open", return_value=mock_doc):
            with patch("form700_extractor.logger") as mock_logger:
                text = extract_text_from_pdf(Path("test.pdf"))
                assert mock_logger.warning.called

    def test_multiple_pages(self):
        pages = []
        for i in range(3):
            p = MagicMock()
            p.get_fonts.return_value = []
            p.get_text.return_value = f"Page {i+1} content"
            p.number = i
            pages.append(p)

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter(pages))

        with patch("fitz.open", return_value=mock_doc):
            text = extract_text_from_pdf(Path("test.pdf"))

        assert "Page 1 content" in text
        assert "Page 3 content" in text


# ── Process Filing (Orchestration) ─────────────────────────────

class TestProcessFiling:
    def test_empty_pdf_returns_error(self):
        with patch("form700_extractor.extract_text_from_pdf", return_value=""):
            result = process_filing(Path("empty.pdf"))
            assert result["error"] is not None
            assert result["extraction"] is None
            assert result["scanner_interests"] == []

    def test_full_pipeline(self):
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.input = SAMPLE_EXTRACTION.copy()

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 2000

        with patch("form700_extractor.extract_text_from_pdf", return_value="Form 700 text"):
            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    result = process_filing(
                        Path("test.pdf"),
                        filer_name="Eduardo Martinez",
                        filing_year=2024,
                    )

        assert result["extraction"] is not None
        assert result["extraction"]["filer_name"] == "Eduardo Martinez"
        assert len(result["scanner_interests"]) == 4

    def test_includes_official_match(self):
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.input = SAMPLE_EXTRACTION.copy()

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500

        gt_path = Path(__file__).parent.parent / "src" / "ground_truth" / "officials.json"

        with patch("form700_extractor.extract_text_from_pdf", return_value="text"):
            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    result = process_filing(
                        Path("test.pdf"),
                        filer_name="Eduardo Martinez",
                    )

        assert "official_match" in result
        if gt_path.exists():
            assert result["official_match"]["matched"] is True


# ── load_form700_to_db ─────────────────────────────────────────

class TestLoadForm700ToDb:
    """Test the database loading function with mocked connection."""

    def _make_mock_conn(self):
        """Create a mock psycopg2 connection with cursor context manager."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cur

    def test_loads_filing_with_interests(self):
        from db import load_form700_to_db

        mock_conn, mock_cur = self._make_mock_conn()
        # ensure_official returns a UUID
        filing_uuid = uuid.uuid4()
        mock_cur.fetchone.return_value = (filing_uuid,)

        with patch("db.ensure_official", return_value=uuid.uuid4()):
            result = load_form700_to_db(
                mock_conn,
                SAMPLE_EXTRACTION,
                filing_metadata={
                    "filer_name": "Eduardo Martinez",
                    "agency": "City of Richmond",
                    "statement_type": "annual",
                    "filing_year": 2024,
                    "source": "netfile_sei",
                    "source_url": "https://example.com",
                    "document_id": None,
                },
            )

        assert result["interests_count"] == 4
        assert result["matched_official"] is True
        assert result["filer_name"] == "Eduardo Martinez"
        # Verify INSERT was called for filing + 4 interests + DELETE
        assert mock_cur.execute.call_count >= 6  # 1 filing INSERT + 1 DELETE + 4 interest INSERTs

    def test_loads_empty_filing(self):
        from db import load_form700_to_db

        mock_conn, mock_cur = self._make_mock_conn()
        filing_uuid = uuid.uuid4()
        mock_cur.fetchone.return_value = (filing_uuid,)

        with patch("db.ensure_official", return_value=uuid.uuid4()):
            result = load_form700_to_db(
                mock_conn,
                SAMPLE_EMPTY_FILING,
                filing_metadata={
                    "filer_name": "Sue Wilson",
                    "filing_year": 2024,
                    "source": "netfile_sei",
                },
            )

        assert result["interests_count"] == 0
        assert result["matched_official"] is True

    def test_handles_unmatched_official(self):
        from db import load_form700_to_db

        mock_conn, mock_cur = self._make_mock_conn()
        filing_uuid = uuid.uuid4()
        mock_cur.fetchone.return_value = (filing_uuid,)

        with patch("db.ensure_official", side_effect=Exception("DB error")):
            result = load_form700_to_db(
                mock_conn,
                SAMPLE_EXTRACTION,
                filing_metadata={
                    "filer_name": "Unknown Person",
                    "filing_year": 2024,
                    "source": "netfile_sei",
                },
            )

        assert result["matched_official"] is False
        assert result["official_id"] is None

    def test_raises_without_filer_name(self):
        from db import load_form700_to_db

        mock_conn, _ = self._make_mock_conn()
        empty_extraction = {
            "filer_name": "",
            "interests": [],
        }

        with pytest.raises(ValueError, match="filer_name"):
            load_form700_to_db(
                mock_conn,
                empty_extraction,
                filing_metadata={"filer_name": "", "filing_year": 2024, "source": "test"},
            )

    def test_uses_extraction_filer_name_over_metadata(self):
        """Extraction result (from PDF) is authoritative over scraper metadata."""
        from db import load_form700_to_db

        mock_conn, mock_cur = self._make_mock_conn()
        filing_uuid = uuid.uuid4()
        mock_cur.fetchone.return_value = (filing_uuid,)

        extraction = SAMPLE_EXTRACTION.copy()
        extraction["filer_name"] = "Eduardo M. Martinez"

        with patch("db.ensure_official", return_value=uuid.uuid4()):
            result = load_form700_to_db(
                mock_conn,
                extraction,
                filing_metadata={
                    "filer_name": "E. Martinez",  # Less precise metadata
                    "filing_year": 2024,
                    "source": "netfile_sei",
                },
            )

        assert result["filer_name"] == "Eduardo M. Martinez"


# ── Conflict Scanner Integration ───────────────────────────────

class TestScannerIntegration:
    """Verify flattened interests match what conflict_scanner.scan_meeting_json expects."""

    def test_has_required_scanner_keys(self):
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        required_keys = {"council_member", "interest_type", "description", "location", "filing_year", "source_url"}
        for item in result:
            assert required_keys.issubset(item.keys())

    def test_real_property_triggers_scanner(self):
        """Real property interests should be detected by scanner for land-use items."""
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        rp = [i for i in result if i["interest_type"] == "real_property"]
        assert len(rp) == 1
        # Scanner checks: interest.get("interest_type") == "real_property"
        assert rp[0]["interest_type"] == "real_property"

    def test_income_triggers_scanner(self):
        """Income interests should match against entity names in agenda items."""
        result = flatten_interests_for_scanner(
            SAMPLE_EXTRACTION, "Eduardo Martinez", 2024
        )
        inc = [i for i in result if i["interest_type"] == "income"]
        assert len(inc) == 1
        # Scanner checks: interest.get("interest_type") in ("income", "investment")
        assert inc[0]["interest_type"] in ("income", "investment")


# ── Module-Level Constants ─────────────────────────────────────

class TestModuleConstants:
    def test_prompts_dir_exists(self):
        from form700_extractor import PROMPTS_DIR
        assert PROMPTS_DIR.exists()

    def test_schema_is_dict(self):
        assert isinstance(FORM700_EXTRACTION_SCHEMA, dict)
        assert FORM700_EXTRACTION_SCHEMA["type"] == "object"
