"""Regression tests for the optional Kimi paper-filing vision fallback."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _sample_pdf(tmp_path):
    import fitz

    path = tmp_path / "filing.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Schedule A contribution")
    doc.save(path)
    doc.close()
    return path


def test_renders_source_pdf_as_bounded_image_blocks(tmp_path):
    from netfile_paper_extractor import _render_pdf_path_image_blocks

    blocks = _render_pdf_path_image_blocks(_sample_pdf(tmp_path))

    assert len(blocks) == 1
    assert blocks[0]["type"] == "image_url"
    assert blocks[0]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_optional_kimi_vision_returns_normalized_rows(tmp_path, monkeypatch):
    from llm_client import VISION_MODEL, get_model_route
    from netfile_paper_extractor import parse_filing_with_vision

    monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="save_contributions",
                input={
                    "contributions": [
                        {
                            "contributor_name": "Richmond Resident",
                            "amount": 250.0,
                            "date": "2026-07-31",
                        }
                    ]
                },
            )
        ],
        stop_reason="tool_use",
    )

    with patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        rows = parse_filing_with_vision(
            _sample_pdf(tmp_path),
            "460",
            "filing-1",
            "Richmond Neighbors",
            MagicMock(),
        )

    assert rows == [
        {
            "contributor_name": "Richmond Resident",
            "amount": 250.0,
            "date": "2026-07-31",
            "filing_id": "filing-1",
            "entity_code": "IND",
            "city": "",
            "state": "",
            "zip": "",
            "occupation": "",
            "contributor_employer": "",
        }
    ]
    kwargs = client_cls.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == VISION_MODEL
    assert kwargs["thinking"] == {"type": "disabled"}
    assert any(
        block.get("type") == "image_url"
        for block in kwargs["messages"][0]["content"]
    )


def test_image_only_form460_summary_uses_bounded_kimi_vision(
    tmp_path, monkeypatch,
):
    from llm_client import OPENAI_LUNA_MODEL, VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        parse_form460_summary_with_vision,
        reset_form460_summary_run_state,
    )

    monkeypatch.delenv(get_model_route(OPENAI_LUNA_MODEL).api_key_env, raising=False)
    monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
    reset_form460_summary_run_state()
    summary = {
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "monetary_this_period": 1200.0,
        "monetary_cycle_to_date": 2400.0,
        "loans_this_period": 0.0,
        "loans_cycle_to_date": 0.0,
        "nonmonetary_this_period": 0.0,
        "nonmonetary_cycle_to_date": 0.0,
        "total_this_period": 1200.0,
        "total_cycle_to_date": 2400.0,
        "itemized_this_period": 1000.0,
        "unitemized_this_period": 200.0,
    }
    response = SimpleNamespace(
        content=[SimpleNamespace(
            type="tool_use",
            name="save_form460_summary",
            input=summary,
        )],
        stop_reason="tool_use",
    )
    text_client = MagicMock()
    image_block = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAAA"},
    }

    with patch(
        "netfile_paper_extractor.extract_text_from_pdf",
        return_value="",
    ), patch(
        "netfile_paper_extractor._render_pdf_path_image_blocks",
        return_value=[image_block],
    ) as render, patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        result = parse_form460_summary_with_vision(
            tmp_path / "image-only.pdf",
            "vision-summary-filing",
            "Richmond Neighbors",
            text_client,
        )

    assert result == summary
    text_client.messages.create.assert_not_called()
    render.assert_called_once_with(
        tmp_path / "image-only.pdf",
        max_pages=6,
        reject_oversized=False,
    )
    kwargs = client_cls.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == VISION_MODEL
    assert kwargs["thinking"] == {"type": "disabled"}
    assert image_block in kwargs["messages"][0]["content"]


def test_image_only_form460_summary_uses_luna_when_configured(
    tmp_path, monkeypatch,
):
    from llm_client import OPENAI_LUNA_MODEL, VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        parse_form460_summary_with_vision,
        reset_form460_summary_run_state,
    )

    monkeypatch.setenv(get_model_route(OPENAI_LUNA_MODEL).api_key_env, "test-key")
    monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
    reset_form460_summary_run_state()
    summary = {
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "monetary_this_period": 5000.0,
        "monetary_cycle_to_date": 5000.0,
        "loans_this_period": 0.0,
        "loans_cycle_to_date": 0.0,
        "nonmonetary_this_period": 0.0,
        "nonmonetary_cycle_to_date": 0.0,
        "total_this_period": 5000.0,
        "total_cycle_to_date": 5000.0,
        "itemized_this_period": 5000.0,
        "unitemized_this_period": 0.0,
    }
    response = SimpleNamespace(
        content=[SimpleNamespace(
            type="tool_use",
            name="save_form460_summary",
            input=summary,
        )],
        stop_reason="tool_use",
    )
    image_block = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAAA"},
    }

    with patch(
        "netfile_paper_extractor.extract_text_from_pdf",
        return_value="",
    ), patch(
        "netfile_paper_extractor._render_pdf_path_image_blocks",
        return_value=[image_block],
    ), patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        result = parse_form460_summary_with_vision(
            tmp_path / "image-only.pdf",
            "luna-summary-filing",
            "Black Men & Women PAC",
            MagicMock(),
        )

    assert result == summary
    kwargs = client_cls.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == OPENAI_LUNA_MODEL
    assert kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["messages"][0]["content"][1]["image_url"]["detail"] == "original"


def test_luna_form460_summary_retries_one_arithmetic_mismatch(
    tmp_path, monkeypatch,
):
    from llm_client import OPENAI_LUNA_MODEL, VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        parse_form460_summary_with_vision,
        reset_form460_summary_run_state,
    )

    monkeypatch.setenv(get_model_route(OPENAI_LUNA_MODEL).api_key_env, "test-key")
    monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
    reset_form460_summary_run_state()
    invalid = {
        "period_start": "2026-05-29",
        "period_end": "2026-06-30",
        "monetary_this_period": 9140.0,
        "monetary_cycle_to_date": 73300.0,
        "loans_this_period": 0.0,
        "loans_cycle_to_date": 0.0,
        "nonmonetary_this_period": 0.0,
        "nonmonetary_cycle_to_date": 0.0,
        "total_this_period": 9140.0,
        "total_cycle_to_date": 73300.0,
        "itemized_this_period": 9140.0,
        "unitemized_this_period": 1147.0,
    }
    valid = {
        **invalid,
        "itemized_this_period": 7993.0,
    }
    responses = [
        SimpleNamespace(
            content=[SimpleNamespace(
                type="tool_use",
                name="save_form460_summary",
                input=payload,
            )],
            stop_reason="tool_use",
        )
        for payload in (invalid, valid)
    ]
    image_block = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAAA"},
    }

    with patch(
        "netfile_paper_extractor.extract_text_from_pdf",
        return_value="",
    ), patch(
        "netfile_paper_extractor._render_pdf_path_image_blocks",
        return_value=[image_block],
    ), patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.side_effect = responses
        result = parse_form460_summary_with_vision(
            tmp_path / "shifted-schedule.pdf",
            "shifted-summary-filing",
            "Anderson for Mayor 2026",
            MagicMock(),
        )

    assert result == valid
    assert client_cls.return_value.messages.create.call_count == 2
    correction = client_cls.return_value.messages.create.call_args.kwargs
    assert "CORRECTION PASS" in correction["messages"][0]["content"][0]["text"]
    assert "10287.00 != 9140.00" in correction["messages"][0]["content"][0]["text"]


def test_image_only_form460_summary_remains_pending_without_any_vision_key(
    tmp_path, monkeypatch,
):
    from llm_client import OPENAI_LUNA_MODEL, VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        OptionalVisionUnavailableError,
        parse_form460_summary_with_vision,
        reset_form460_summary_run_state,
    )

    monkeypatch.delenv(get_model_route(OPENAI_LUNA_MODEL).api_key_env, raising=False)
    monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
    reset_form460_summary_run_state()

    with patch(
        "netfile_paper_extractor.extract_text_from_pdf",
        return_value="",
    ), pytest.raises(OptionalVisionUnavailableError, match="remains pending"):
        parse_form460_summary_with_vision(
            tmp_path / "never-opened.pdf",
            "no-vision-summary",
            "Richmond Neighbors",
            MagicMock(),
        )


def test_optional_vision_remains_pending_without_provider_key(tmp_path, monkeypatch):
    from llm_client import VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        OptionalVisionUnavailableError,
        parse_filing_with_vision,
    )

    monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
    with patch("netfile_paper_extractor.LLMClient") as client_cls:
        with pytest.raises(OptionalVisionUnavailableError, match="remains pending"):
            parse_filing_with_vision(
                tmp_path / "never-opened.pdf",
                "460",
                "filing-1",
                "Richmond Neighbors",
                MagicMock(),
            )

    client_cls.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(content=[], stop_reason="end_turn"),
        SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input={"_raw": "{"})],
            stop_reason="end_turn",
        ),
        SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input={"contributions": []})],
            stop_reason="max_tokens",
        ),
    ],
)
def test_incomplete_vision_responses_leave_filing_pending(
    response, tmp_path, monkeypatch
):
    from llm_client import VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        VisionExtractionIncompleteError,
        parse_filing_with_vision,
    )

    monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
    with patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        with pytest.raises(VisionExtractionIncompleteError):
            parse_filing_with_vision(
                _sample_pdf(tmp_path),
                "460",
                "filing-1",
                "Richmond Neighbors",
                MagicMock(),
            )


def test_valid_empty_contribution_list_is_a_complete_vision_result(
    tmp_path, monkeypatch
):
    from llm_client import VISION_MODEL, get_model_route
    from netfile_paper_extractor import parse_filing_with_vision

    monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
    response = SimpleNamespace(
        content=[SimpleNamespace(
            type="tool_use",
            name="save_contributions",
            input={"contributions": []},
        )],
        stop_reason="tool_use",
    )
    with patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        assert parse_filing_with_vision(
            _sample_pdf(tmp_path),
            "460",
            "filing-1",
            "Richmond Neighbors",
            MagicMock(),
        ) == []


@pytest.mark.parametrize(
    "row",
    [
        {"contributor_name": "Resident", "amount": 100.0},
        {"contributor_name": "Resident", "amount": "100", "date": "2026-08-01"},
        {"contributor_name": "Resident", "amount": float("inf"), "date": "2026-08-01"},
        {"contributor_name": "Resident", "amount": 100.0, "date": "2026-02-30"},
        {
            "contributor_name": "Resident",
            "amount": 100.0,
            "date": "2026-08-01",
            "entity_code": "PERSON",
        },
    ],
)
def test_malformed_nonempty_vision_rows_leave_filing_pending(
    row, tmp_path, monkeypatch
):
    from llm_client import VISION_MODEL, get_model_route
    from netfile_paper_extractor import (
        VisionExtractionIncompleteError,
        parse_filing_with_vision,
    )

    monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
    response = SimpleNamespace(
        content=[SimpleNamespace(
            type="tool_use",
            name="save_contributions",
            input={"contributions": [row]},
        )],
        stop_reason="tool_use",
    )
    with patch("netfile_paper_extractor.LLMClient") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        with pytest.raises(VisionExtractionIncompleteError):
            parse_filing_with_vision(
                _sample_pdf(tmp_path),
                "460",
                "filing-malformed",
                "Richmond Neighbors",
                MagicMock(),
            )


def test_extract_committee_does_not_mark_unavailable_vision_as_processed(
    tmp_path, monkeypatch
):
    from llm_client import VISION_MODEL, get_model_route
    from netfile_paper_extractor import extract_committee

    monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
    filing = {"filing_id": "filing-1", "form_type": "Form 460"}
    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing",
        return_value=_sample_pdf(tmp_path),
    ), patch("netfile_paper_extractor.extract_text_from_pdf", return_value=""):
        result = extract_committee(
            "Richmond Neighbors",
            [filing],
            MagicMock(),
            dry_run=True,
        )

    assert result["filings"] == []
    assert result["contributions"] == []
