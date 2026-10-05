"""Privacy/precision invariants for the independently reviewed local projection."""
from decimal import Decimal
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from export_core import COLUMNS, encode_row, projection_queries  # noqa: E402


def test_only_public_relation_and_field_allowlists() -> None:
    forbidden_fields = {"email", "phone", "address", "donor_address", "raw_text", "metadata",
                        "payload", "reviewed_by", "claim_token", "plain_language_summary",
                        "bio_summary", "vote_explainer", "embedding"}
    assert not forbidden_fields.intersection(field for columns in COLUMNS.values() for field in columns)
    queries = projection_queries()
    assert len(queries) == 13
    assert not re.search(r"SELECT\s+(?:\w+\.)?\*", "\n".join(queries.values()), re.I)
    referenced = set(re.findall(r"\b(?:FROM|JOIN)\s+public\.([a-z_]+)", "\n".join(queries.values()), re.I))
    assert referenced == set(COLUMNS)


def test_decimal_and_line_boundaries_are_preserved() -> None:
    encoded = encode_row(("amount", "speaker_name"), (Decimal("9007199254740993.01"), "A\nB café"))
    assert encoded.count(b"\n") == 1
    assert json.loads(encoded) == {"amount": "9007199254740993.01", "speaker_name": "A\nB café"}


def test_held_vote_identity_and_finance_publication_boundary() -> None:
    queries = projection_queries()
    for name in ("motions", "votes"):
        assert "9cf375c8-edc1-413c-8ee0-6485348fbc6f" in queries[name]
        assert "5f560013-daea-499a-8ecd-ca1a089c8a0c" in queries[name]
        assert "lower(ai.item_number) = 'j-2'" in queries[name]
    money = queries["finance_public_events"]
    assert "2026-01-01" in money and "2026-11-03" in money
    assert "confidence_score >= 0.90" in money
    assert "reconciliation_status IN ('source_reported', 'matched_exact')" in money
    assert "limitations" in queries["finance_public_coverage"]


def test_bootstrap_contains_no_provider_or_private_runtime() -> None:
    bootstrap = (HERE / "public-core.sql").read_text(encoding="utf-8")
    assert not re.search(r"CREATE\s+(?:EXTENSION|SCHEMA\s+(?:auth|vault))", bootstrap, re.I)
    for table in ("operator_config", "email_subscribers", "search_queries", "documents", "donors"):
        assert f"CREATE TABLE public.{table} " not in bootstrap
    assert "LANGUAGE sql STABLE SECURITY INVOKER" in bootstrap
    assert "basic_core_conflict_flags_empty CHECK (false)" in bootstrap
    assert "core_meeting_source_guid" in bootstrap
    # Retirement must remain possible so source revisions cannot force deletes.
    assert "source_cancelled_at IS NULL)" not in bootstrap
    assert "agenda_source_retired_at IS NULL)" not in bootstrap
