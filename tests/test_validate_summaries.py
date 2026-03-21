"""Tests for the summary readability validator."""

from __future__ import annotations

import pytest

from validate_summaries import (
    validate_item,
    _count_words,
    _count_sentences,
    _max_sentence_length,
    _flesch_kincaid_grade,
)


class TestWordCount:
    def test_simple(self):
        assert _count_words("The council will vote.") == 4

    def test_empty(self):
        assert _count_words("") == 0


class TestSentenceCount:
    def test_single(self):
        assert _count_sentences("One sentence.") == 1

    def test_multiple(self):
        assert _count_sentences("First. Second. Third.") == 3

    def test_question_and_exclamation(self):
        assert _count_sentences("What happened? It passed!") == 2


class TestMaxSentenceLength:
    def test_single_sentence(self):
        assert _max_sentence_length("The council will vote on this item.") == 7

    def test_variable_lengths(self):
        # "Short." = 1 word, "This is a longer sentence here." = 6 words
        assert _max_sentence_length("Short. This is a longer sentence here.") == 6


class TestFleschKincaid:
    def test_simple_text_low_grade(self):
        grade = _flesch_kincaid_grade("The dog ran fast. It was fun.")
        assert grade < 5

    def test_complex_text_higher_grade(self):
        grade = _flesch_kincaid_grade(
            "The administration recommends appropriation of supplemental "
            "budgetary allocation for infrastructure rehabilitation."
        )
        assert grade > 10

    def test_empty(self):
        assert _flesch_kincaid_grade("") == 0.0


class TestValidateItem:
    def test_clean_item(self):
        result = validate_item({
            "id": "test-id",
            "title": "Approve park renovation",
            "plain_language_summary": "Council will approve park renovation. A yes vote will fix the playground.",
            "summary_headline": "Park renovation approved.",
            "category": "parks",
        })
        assert result["has_summary"] is True
        assert result["has_headline"] is True
        # Simple, short text should have few or no issues
        assert "missing summary" not in [i for i in result["issues"]]

    def test_missing_summary(self):
        result = validate_item({
            "id": "test-id",
            "title": "Test",
            "plain_language_summary": None,
            "summary_headline": None,
            "category": "other",
        })
        assert "missing summary" in result["issues"]

    def test_missing_headline(self):
        result = validate_item({
            "id": "test-id",
            "title": "Test",
            "plain_language_summary": "A summary exists.",
            "summary_headline": None,
            "category": "other",
        })
        assert "missing headline (summary exists)" in result["issues"]

    def test_too_long_summary(self):
        long_summary = " ".join(["word"] * 80) + "."
        result = validate_item({
            "id": "test-id",
            "title": "Test",
            "plain_language_summary": long_summary,
            "summary_headline": "Short headline.",
            "category": "other",
        })
        assert any("summary too long" in i for i in result["issues"])

    def test_too_long_headline(self):
        long_headline = " ".join(["word"] * 25) + "."
        result = validate_item({
            "id": "test-id",
            "title": "Test",
            "plain_language_summary": "A normal summary.",
            "summary_headline": long_headline,
            "category": "other",
        })
        assert any("headline too long" in i for i in result["issues"])

    def test_banned_word_detected(self):
        result = validate_item({
            "id": "test-id",
            "title": "Test",
            "plain_language_summary": "The council shall approve this measure.",
            "summary_headline": "Measure approved.",
            "category": "other",
        })
        assert any("banned word" in i and "shall" in i for i in result["issues"])

    def test_jargon_detected(self):
        result = validate_item({
            "id": "test-id",
            "title": "Test",
            "plain_language_summary": "The ordinance will change parking rules.",
            "summary_headline": "Parking ordinance changed.",
            "category": "other",
        })
        assert any("jargon" in i and "ordinance" in i for i in result["issues"])
