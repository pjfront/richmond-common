"""Tests for theme_extractor.py — S21 Phase B."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from theme_extractor import (
    _slugify,
    _format_seed_prompt,
    extract_themes_for_item,
    import_themes,
    get_items_needing_themes,
    get_comments_for_item,
)


# -- Unit tests: slugify ----------------------------------------


class TestSlugify:
    def test_basic(self):
        assert _slugify("Privacy & Data Retention") == "privacy-data-retention"

    def test_special_chars(self):
        assert _slugify("Youth Safety (K-12)") == "youth-safety-k-12"

    def test_extra_spaces(self):
        assert _slugify("  Public  Safety  ") == "public-safety"

    def test_already_slug(self):
        assert _slugify("contract-cost") == "contract-cost"

    def test_truncates_long(self):
        result = _slugify("a" * 200)
        assert len(result) <= 100

    def test_empty(self):
        assert _slugify("") == ""

    def test_numbers(self):
        assert _slugify("District 5 Rezoning") == "district-5-rezoning"


# -- Unit tests: seed prompt ------------------------------------


class TestFormatSeedPrompt:
    def test_empty_seeds(self):
        assert _format_seed_prompt([]) == ""

    def test_with_seeds(self):
        result = _format_seed_prompt(["Chevron", "Housing"])
        assert "Chevron, Housing" in result
        assert "reuse" in result.lower()

    def test_preserves_order(self):
        result = _format_seed_prompt(["Zoning", "Budget", "Housing"])
        assert "Zoning, Budget, Housing" in result


# -- Unit tests: import_themes ----------------------------------


SAMPLE_EXTRACTION = {
    "themes": [
        {
            "label": "Privacy & Data Retention",
            "slug": "privacy-data-retention",
            "description": "Concerns about surveillance data storage and access.",
        },
        {
            "label": "Public Safety",
            "slug": "public-safety",
            "description": "Impact on crime reduction and response times.",
        },
    ],
    "assignments": [
        {
            "speaker_name": "Ahmad Anderson",
            "theme_slug": "public-safety",
            "confidence": 0.95,
        },
        {
            "speaker_name": "Claudia Citra",
            "theme_slug": "privacy-data-retention",
            "confidence": 0.9,
        },
        {
            "speaker_name": "Claudia Citra",
            "theme_slug": "public-safety",
            "confidence": 0.75,
        },
        {
            "speaker_name": "Unknown Speaker",
            "theme_slug": "public-safety",
            "confidence": 0.8,
        },
    ],
    "narratives": [
        {
            "theme_slug": "privacy-data-retention",
            "narrative": "Several speakers raised concerns about data retention periods.",
            "comment_count": 15,
        },
        {
            "theme_slug": "public-safety",
            "narrative": "Residents described incidents where cameras aided investigations.",
            "comment_count": 12,
        },
    ],
    "extraction_notes": "Clear audio throughout.",
}

SAMPLE_COMMENTS = [
    {
        "comment_id": "c1111111-1111-1111-1111-111111111111",
        "speaker_name": "Ahmad Anderson",
        "method": "in_person",
        "summary": "Argued that public safety is foundational.",
    },
    {
        "comment_id": "c2222222-2222-2222-2222-222222222222",
        "speaker_name": "Claudia Citra",
        "method": "in_person",
        "summary": "Raised concerns about data retention and safety.",
    },
    {
        "comment_id": "c3333333-3333-3333-3333-333333333333",
        "speaker_name": "David Lee",
        "method": "zoom",
        "summary": "Brief comment about costs.",
    },
]


class TestImportThemesDryRun:
    def test_dry_run_returns_stats(self):
        stats = import_themes(
            SAMPLE_EXTRACTION,
            "item-uuid-123",
            SAMPLE_COMMENTS,
            dry_run=True,
        )
        assert stats["themes_created"] == 2
        assert stats["narratives"] == 2
        # 3 of 4 assignments match (Unknown Speaker doesn't)
        assert stats["assignments"] == 3

    def test_dry_run_empty_result(self):
        stats = import_themes(
            {"themes": [], "assignments": [], "narratives": []},
            "item-uuid-123",
            SAMPLE_COMMENTS,
            dry_run=True,
        )
        assert stats["themes_created"] == 0
        assert stats["assignments"] == 0

    def test_multi_theme_speaker(self):
        """Claudia Citra appears under both themes."""
        stats = import_themes(
            SAMPLE_EXTRACTION,
            "item-uuid-123",
            SAMPLE_COMMENTS,
            dry_run=True,
        )
        # Claudia has 2 assignments, Ahmad has 1, Unknown unmatched = 3 total
        assert stats["assignments"] == 3


# -- Unit tests: extract_themes_for_item -----------------------


class TestExtractThemes:
    @patch("theme_extractor.anthropic")
    def test_parses_json_response(self, mock_anthropic):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_EXTRACTION))]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 300
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        item = {
            "item_id": "test-id",
            "item_number": "W.1",
            "title": "Flock Safety Contract",
            "meeting_date": "2026-03-03",
            "comment_count": 3,
        }

        result = extract_themes_for_item(item, SAMPLE_COMMENTS, [])
        assert result is not None
        assert len(result["themes"]) == 2
        assert len(result["assignments"]) == 4

    @patch("theme_extractor.anthropic")
    def test_handles_markdown_fences(self, mock_anthropic):
        wrapped = f"```json\n{json.dumps(SAMPLE_EXTRACTION)}\n```"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=wrapped)]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 300
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        item = {
            "item_id": "test-id",
            "item_number": "W.1",
            "title": "Test",
            "meeting_date": "2026-01-01",
            "comment_count": 3,
        }

        result = extract_themes_for_item(item, SAMPLE_COMMENTS, [])
        assert result is not None
        assert len(result["themes"]) == 2

    @patch("theme_extractor.anthropic")
    def test_seeds_included_in_prompt(self, mock_anthropic):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_EXTRACTION))]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 300
        mock_client = mock_anthropic.Anthropic.return_value
        mock_client.messages.create.return_value = mock_response

        item = {
            "item_id": "test-id",
            "item_number": "W.1",
            "title": "Test",
            "meeting_date": "2026-01-01",
            "comment_count": 3,
        }

        extract_themes_for_item(item, SAMPLE_COMMENTS, ["Chevron", "Housing"])

        call_args = mock_client.messages.create.call_args
        system = call_args.kwargs["system"]
        assert "Chevron" in system
        assert "Housing" in system

    @patch("theme_extractor.anthropic", None)
    def test_returns_none_without_anthropic(self):
        item = {
            "item_id": "test-id",
            "item_number": "W.1",
            "title": "Test",
            "meeting_date": "2026-01-01",
            "comment_count": 3,
        }
        result = extract_themes_for_item(item, SAMPLE_COMMENTS, [])
        assert result is None

    @patch("theme_extractor.anthropic")
    def test_returns_none_on_bad_json(self, mock_anthropic):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not json at all")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        item = {
            "item_id": "test-id",
            "item_number": "W.1",
            "title": "Test",
            "meeting_date": "2026-01-01",
            "comment_count": 3,
        }
        result = extract_themes_for_item(item, SAMPLE_COMMENTS, [])
        assert result is None


# -- Slug consistency ------------------------------------------


class TestSlugConsistency:
    """Verify that slugs generated from labels match what the LLM returns."""

    def test_slug_matches_label(self):
        for theme in SAMPLE_EXTRACTION["themes"]:
            generated = _slugify(theme["label"])
            assert generated == theme["slug"], (
                f"Slug mismatch: _slugify('{theme['label']}') = '{generated}', "
                f"expected '{theme['slug']}'"
            )
