"""Tests for pre-summarization consistency gate and parent wrapper detection."""

from __future__ import annotations

import pytest

from text_utils import find_parent_wrapper_numbers
from plain_language_summarizer import validate_item_for_summarization


# ── find_parent_wrapper_numbers ───────────────────────────────


class TestFindParentWrapperNumbers:
    def test_detects_parents_with_children(self):
        nums = ["V.1", "V.1.a", "V.1.b", "V.2", "V.3", "V.3.a"]
        parents = find_parent_wrapper_numbers(nums)
        assert parents == {"V.1", "V.3"}

    def test_no_parents_when_all_flat(self):
        nums = ["V.1", "V.2", "V.3", "V.4"]
        parents = find_parent_wrapper_numbers(nums)
        assert parents == set()

    def test_empty_list(self):
        assert find_parent_wrapper_numbers([]) == set()

    def test_section_headers_not_parents(self):
        # "V" has no dots, so V.1 doesn't make "V" a parent via rsplit
        nums = ["V", "V.1", "V.2"]
        parents = find_parent_wrapper_numbers(nums)
        assert parents == set()

    def test_deep_nesting(self):
        # V.1.a.i has parent V.1.a, and V.1.a has parent V.1
        nums = ["V.1", "V.1.a", "V.1.a.i"]
        parents = find_parent_wrapper_numbers(nums)
        assert "V.1" in parents
        assert "V.1.a" in parents


# ── validate_item_for_summarization ───────────────────────────


class TestValidateItemForSummarization:
    def test_clean_item_no_warnings(self):
        item = {
            "item_number": "V.1",
            "title": "Accept $50,000 grant",
            "description": "The city receives $50,000 from the state for parks.",
            "financial_amount": "$50,000",
        }
        assert validate_item_for_summarization(item) == []

    def test_warns_on_missing_amount_in_text(self):
        item = {
            "item_number": "V.1",
            "title": "Accept grant for parks",
            "description": "The city receives a grant for park improvements.",
            "financial_amount": "$251,101",
        }
        warnings = validate_item_for_summarization(item)
        assert len(warnings) == 1
        assert "$251,101" in warnings[0]
        assert "not found" in warnings[0]

    def test_no_warning_when_no_financial_amount(self):
        item = {
            "item_number": "V.1",
            "title": "Approve minutes",
            "description": "Regular meeting minutes.",
            "financial_amount": None,
        }
        assert validate_item_for_summarization(item) == []

    def test_detects_near_duplicate_siblings(self):
        item = {
            "item_number": "V.1",
            "title": "Grant item",
            "description": "ACCEPT $246,601 in workforce development grant funds from Construction Trades and Chevron and Pinole Youth Foundation",
        }
        sibling = {
            "item_number": "V.1.b",
            "title": "Workforce grants",
            "description": "ACCEPT $246,601 in workforce development grant funds from Construction Trades and Chevron and Pinole Youth Foundation for job training",
        }
        warnings = validate_item_for_summarization(item, siblings=[item, sibling])
        assert any("near-duplicate" in w for w in warnings)

    def test_no_duplicate_warning_for_distinct_items(self):
        item_a = {
            "item_number": "V.1",
            "title": "Kaiser grant",
            "description": "ADOPT a resolution to accept $4,500 from Kaiser Permanente for Park Prescription Day events.",
        }
        item_b = {
            "item_number": "V.2",
            "title": "Workforce grants",
            "description": "ACCEPT $246,601 in workforce development grant funds from Construction Trades and Chevron.",
        }
        assert validate_item_for_summarization(item_a, siblings=[item_a, item_b]) == []

    def test_skips_self_in_sibling_check(self):
        item = {
            "item_number": "V.1",
            "title": "Some item",
            "description": "A sufficiently long description that would match itself if we did not skip self-comparison in the loop.",
        }
        # Should not warn about being a duplicate of itself
        assert validate_item_for_summarization(item, siblings=[item]) == []
