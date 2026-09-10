"""Two fixed organization-source watches; no production requests or sponsor inference."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock

import pytest

import paper_finance_review as paper


NOW = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
PDF = b"%PDF-reviewed-organization-fixture"


def fixture():
    committees, inventories, metadata, pdfs = [], {}, {}, {}
    for fppc, portal, fid, name in [
        ("1490887", "216706544", "216859596", "Safe Richmond Neighborhoods"),
        ("1390351", "168662145", "217301754", "East Bay Working Families"),
    ]:
        source = {"filing_id": fid, "form": "410", "filed_at": "2026-08-27",
                  "source_url": f"{paper.CONNECT}/image/{fid}", "sha256": paper.sha(PDF), "reviewed_pages": [1, 2, 3]}
        committee = {"fppc_id": fppc, "portal_filer_id": portal, "display_name": name, "reported_name": name,
                     "committee_type": "City committee", "purpose": "Reported purpose", "purpose_page": 2,
                     "sponsors": [{"name": "Reviewed sponsor", "affiliation": "Reported affiliation", "page": 3}], "source": source}
        committees.append(committee)
        inventories[portal] = {"filings": [{"id": fid, "formName": "FPPC 410", "formId": paper.ORGANIZATION_FORM,
                "filerName": name, "filingDate": "2026-08-27"}], "totalCount": 0}
        metadata[fid] = {"filingId": fid, "filerName": name, "sosFilerId": fppc, "agency": "RICH",
            "formId": paper.ORGANIZATION_FORM, "isEfiled": False, "filingDate": "2026-08-27", "amends": None, "amendedBy": None}
        pdfs[fid] = PDF
    return {"schema_version": 1, "checked_at": NOW.isoformat(), "committees": committees}, inventories, metadata, pdfs


class Sources:
    def __init__(self, inventories, metadata, pdfs):
        self.inventories, self.metadata, self.pdfs = inventories, metadata, pdfs
        self.calls = []
        self.bytes = 0

    def get(self, url, cap, local_name=None):
        self.calls.append(url)
        if "/byFiler?" in url:
            portal = url.split("filerId=")[1].split("&")[0]
            payload = paper.canonical(self.inventories[portal])
        else:
            fid = local_name.split(".")[0]
            payload = self.pdfs[fid] if "/image/" in url else paper.canonical(self.metadata[fid])
        if len(payload) > cap:
            raise ValueError("Source exceeded byte cap")
        self.bytes += len(payload)
        return payload


def add_source(registry, inventories, metadata, pdfs, number=217400000, *, name=None):
    committee = registry["committees"][0]
    baseline = committee["source"]["filing_id"]
    fid = str(number)
    inventories[committee["portal_filer_id"]]["filings"].append({"id": fid, "formName": "FPPC 410 (Amendment)",
        "formId": paper.ORGANIZATION_FORM, "filingDate": "2026-09-09", "filerName": name or committee["reported_name"]})
    metadata[fid] = {**metadata[baseline], "filingId": fid, "filingDate": "2026-09-09",
                     "amends": baseline, "filerName": name or committee["reported_name"]}
    pdfs[fid] = PDF + fid.encode()
    return fid


def test_unchanged_sources_use_daily_metadata_and_weekly_bytes_without_ocr(monkeypatch):
    registry, inventories, metadata, pdfs = fixture()
    monkeypatch.setattr(paper, "prepare_pages", Mock(side_effect=AssertionError("Organization watch must not infer sponsors")))
    first = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)
    assert len(first) == 2 and not any(row["needs_packet"] for row in first)
    cache = {row["core"]["filing_id"]: row for row in first}
    sources = Sources(inventories, metadata, pdfs)
    replay = paper.acquire_organizations(registry, sources, cache, NOW + timedelta(days=1))
    assert all(not row["write_needed"] for row in replay)
    assert not any("/image/" in url for url in sources.calls)
    sources = Sources(inventories, metadata, pdfs)
    weekly = paper.acquire_organizations(registry, sources, cache, NOW + timedelta(days=7))
    assert sum("/image/" in url for url in sources.calls) == 2
    assert all(row["write_needed"] and not row["needs_packet"] for row in weekly)


def test_new_report_with_renamed_committee_prepares_explicit_resolve_only_packet():
    registry, inventories, metadata, pdfs = fixture()
    fid = add_source(registry, inventories, metadata, pdfs, name="Changed official committee name")
    rows = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)
    new = next(row for row in rows if row["core"]["filing_id"] == fid)
    packet = paper.prepare_organization_packet(new, registry["committees"][0])
    assert packet.kind is None and packet.subject == "2026-general" and new["needs_packet"]
    assert packet.evidence["previous_snapshot"] == registry["committees"][0]
    assert packet.evidence["proposed_change"]["filing"]["reported_name"] == "Changed official committee name"
    assert packet.evidence["source_versions"] == [[fid, paper.sha(pdfs[fid]), paper.sha(paper.canonical(metadata[fid]))]]
    assert "Approval records a judgment only" in packet.evidence["publication_effect"]
    assert "sponsors" not in packet.evidence["proposed_change"]
    later = {**new, "last_checked_at": (NOW + timedelta(days=1)).isoformat()}
    assert paper.prepare_organization_packet(later, registry["committees"][0]).dedup_key == packet.dedup_key


@pytest.mark.parametrize("change", ["pdf", "metadata", "superseded"])
def test_replaced_reviewed_evidence_stays_pending_until_snapshot_review(change):
    registry, inventories, metadata, pdfs = fixture()
    first = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)
    cache = {row["core"]["filing_id"]: row for row in first}
    fid = registry["committees"][0]["source"]["filing_id"]
    if change == "pdf":
        pdfs[fid] += b"replaced scan"
    elif change == "metadata":
        metadata[fid]["amends"] = "216774495"
    else:
        metadata[fid]["amendedBy"] = "217499999"
    changed = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), cache, NOW + timedelta(days=8))
    result = next(row for row in changed if row["core"]["filing_id"] == fid)
    assert result["needs_packet"] and result["write_needed"]
    cache.update({row["core"]["filing_id"]: row for row in changed})
    again = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), cache, NOW + timedelta(days=9))
    assert next(row for row in again if row["core"]["filing_id"] == fid)["needs_packet"]


def test_reviewed_registry_update_reanchors_metadata_only_after_new_byte_check():
    registry, inventories, metadata, pdfs = fixture()
    first = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)
    fid = registry["committees"][0]["source"]["filing_id"]
    metadata[fid]["amends"] = "216774495"
    registry["checked_at"] = (NOW + timedelta(days=1)).isoformat()
    sources = Sources(inventories, metadata, pdfs)
    updated = paper.acquire_organizations(registry, sources, {row["core"]["filing_id"]: row for row in first}, NOW + timedelta(days=1))
    assert all(row["write_needed"] and not row["needs_packet"] for row in updated)
    assert sum("/image/" in url for url in sources.calls) == 2


@pytest.mark.parametrize("field,value", [("agency", "OTHER"), ("sosFilerId", "1481105"),
    ("formId", "not-410"), ("filingId", "217499999"), ("filerName", "Different from inventory"),
    ("isEfiled", "false"), ("filingDate", "2026-08-28"), ("amendedBy", "../file")])
def test_wrong_independent_metadata_fails_before_any_pdf_read(field, value):
    registry, inventories, metadata, pdfs = fixture()
    metadata["216859596"][field] = value
    sources = Sources(inventories, metadata, pdfs)
    with pytest.raises(ValueError):
        paper.acquire_organizations(registry, sources, {}, NOW)
    assert not any("/image/" in url for url in sources.calls)


def test_realistic_148_row_inventory_does_not_relax_anderson_limit():
    registry, inventories, _, _ = fixture()
    committee = registry["committees"][1]
    inventory = inventories[committee["portal_filer_id"]]
    inventory["filings"] += [{"id": str(100000000 + number), "formName": "FPPC 496", "formId": "other"} for number in range(147)]
    assert len(paper.organization_inventory(inventory, committee, NOW.date())) == 1
    assert paper.MAX_SOURCES == 100
    inventory["filings"] += [{"id": str(110000000 + number)} for number in range(53)]
    with pytest.raises(ValueError):
        paper.organization_inventory(inventory, committee, NOW.date())


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(totalCount=5), lambda data: data.update(filings=[]),
    lambda data: data["filings"].append(data["filings"][0]),
    lambda data: data["filings"][0].update(id="217499999"),
    lambda data: data["filings"][0].update(formId="wrong"),
    lambda data: data["filings"][0].update(filingDate="2027-01-01"),
])
def test_missing_failed_or_ambiguous_inventory_never_creates_replacement(mutation):
    registry, inventories, metadata, pdfs = fixture()
    mutation(inventories["216706544"])
    with pytest.raises(ValueError):
        paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)


def test_two_changed_sources_per_run_rotate_to_remaining_source():
    registry, inventories, metadata, pdfs = fixture()
    first = paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)
    cache = {row["core"]["filing_id"]: row for row in first}
    for number in range(3):
        add_source(registry, inventories, metadata, pdfs, 217400000 + number)
    sources = Sources(inventories, metadata, pdfs)
    rows = paper.acquire_organizations(registry, sources, cache, NOW + timedelta(days=1))
    assert sources.prepared_count == 2 and len(sources.deferred_filings) == 1 and sources.pdf_reads <= 4
    cache.update({row["core"]["filing_id"]: row for row in rows})
    sources = Sources(inventories, metadata, pdfs)
    rows = paper.acquire_organizations(registry, sources, cache, NOW + timedelta(days=2))
    assert sources.prepared_count == 1 and not sources.deferred_filings
    assert len(rows) == 5


@pytest.mark.parametrize("mutation", [
    lambda data: data["committees"].append(deepcopy(data["committees"][0])),
    lambda data: data["committees"][0].update(portal_filer_id="214395297"),
    lambda data: data["committees"][0]["source"].update(source_url="https://other.test/document"),
    lambda data: data["committees"][0]["source"].update(sha256="unhashed"),
    lambda data: data["committees"][0]["sponsors"][0].update(page=9),
])
def test_registry_bounds_and_source_pins(mutation):
    registry, _, _, _ = fixture()
    mutation(registry)
    with pytest.raises(ValueError):
        paper.validate_organizations(registry)


def test_non_pdf_fails_without_any_extraction_or_public_mutation():
    registry, inventories, metadata, pdfs = fixture()
    original = deepcopy(registry)
    pdfs["216859596"] = b"<html>source unavailable</html>"
    with pytest.raises(ValueError):
        paper.acquire_organizations(registry, Sources(inventories, metadata, pdfs), {}, NOW)
    assert registry == original


def test_candidate_source_failure_still_checks_organizations_and_reports_failure(tmp_path, monkeypatch):
    from test_paper_finance_review import fixture as candidate_fixture
    import db
    snapshot, _, _ = candidate_fixture()
    registry, _, _, _ = fixture()
    candidate_path, organization_path, report = tmp_path / "candidate.json", tmp_path / "organizations.json", tmp_path / "report.json"
    candidate_path.write_text(json.dumps(snapshot))
    organization_path.write_text(json.dumps(registry))
    conn = MagicMock()
    monkeypatch.setattr(db, "get_connection", lambda: conn)
    monkeypatch.setattr(paper, "read_existing", lambda *_: {})
    monkeypatch.setattr(paper, "Acquisition", lambda *_: SimpleNamespace(selected_count=2, deferred_filings=[],
        prepared_count=0, pdf_reads=0, requests=4, pdf_downloads=0, bytes=1000))
    monkeypatch.setattr(paper, "acquire", Mock(side_effect=ValueError("Official candidate source was unavailable")))
    organization_pass = Mock(return_value=[])
    monkeypatch.setattr(paper, "acquire_organizations", organization_pass)
    monkeypatch.setattr(sys, "argv", ["paper_finance_review.py", "--snapshot", str(candidate_path),
        "--organizations", str(organization_path), "--report", str(report)])
    with pytest.raises(RuntimeError, match="paper"):
        paper.main()
    organization_pass.assert_called_once()
    result = json.loads(report.read_text())
    assert result["failed_sections"] == ["paper"]
    assert result["reason"] == "Official candidate source was unavailable"
    assert result["organizations"]["selected_filings"] == 2
    assert result["published"] == 0
    conn.close.assert_called_once()
