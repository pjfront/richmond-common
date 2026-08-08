"""Durable idempotency tests for terminal-zero NetFile paper filings."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _response(*, content, stop_reason="tool_use"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _tool_input(value):
    return SimpleNamespace(
        type="tool_use",
        name="save_contributions",
        input=value,
    )


def _form460_summary(**overrides):
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
    summary.update(overrides)
    return summary


def _form460_tool(value, *, name="save_form460_summary"):
    return SimpleNamespace(type="tool_use", name=name, input=value)


@pytest.mark.parametrize(
    "response",
    [
        _response(
            content=[_form460_tool(_form460_summary())],
            stop_reason="max_tokens",
        ),
        _response(
            content=[_form460_tool(_form460_summary())],
            stop_reason="end_turn",
        ),
        _response(
            content=[SimpleNamespace(
                type="text",
                text='{"period_end":"2026-06-30"}',
            )],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool({"_raw": "{"})],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(), name="wrong_tool")],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool({
                key: value
                for key, value in _form460_summary().items()
                if key != "period_end"
            })],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool({
                key: value
                for key, value in _form460_summary().items()
                if key != "period_start"
            })],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(period_start=""))],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(
                period_start="2026-07-01",
                period_end="2026-06-30",
            ))],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(extra_field=1))],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(period_end="06/30/2026"))],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(total_this_period="1200"))],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(total_this_period=True))],
            stop_reason="tool_use",
        ),
        _response(
            content=[_form460_tool(_form460_summary(total_this_period=float("nan")))],
            stop_reason="tool_use",
        ),
    ],
)
def test_form460_summary_invalid_or_truncated_output_fails_closed(response):
    from netfile_paper_extractor import (
        Form460SummaryIncompleteError,
        get_form460_summary_run_cache,
        get_form460_summary_run_failures,
        parse_form460_summary_with_vision,
        reset_form460_summary_run_state,
    )

    reset_form460_summary_run_state()
    client = MagicMock()
    client.messages.create.return_value = response
    with patch(
        "netfile_paper_extractor.extract_text_from_pdf",
        return_value="visible Form 460 text",
    ), pytest.raises(Form460SummaryIncompleteError):
        parse_form460_summary_with_vision(
            Path("filing-460.pdf"),
            "strict-filing",
            "Richmond Neighbors",
            client,
        )

    assert get_form460_summary_run_cache() == {}
    assert "strict-filing" in get_form460_summary_run_failures()


def test_valid_form460_summary_requires_exact_tool_contract():
    from netfile_paper_extractor import (
        parse_form460_summary_with_vision,
        reset_form460_summary_run_state,
    )

    reset_form460_summary_run_state()
    expected = _form460_summary()
    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_form460_tool(expected)],
        stop_reason="tool_use",
    )
    with patch(
        "netfile_paper_extractor.extract_text_from_pdf",
        return_value="visible Form 460 text",
    ):
        result = parse_form460_summary_with_vision(
            Path("filing-460.pdf"),
            "valid-filing",
            "Richmond Neighbors",
            client,
        )

    assert result == expected
    client.messages.create.assert_called_once()


def test_current_run_summary_reconciles_after_persistence_soft_failure_with_one_paid_call():
    import load_paper_filings as loader
    import netfile_paper_extractor as extractor
    from pipelines.netfile import sync_paper_filing_reconciliation

    extractor.reset_form460_summary_run_state()
    expected = _form460_summary()
    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_form460_tool(expected)],
        stop_reason="tool_use",
    )
    filing = {
        "filing_id": "one-paid-call",
        "form_type": "Form 460",
        "committee": "Richmond Neighbors",
    }
    contribution = {
        "filing_id": "one-paid-call",
        "contributor_name": "Resident",
        "amount": 100.0,
        "date": "2026-05-01",
    }

    with patch.object(extractor, "find_committee_json", return_value=None), patch.object(
        extractor,
        "download_paper_filing",
        return_value=Path("one-paid-call.pdf"),
    ), patch.object(
        extractor,
        "extract_text_from_pdf",
        return_value="visible Form 460 text",
    ), patch.object(
        extractor,
        "parse_filing_with_claude",
        return_value=[contribution],
    ), patch.object(
        extractor,
        "write_json_atomic",
    ), patch.object(
        loader,
        "persist_form460_summary",
        return_value=False,
    ) as persist:
        artifact = extractor.extract_committee(
            "Richmond Neighbors",
            [filing],
            client,
        )

    assert artifact["filings"][0]["form_summary"] == expected
    persist.assert_called_once()
    client.messages.create.assert_called_once()

    reconciliation = MagicMock(return_value={
        "filings_examined": 1,
        "rows_synthesized": 1,
        "dollars_synthesized": 200.0,
        "filings_already_matched": 0,
        "filings_over": 0,
        "over_filings": [],
    })
    with patch.object(
        loader,
        "_load_form_summary_cache",
        return_value={"_committees": {}},
    ), patch(
        "netfile_client.fetch_filing_rss",
        return_value=[filing],
    ), patch(
        "llm_client.LLMClient",
        return_value=client,
    ), patch.object(
        loader,
        "_save_form_summary_cache",
        return_value=True,
    ) as save_cache, patch.object(
        loader,
        "reconcile_paper_filings_to_forms",
        reconciliation,
    ):
        result = sync_paper_filing_reconciliation(
            MagicMock(),
            "0660620",
        )

    # The immediate one-row write soft-failed, then the required automatic
    # cache save recovered durability. Reconciliation reuses the exact result
    # without a second paid call.
    client.messages.create.assert_called_once()
    save_cache.assert_called_once()
    passed_cache = reconciliation.call_args.kwargs["form_summary_cache"]
    assert passed_cache["one-paid-call"] == expected
    assert result["retryable_incomplete"] is False


def test_invalid_summary_is_not_cached_or_paid_twice_and_reconciliation_retries():
    import load_paper_filings as loader
    import netfile_paper_extractor as extractor
    from pipelines.netfile import sync_paper_filing_reconciliation

    extractor.reset_form460_summary_run_state()
    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_form460_tool(_form460_summary())],
        stop_reason="max_tokens",
    )
    with patch.object(
        extractor,
        "extract_text_from_pdf",
        return_value="visible Form 460 text",
    ), pytest.raises(extractor.Form460SummaryIncompleteError):
        extractor.parse_form460_summary_with_vision(
            Path("truncated.pdf"),
            "truncated-filing",
            "Richmond Neighbors",
            client,
        )

    filing = {
        "filing_id": "truncated-filing",
        "form_type": "Form 460",
        "committee": "Richmond Neighbors",
    }
    reconciliation = MagicMock(return_value={
        "filings_examined": 0,
        "rows_synthesized": 0,
        "dollars_synthesized": 0.0,
        "filings_already_matched": 0,
        "filings_over": 0,
        "over_filings": [],
    })
    with patch.object(
        loader,
        "_load_form_summary_cache",
        return_value={"_committees": {}},
    ), patch(
        "netfile_client.fetch_filing_rss",
        return_value=[filing],
    ), patch(
        "llm_client.LLMClient",
        return_value=client,
    ), patch.object(
        loader,
        "_save_form_summary_cache",
    ) as save_cache, patch.object(
        loader,
        "reconcile_paper_filings_to_forms",
        reconciliation,
    ):
        result = sync_paper_filing_reconciliation(
            MagicMock(),
            "0660620",
        )

    client.messages.create.assert_called_once()
    save_cache.assert_not_called()
    reconciliation.assert_not_called()
    assert result["retryable_incomplete"] is True
    assert result["form460_summaries_pending"] == 1
    assert result["cache_complete_for_reconciliation"] is False


def test_automatic_reconciliation_db_cache_read_failure_never_reconciles():
    import load_paper_filings as loader
    from pipelines.netfile import sync_paper_filing_reconciliation

    reconciliation = MagicMock()
    load_error = loader.FormSummaryCacheDurabilityError(
        "durable form_summary_cache read failed"
    )
    with patch.object(
        loader,
        "_load_form_summary_cache",
        side_effect=load_error,
    ) as load_cache, patch.object(
        loader,
        "reconcile_paper_filings_to_forms",
        reconciliation,
    ):
        result = sync_paper_filing_reconciliation(
            MagicMock(),
            "0660620",
        )

    load_cache.assert_called_once_with(require_durable_db=True)
    reconciliation.assert_not_called()
    assert result["durable_cache_ready"] is False
    assert result["cache_complete_for_reconciliation"] is False
    assert result["retryable_incomplete"] is True
    assert "cache read failed" in result["incomplete_reasons"][0]


def test_current_run_memory_does_not_conceal_required_db_cache_write_failure():
    import load_paper_filings as loader
    import netfile_paper_extractor as extractor
    from pipelines.netfile import sync_paper_filing_reconciliation

    extractor.reset_form460_summary_run_state()
    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_form460_tool(_form460_summary())],
        stop_reason="tool_use",
    )
    with patch.object(
        extractor,
        "extract_text_from_pdf",
        return_value="visible Form 460 text",
    ):
        extractor.parse_form460_summary_with_vision(
            Path("memory-only.pdf"),
            "memory-only-filing",
            "Richmond Neighbors",
            client,
        )

    filing = {
        "filing_id": "memory-only-filing",
        "form_type": "Form 460",
        "committee": "Richmond Neighbors",
    }
    reconciliation = MagicMock()
    write_error = loader.FormSummaryCacheDurabilityError(
        "durable form_summary_cache write failed"
    )
    with patch.object(
        loader,
        "_load_form_summary_cache",
        return_value={"_committees": {}},
    ), patch(
        "netfile_client.fetch_filing_rss",
        return_value=[filing],
    ), patch.object(
        loader,
        "_save_form_summary_cache",
        side_effect=write_error,
    ) as save_cache, patch.object(
        loader,
        "reconcile_paper_filings_to_forms",
        reconciliation,
    ):
        result = sync_paper_filing_reconciliation(
            MagicMock(),
            "0660620",
        )

    client.messages.create.assert_called_once()
    save_cache.assert_called_once()
    assert save_cache.call_args.kwargs["require_durable_db"] is True
    reconciliation.assert_not_called()
    assert result["durable_cache_ready"] is False
    assert result["cache_complete_for_reconciliation"] is False
    assert result["retryable_incomplete"] is True
    assert "cache write failed" in result["incomplete_reasons"][0]


def test_local_cache_fallback_is_dev_only_when_db_read_fails(tmp_path):
    import json
    import load_paper_filings as loader

    fallback_path = tmp_path / "form_summaries.json"
    fallback = {
        "local-filing": _form460_summary(),
        "_committees": {"local-filing": "Richmond Neighbors"},
    }
    fallback_path.write_text(json.dumps(fallback), encoding="utf-8")
    with patch.object(loader, "FORM_SUMMARY_CACHE", fallback_path), patch(
        "db.get_connection",
        side_effect=RuntimeError("database offline"),
    ):
        assert loader._load_form_summary_cache() == fallback
        with pytest.raises(loader.FormSummaryCacheDurabilityError):
            loader._load_form_summary_cache(require_durable_db=True)


def test_automatic_cache_write_failure_does_not_create_local_authority(tmp_path):
    import load_paper_filings as loader

    fallback_path = tmp_path / "form_summaries.json"
    cache = {
        "current-filing": _form460_summary(),
        "_committees": {"current-filing": "Richmond Neighbors"},
    }
    with patch.object(loader, "FORM_SUMMARY_CACHE", fallback_path), patch(
        "db.get_connection",
        side_effect=RuntimeError("database write unavailable"),
    ), pytest.raises(loader.FormSummaryCacheDurabilityError):
        loader._save_form_summary_cache(
            cache,
            require_durable_db=True,
        )

    assert not fallback_path.exists()


@pytest.mark.parametrize(
    "response",
    [
        _response(content=[]),
        _response(content=[_tool_input({"_raw": "{"})]),
        _response(content=[_tool_input({"contributions": "not-a-list"})]),
        _response(content=[_tool_input({"contributions": [1]})]),
        _response(
            content=[_tool_input({"contributions": []})],
            stop_reason="max_tokens",
        ),
    ],
)
def test_incomplete_text_results_are_not_valid_empty_results(response):
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        parse_filing_with_claude,
    )

    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(TextExtractionIncompleteError):
        parse_filing_with_claude(
            "visible filing text", "460", "filing-1", "Committee", client
        )


def test_explicit_empty_text_tool_result_is_complete():
    from netfile_paper_extractor import parse_filing_with_claude

    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_tool_input({"contributions": []})]
    )

    assert parse_filing_with_claude(
        "visible filing text", "497", "filing-1", "Committee", client
    ) == []


def test_valid_nonempty_text_row_is_normalized_after_validation():
    from netfile_paper_extractor import parse_filing_with_claude

    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_tool_input({"contributions": [{
            "contributor_name": "Resident",
            "amount": 100.0,
            "date": "2026-08-01",
            "entity_code": "IND",
        }]})],
    )

    rows = parse_filing_with_claude(
        "visible filing text",
        "460",
        "filing-valid-row",
        "Richmond Neighbors",
        client,
    )

    assert rows[0]["filing_id"] == "filing-valid-row"
    assert rows[0]["contributor_name"] == "Resident"
    assert rows[0]["city"] == ""


@pytest.mark.parametrize(
    "row",
    [
        {"contributor_name": "Resident", "amount": 100.0},
        {"contributor_name": "Resident", "amount": "100", "date": "2026-08-01"},
        {"contributor_name": "Resident", "amount": True, "date": "2026-08-01"},
        {"contributor_name": "Resident", "amount": float("nan"), "date": "2026-08-01"},
        {"contributor_name": "Resident", "amount": 100.0, "date": "08/01/2026"},
        {
            "contributor_name": "Resident",
            "amount": 100.0,
            "date": "2026-08-01",
            "entity_code": "INVALID",
        },
        {
            "contributor_name": "Resident",
            "amount": 100.0,
            "date": "2026-08-01",
            "unsupported": "field",
        },
    ],
)
def test_malformed_nonempty_text_contribution_rows_fail_closed(row):
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        parse_filing_with_claude,
    )

    client = MagicMock()
    client.messages.create.return_value = _response(
        content=[_tool_input({"contributions": [row]})],
    )

    with pytest.raises(TextExtractionIncompleteError):
        parse_filing_with_claude(
            "visible filing text",
            "460",
            "filing-malformed",
            "Richmond Neighbors",
            client,
        )


def test_text_contribution_requires_named_tool_without_text_companion():
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        parse_filing_with_claude,
    )

    valid_row = {
        "contributor_name": "Resident",
        "amount": 100.0,
        "date": "2026-08-01",
    }
    responses = [
        _response(content=[SimpleNamespace(
            type="tool_use",
            name="wrong_tool",
            input={"contributions": [valid_row]},
        )]),
        _response(content=[
            SimpleNamespace(type="text", text="Here is the result"),
            _tool_input({"contributions": [valid_row]}),
        ]),
        _response(content=[
            _tool_input({"contributions": [valid_row]}),
            _tool_input({"contributions": [valid_row]}),
        ]),
    ]
    for response in responses:
        client = MagicMock()
        client.messages.create.return_value = response
        with pytest.raises(TextExtractionIncompleteError):
            parse_filing_with_claude(
                "visible filing text",
                "460",
                "filing-contract",
                "Richmond Neighbors",
                client,
            )


def _mock_connection():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cursor


def test_db_idempotency_includes_contributions_and_zero_receipts():
    from netfile_paper_extractor import db_filing_ids_extracted

    conn, cursor = _mock_connection()
    cursor.fetchall.side_effect = [
        [("from-contributions",)],
        [("from-zero-receipt",)],
    ]

    with patch("db.get_connection", return_value=conn):
        result = db_filing_ids_extracted(
            {"from-contributions", "from-zero-receipt", "pending"}
        )

    assert result == {"from-contributions", "from-zero-receipt"}
    assert cursor.execute.call_count == 2
    assert "FROM contributions" in cursor.execute.call_args_list[0].args[0]
    assert "FROM paper_filing_zero_results" in cursor.execute.call_args_list[1].args[0]
    conn.close.assert_called_once()


def test_db_idempotency_preserves_contribution_ids_before_migration_rollout():
    from netfile_paper_extractor import db_filing_ids_extracted

    conn, cursor = _mock_connection()
    cursor.execute.side_effect = [None, RuntimeError("relation does not exist")]
    cursor.fetchall.return_value = [("already-loaded",)]

    with patch("db.get_connection", return_value=conn):
        result = db_filing_ids_extracted({"already-loaded", "zero-result"})

    assert result == {"already-loaded"}
    conn.rollback.assert_called_once()


def test_zero_receipt_insert_is_idempotent_and_has_d1_provenance():
    from netfile_paper_extractor import persist_paper_filing_zero_result

    conn, cursor = _mock_connection()
    with patch("db.get_connection", return_value=conn):
        assert persist_paper_filing_zero_result(
            filing_id="filing-1",
            committee="Richmond Neighbors",
            form_type="497",
            result_kind="extractor_returned_zero",
            extraction_method="text_llm",
            extraction_model="deepseek-v4-pro",
            source_url="https://netfile.com/Connect2/api/public/image/filing-1",
        )

    sql, params = cursor.execute.call_args.args
    assert "ON CONFLICT (city_fips, filing_id) DO NOTHING" in sql
    assert "source_url, source_tier, confidence_score" in sql
    assert params == (
        "0660620",
        "filing-1",
        "Richmond Neighbors",
        "497",
        "extractor_returned_zero",
        "text_llm",
        "deepseek-v4-pro",
        "https://netfile.com/Connect2/api/public/image/filing-1",
    )
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_current_run_form460_summary_persists_without_touching_zero_receipts():
    from load_paper_filings import persist_form460_summary

    conn, cursor = _mock_connection()
    summary = _form460_summary()
    with patch("db.get_connection", return_value=conn):
        assert persist_form460_summary(
            filing_id="filing-summary",
            committee="Richmond Neighbors",
            summary=summary,
        )

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("DELETE FROM form_summary_cache" in sql for sql in sql_statements)
    assert any("INSERT INTO form_summary_cache" in sql for sql in sql_statements)
    assert all("paper_filing_zero_results" not in sql for sql in sql_statements)
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_current_run_amendment_replaces_prior_period_in_reconciliation_cache():
    from load_paper_filings import _put_form_summary_in_cache

    old_summary = _form460_summary(total_this_period=1000.0)
    cache = {
        "old-filing": old_summary,
        "_committees": {"old-filing": "Richmond Neighbors"},
    }
    amended = _form460_summary(total_this_period=1200.0)

    _put_form_summary_in_cache(
        cache,
        filing_id="amended-filing",
        committee="Richmond Neighbors",
        summary=amended,
    )

    assert "old-filing" not in cache
    assert "old-filing" not in cache["_committees"]
    assert cache["amended-filing"] == amended


@pytest.mark.parametrize(
    "cache, message",
    [
        (
            {"bad-filing": _form460_summary(), "_committees": {}},
            "no committee mapping",
        ),
        (
            {
                "bad-filing": _form460_summary(period_end="<UNKNOWN>"),
                "_committees": {"bad-filing": "Richmond Neighbors"},
            },
            "malformed reporting period",
        ),
        (
            {
                "bad-filing": _form460_summary(
                    monetary_this_period=float("nan")
                ),
                "_committees": {"bad-filing": "Richmond Neighbors"},
            },
            "invalid monetary total",
        ),
    ],
)
def test_reconciliation_preflight_rejects_unsafe_cache_before_delete(
    cache, message,
):
    from load_paper_filings import (
        FormSummaryCacheDurabilityError,
        reconcile_paper_filings_to_forms,
    )

    conn, cursor = _mock_connection()
    with pytest.raises(FormSummaryCacheDurabilityError, match=message):
        reconcile_paper_filings_to_forms(
            conn,
            form_summary_cache=cache,
        )

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert all("DELETE FROM contributions" not in sql for sql in sql_statements)
    conn.commit.assert_not_called()


def test_reconciliation_unknown_committee_fails_before_delete():
    from load_paper_filings import (
        FormSummaryCacheDurabilityError,
        reconcile_paper_filings_to_forms,
    )

    conn, cursor = _mock_connection()
    cursor.fetchone.return_value = None
    cache = {
        "unknown-filing": _form460_summary(),
        "_committees": {"unknown-filing": "Unknown Committee"},
    }

    with pytest.raises(FormSummaryCacheDurabilityError, match="unknown committee"):
        reconcile_paper_filings_to_forms(
            conn,
            form_summary_cache=cache,
        )

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert all("DELETE FROM contributions" not in sql for sql in sql_statements)
    conn.commit.assert_not_called()


def test_reconciliation_partial_cache_cannot_erase_prior_filing():
    from load_paper_filings import (
        FormSummaryCacheDurabilityError,
        reconcile_paper_filings_to_forms,
    )

    conn, cursor = _mock_connection()
    cursor.fetchone.side_effect = [
        ("committee-id",),
        (100.0,),
    ]
    cursor.fetchall.return_value = [
        ("missing-prior-filing", "committee-id", "2025-12-31"),
    ]
    cache = {
        "current-filing": _form460_summary(),
        "_committees": {"current-filing": "Richmond Neighbors"},
    }

    with pytest.raises(FormSummaryCacheDurabilityError, match="missing-prior-filing"):
        reconcile_paper_filings_to_forms(
            conn,
            form_summary_cache=cache,
        )

    sql_statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert all("DELETE FROM contributions" not in sql for sql in sql_statements)
    conn.commit.assert_not_called()


def test_reconciliation_amendment_period_covers_superseded_filing_id():
    from load_paper_filings import reconcile_paper_filings_to_forms

    conn, cursor = _mock_connection()
    cursor.fetchone.side_effect = [
        ("committee-id",),
        (100.0,),
    ]
    cursor.fetchall.return_value = [
        ("superseded-filing", "committee-id", "2026-06-30"),
    ]
    cursor.rowcount = 1
    cache = {
        "amended-filing": _form460_summary(),
        "_committees": {"amended-filing": "Richmond Neighbors"},
    }

    with patch("load_paper_filings.load_contributions_to_db") as loader:
        result = reconcile_paper_filings_to_forms(
            conn,
            form_summary_cache=cache,
        )

    assert result["rows_synthesized"] == 1
    assert loader.call_args.kwargs["commit"] is False
    conn.commit.assert_called_once()


def test_reconciliation_replacement_is_one_caller_owned_transaction():
    from load_paper_filings import reconcile_paper_filings_to_forms

    conn, cursor = _mock_connection()
    cursor.fetchone.side_effect = [
        ("committee-id",),  # complete-cache committee preflight
        (100.0,),           # existing itemized monetary total
        (1,),               # prior UNI count
    ]
    cursor.rowcount = 1
    cache = {
        "filing-atomic": _form460_summary(monetary_this_period=1200.0),
        "_committees": {"filing-atomic": "Richmond Neighbors"},
    }

    with patch("load_paper_filings.load_contributions_to_db") as loader:
        result = reconcile_paper_filings_to_forms(
            conn,
            form_summary_cache=cache,
        )

    assert result["rows_synthesized"] == 1
    loader.assert_called_once()
    assert loader.call_args.kwargs["commit"] is False
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()


def test_reconciliation_rolls_back_delete_when_replacement_fails():
    from load_paper_filings import reconcile_paper_filings_to_forms

    conn, cursor = _mock_connection()
    cursor.fetchone.side_effect = [
        ("committee-id",),
        (100.0,),
        (1,),
    ]
    cursor.rowcount = 1
    cache = {
        "filing-atomic": _form460_summary(monetary_this_period=1200.0),
        "_committees": {"filing-atomic": "Richmond Neighbors"},
    }

    with patch(
        "load_paper_filings.load_contributions_to_db",
        side_effect=RuntimeError("insert failed"),
    ) as loader, pytest.raises(RuntimeError, match="insert failed"):
        reconcile_paper_filings_to_forms(
            conn,
            form_summary_cache=cache,
        )

    assert loader.call_args.kwargs["commit"] is False
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()


def test_form_410_receipt_is_persisted_only_after_json_write():
    from netfile_paper_extractor import extract_committee

    events: list[str] = []
    filing = {
        "filing_id": "filing-410",
        "form_type": "Form 410 - Statement of Organization",
        "document_url": "https://netfile.example/public/image/filing-410",
    }

    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing",
        return_value=Path("filing-410.pdf"),
    ), patch(
        "netfile_paper_extractor.write_json_atomic",
        side_effect=lambda *_: events.append("json"),
    ), patch(
        "netfile_paper_extractor.persist_paper_filing_zero_result",
        side_effect=lambda **_: events.append("receipt") or True,
    ) as persist:
        result = extract_committee("Richmond Neighbors", [filing], MagicMock())

    assert events == ["json", "receipt"]
    assert result["filings"][0]["form"] == "410"
    assert result["contributions"] == []
    assert persist.call_args.kwargs == {
        "filing_id": "filing-410",
        "committee": "Richmond Neighbors",
        "form_type": "410",
        "result_kind": "not_contribution_form",
        "extraction_method": "rss_classification",
        "extraction_model": "deterministic",
        "source_url": "https://netfile.example/public/image/filing-410",
        "city_fips": "0660620",
    }


@pytest.mark.parametrize(
    ("form_type", "text", "parser_name", "expected_method"),
    [
        ("Form 460", "visible text", "parse_filing_with_claude", "text_llm"),
        ("Form 497", "", "parse_filing_with_vision", "vision_llm"),
    ],
)
def test_valid_empty_llm_result_gets_durable_receipt(
    form_type, text, parser_name, expected_method
):
    from netfile_paper_extractor import extract_committee

    filing = {
        "filing_id": "filing-empty",
        "form_type": form_type,
        "document_url": "https://netfile.example/public/image/filing-empty",
    }
    patches = [
        patch("netfile_paper_extractor.find_committee_json", return_value=None),
        patch(
            "netfile_paper_extractor.download_paper_filing",
            return_value=Path("filing-empty.pdf"),
        ),
        patch("netfile_paper_extractor.extract_text_from_pdf", return_value=text),
        patch(f"netfile_paper_extractor.{parser_name}", return_value=[]),
        patch("netfile_paper_extractor.parse_form460_summary_with_vision", return_value=None),
        patch("netfile_paper_extractor.write_json_atomic"),
        patch("netfile_paper_extractor.persist_paper_filing_zero_result"),
    ]

    entered = [p.start() for p in patches]
    try:
        result = extract_committee("Richmond Neighbors", [filing], MagicMock())
    finally:
        for p in reversed(patches):
            p.stop()

    persist = entered[-1]
    assert result["filings"][0]["filing_id"] == "filing-empty"
    assert result["contributions"] == []
    persist.assert_called_once()
    assert persist.call_args.kwargs["result_kind"] == "extractor_returned_zero"
    assert persist.call_args.kwargs["extraction_method"] == expected_method


def test_incomplete_text_result_remains_pending_without_receipt():
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        extract_committee,
    )

    filing = {"filing_id": "filing-pending", "form_type": "Form 460"}
    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing",
        return_value=Path("filing-pending.pdf"),
    ), patch(
        "netfile_paper_extractor.extract_text_from_pdf", return_value="visible text"
    ), patch(
        "netfile_paper_extractor.parse_filing_with_claude",
        side_effect=TextExtractionIncompleteError("missing tool result"),
    ), patch(
        "netfile_paper_extractor.write_json_atomic"
    ) as write_json, patch(
        "netfile_paper_extractor.persist_paper_filing_zero_result"
    ) as persist:
        result = extract_committee("Richmond Neighbors", [filing], MagicMock())

    assert result["filings"] == []
    assert result["contributions"] == []
    write_json.assert_not_called()
    persist.assert_not_called()


def test_nonempty_or_dry_run_never_writes_zero_receipt():
    from netfile_paper_extractor import extract_committee

    filing = {"filing_id": "filing-497", "form_type": "Form 497"}
    row = {
        "filing_id": "filing-497",
        "contributor_name": "Resident",
        "amount": 100,
        "date": "2026-08-01",
    }
    common = (
        patch("netfile_paper_extractor.find_committee_json", return_value=None),
        patch(
            "netfile_paper_extractor.download_paper_filing",
            return_value=Path("filing-497.pdf"),
        ),
        patch("netfile_paper_extractor.extract_text_from_pdf", return_value="text"),
        patch("netfile_paper_extractor.write_json_atomic"),
        patch("netfile_paper_extractor.persist_paper_filing_zero_result"),
    )

    with common[0], common[1], common[2], patch(
        "netfile_paper_extractor.parse_filing_with_claude", return_value=[row]
    ), common[3], common[4] as persist:
        extract_committee("Richmond Neighbors", [filing], MagicMock())
        persist.assert_not_called()

    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing",
        return_value=Path("filing-497.pdf"),
    ), patch(
        "netfile_paper_extractor.extract_text_from_pdf", return_value="text"
    ), patch(
        "netfile_paper_extractor.parse_filing_with_claude", return_value=[]
    ), patch(
        "netfile_paper_extractor.persist_paper_filing_zero_result"
    ) as persist:
        extract_committee(
            "Richmond Neighbors", [filing], MagicMock(), dry_run=True
        )
        persist.assert_not_called()


def test_migration_128_declares_non_null_d1_quartet_and_operator_rls():
    migration = (
        Path(__file__).parent.parent
        / "src"
        / "migrations"
        / "128_paper_filing_zero_results.sql"
    ).read_text(encoding="utf-8")

    for column in (
        "source_url TEXT NOT NULL",
        "extracted_at TIMESTAMPTZ NOT NULL",
        "source_tier SMALLINT NOT NULL",
        "confidence_score NUMERIC(3,2) NOT NULL",
    ):
        assert column in migration
    assert "PRIMARY KEY (city_fips, filing_id)" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "TO service_role" in migration
