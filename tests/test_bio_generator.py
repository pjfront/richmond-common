"""Tests for bio generator pipeline module."""
import json
from unittest.mock import patch, MagicMock
from src.bio_generator import build_factual_profile, generate_bio_summary, BIO_CONSTRAINTS


def test_build_factual_profile_basic():
    """Factual profile should include all expected fields."""
    profile = build_factual_profile(
        official_name="Jane Doe",
        official_role="councilmember",
        official_seat="District 1",
        term_start="2023-01-10",
        term_end=None,
        vote_count=487,
        meetings_attended=22,
        meetings_total=24,
        top_categories=[
            {"category": "contracts", "count": 98},
            {"category": "governance", "count": 72},
        ],
        majority_alignment_rate=0.89,
        sole_dissent_count=12,
        sole_dissent_categories=[
            {"category": "budget", "count": 5},
            {"category": "infrastructure", "count": 4},
        ],
    )

    assert profile["name"] == "Jane Doe"
    assert profile["role"] == "councilmember"
    assert profile["seat"] == "District 1"
    assert profile["term_start"] == "2023-01-10"
    assert profile["vote_count"] == 487
    assert profile["attendance_rate"] == "92%"
    assert profile["attendance_fraction"] == "22 of 24"
    assert profile["majority_alignment_rate"] == "89%"
    assert len(profile["top_categories"]) == 2
    assert profile["sole_dissent_count"] == 12


def test_build_factual_profile_zero_meetings():
    """Handle zero meetings without division by zero."""
    profile = build_factual_profile(
        official_name="Test",
        official_role="councilmember",
        official_seat=None,
        term_start=None,
        term_end=None,
        vote_count=0,
        meetings_attended=0,
        meetings_total=0,
        top_categories=[],
        majority_alignment_rate=0.0,
        sole_dissent_count=0,
        sole_dissent_categories=[],
    )
    assert profile["attendance_rate"] == "0%"
    assert profile["attendance_fraction"] == "0 of 0"


def test_bio_constraints_exist():
    """Constraints string should include key guardrails."""
    assert "political orientation" in BIO_CONSTRAINTS.lower()
    assert "compare" in BIO_CONSTRAINTS.lower()
    assert "value-laden" in BIO_CONSTRAINTS.lower()


def test_generate_bio_summary_calls_api():
    """generate_bio_summary should call the Claude API with factual data."""
    mock_profile = {
        "name": "Jane Doe",
        "role": "councilmember",
        "vote_count": 100,
        "attendance_rate": "90%",
        "attendance_fraction": "18 of 20",
        "top_categories": [{"category": "budget", "count": 30}],
        "majority_alignment_rate": "85%",
        "sole_dissent_count": 5,
        "sole_dissent_categories": [{"category": "budget", "count": 3}],
    }

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Jane Doe has participated in 18 of 20 meetings.")]
    mock_response.model = "claude-sonnet-4-5-20250514"

    with patch("src.bio_generator.anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        result = generate_bio_summary(mock_profile)

        assert result["summary"] == "Jane Doe has participated in 18 of 20 meetings."
        assert result["model"] == "claude-sonnet-4-5-20250514"
        # Verify constraints were passed in the prompt
        call_args = mock_client.messages.create.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"]
        assert "political orientation" in prompt_text.lower()
