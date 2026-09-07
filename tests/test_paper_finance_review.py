"""No production requests or model calls: source, cache, OCR and publication boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

import paper_finance_review as paper


NOW = datetime(2026, 9, 6, 21, tzinfo=timezone.utc)
PDF = b"%PDF-reviewed-original-fixture"


def fixture() -> tuple[dict, dict, dict]:
    source = {"filing_id": "217094857", "form": "460", "filed_at": "2026-07-29",
              "period_start": "2026-05-29", "period_end": "2026-06-30",
              "source_url": f"{paper.CONNECT}/image/217094857", "pdf_sha256": paper.sha(PDF),
              "metadata_sha256": "a" * 64, "reviewed_pages": [1, 3]}
    snapshot = {"schema_version": 1, "committee": paper.COMMITTEE, "reviewed_at": NOW.isoformat(),
                "sources": [source], "periodic": {"filing_id": source["filing_id"]}}
    row = {"id": source["filing_id"], "formName": "FPPC 460", "formId": paper.FORM_IDS["460"],
           "filerName": paper.COMMITTEE["name"], "filingDate": source["filed_at"],
           "periodStart": source["period_start"], "periodEnd": source["period_end"]}
    info = {"filingId": source["filing_id"], "sosFilerId": "1481105", "agency": "RICH",
            "filerName": paper.COMMITTEE["name"], "formId": paper.FORM_IDS["460"], "isEfiled": False,
            "filingDate": source["filed_at"], "dateStart": source["period_start"], "dateEnd": source["period_end"],
            "amends": None, "amendedBy": None}
    source["metadata_sha256"] = paper.sha(paper.canonical(info))
    return snapshot, {"filings": [row], "totalCount": 0}, info


class Sources:
    def __init__(self, inventory: dict, metadata: dict, pdf: bytes = PDF):
        self.inventory, self.metadata, self.pdf = inventory, metadata, pdf
        self.calls = []

    def get(self, url, cap, local_name=None):
        self.calls.append(url)
        if url == paper.INVENTORY:
            return paper.canonical(self.inventory)
        return self.pdf if "/image/" in url else paper.canonical(self.metadata)


def test_checked_sources_skip_ocr_and_are_not_zero_money_findings() -> None:
    snapshot, inventory, info = fixture()
    ocr = Mock(side_effect=AssertionError("Reviewed sources must not run OCR"))
    result = paper.acquire(snapshot, Sources(inventory, info), {}, NOW, ocr)
    assert len(result) == 1 and not result[0]["needs_packet"]
    assert result[0]["pdf_sha256"] == snapshot["sources"][0]["pdf_sha256"]
    assert result[0]["pages"]["prepared_pages"] == []
    ocr.assert_not_called()


@pytest.mark.parametrize("change", [
    {"committee": {**paper.COMMITTEE, "fppc_id": "1490887"}}, {"schema_version": 2},
    {"sources": []}, {"periodic": {"filing_id": "999999999"}},
])
def test_snapshot_requires_exact_identity_and_source_pins(change) -> None:
    snapshot, _, _ = fixture()
    with pytest.raises((ValueError, KeyError)):
        paper.validate_snapshot({**snapshot, **change})


@pytest.mark.parametrize("field,value", [
    ("source_url", "https://example.test/source"), ("pdf_sha256", "unhashed"),
    ("filing_id", "../image"), ("reviewed_pages", []), ("period_end", "2026-08-31"),
])
def test_snapshot_rejects_untrusted_links_hashes_and_periods(field, value) -> None:
    snapshot, _, _ = fixture()
    snapshot["sources"][0][field] = value
    with pytest.raises((ValueError, KeyError)):
        paper.validate_snapshot(snapshot)


def test_current_inventory_keeps_late_filed_497_receipt_dates_uninferred() -> None:
    snapshot, inventory, _ = fixture()
    inventory["filings"].append({"id": "217243030", "formName": "FPPC Form 497", "formId": paper.FORM_IDS["497"],
                                 "filerName": paper.COMMITTEE["name"], "filingDate": "2026-08-17"})
    selected = paper.select_inventory(inventory, snapshot, NOW.date())
    assert selected["217243030"]["period_start"] is None
    assert selected["217243030"]["period_end"] is None
    assert "received_date" not in selected["217243030"]


@pytest.mark.parametrize("mutate", [
    lambda v: v.update(totalCount=5), lambda v: v.update(filings=[]),
    lambda v: v["filings"].append(v["filings"][0]),
    lambda v: v["filings"][0].update(filerName="Another committee"),
    lambda v: v["filings"][0].update(filingDate="2026-09-07"),
    lambda v: v["filings"][0].update(id="217094858"),
])
def test_failed_or_removed_inventory_never_replaces_source_state(mutate) -> None:
    snapshot, inventory, _ = fixture()
    mutate(inventory)
    with pytest.raises(ValueError):
        paper.select_inventory(inventory, snapshot, NOW.date())


@pytest.mark.parametrize("field,value", [("sosFilerId", "1490887"), ("formId", "other"), ("agency", "OTHER"),
                                         ("dateEnd", "2026-06-29"), ("isEfiled", "false")])
def test_independent_metadata_mismatch_fails_before_pdf_fetch(field, value) -> None:
    snapshot, inventory, info = fixture()
    info[field] = value
    acquisition = Sources(inventory, info)
    with pytest.raises(ValueError):
        paper.acquire(snapshot, acquisition, {}, NOW)
    assert not any("/image/" in call for call in acquisition.calls)


def test_unchanged_daily_replay_reads_metadata_only_and_weekly_rechecks_bytes() -> None:
    snapshot, inventory, info = fixture()
    first = paper.acquire(snapshot, Sources(inventory, info), {}, NOW)[0]
    sources = Sources(inventory, info)
    replay = paper.acquire(snapshot, sources, {"217094857": first}, NOW + timedelta(days=1))
    assert replay[0]["write_needed"] is False
    assert not any("/image/" in call for call in sources.calls)
    sources = Sources(inventory, info)
    later = paper.acquire(snapshot, sources, {"217094857": first}, NOW + timedelta(days=8))
    assert later[0]["write_needed"] is True and later[0]["needs_packet"] is False
    assert sum("/image/" in call for call in sources.calls) == 1


def test_metadata_lineage_change_forces_pdf_read_and_review(monkeypatch) -> None:
    snapshot, inventory, info = fixture()
    first = paper.acquire(snapshot, Sources(inventory, info), {}, NOW)[0]
    info["amendedBy"] = "217999999"
    monkeypatch.setattr(paper, "prepare_pages", lambda *_: {"prepared_pages": [], "omitted_pages": 0})
    sources = Sources(inventory, info)
    record = paper.acquire(snapshot, sources, {"217094857": first}, NOW)[0]
    assert record["needs_packet"] and any("/image/" in call for call in sources.calls)


@pytest.mark.parametrize("change", ["metadata_bytes", "electronic_flag", "snapshot_pin"])
def test_identical_pdf_does_not_hide_changed_metadata_or_wrong_snapshot_pin(monkeypatch, change) -> None:
    snapshot, inventory, info = fixture()
    first = paper.acquire(snapshot, Sources(inventory, info), {}, NOW)[0]
    if change == "metadata_bytes":
        info["newSourceField"] = "changed source metadata"
    elif change == "electronic_flag":
        info["isEfiled"] = True
    else:
        snapshot["sources"][0]["metadata_sha256"] = "b" * 64
    monkeypatch.setattr(paper, "prepare_pages", lambda *_: {"prepared_pages": [{"page": 1}], "omitted_pages": 0})
    sources = Sources(inventory, info)
    record = paper.acquire(snapshot, sources, {"217094857": first}, NOW)[0]
    assert record["needs_packet"] and record["write_needed"]
    # A changed source version must be retained even when the parsed core is
    # identical. A changed snapshot pin alone still exposes the cached source.
    if change != "snapshot_pin":
        assert record["write_needed"] and any("/image/" in call for call in sources.calls)
        assert record["metadata_sha256"] != first["metadata_sha256"]


def test_inventory_keeps_intermediate_periods_and_new_old_period_amendments() -> None:
    snapshot, inventory, _ = fixture()
    for fid, start, end, filed in [
        ("217999901", "2026-07-01", "2026-09-30", "2026-10-05"),
        ("217999902", "2026-10-01", "2026-10-17", "2026-10-20"),
        ("217999903", "2025-01-01", "2025-12-31", "2026-10-21"),
    ]:
        inventory["filings"].append({**inventory["filings"][0], "id": fid, "periodStart": start,
            "periodEnd": end, "filingDate": filed})
    assert set(paper.select_inventory(inventory, snapshot, datetime(2026, 10, 22).date())) == {
        "217094857", "217999901", "217999902", "217999903"}


class ManySources(Sources):
    def get(self, url, cap, local_name=None):
        self.calls.append(url)
        if url == paper.INVENTORY:
            return paper.canonical(self.inventory)
        fid = local_name.split(".")[0]
        return self.pdf + fid.encode() if "/image/" in url else paper.canonical(self.metadata[fid])


def test_five_changed_sources_make_bounded_progress_and_expired_pending_does_not_consume_cap(monkeypatch) -> None:
    snapshot, inventory, info = fixture()
    metadata = {info["filingId"]: info}
    for number in range(5):
        fid = str(217999901 + number)
        inventory["filings"].append({"id": fid, "formName": "FPPC Form 497", "formId": paper.FORM_IDS["497"],
            "filerName": paper.COMMITTEE["name"], "filingDate": "2026-08-17"})
        metadata[fid] = {**info, "filingId": fid, "formId": paper.FORM_IDS["497"], "filingDate": "2026-08-17"}
    prepared = {"prepared_pages": [{"page": 1, "method": "local_tesseract"}], "omitted_pages": 0}
    preparation = Mock(return_value=prepared)
    monkeypatch.setattr(paper, "prepare_pages", preparation)
    sources = ManySources(inventory, metadata)
    # Baseline bytes are exact in this fixture as in a controlled initial seed.
    snapshot["sources"][0]["pdf_sha256"] = paper.sha(PDF + b"217094857")
    first = paper.acquire(snapshot, sources, {}, NOW)
    assert sources.prepared_count == 4 and len(sources.deferred_filings) == 1
    assert len(first) == 5  # One reviewed baseline, four new prepared sources.
    cache = {record["core"]["filing_id"]: record for record in first}
    # Even an expired outstanding packet with unchanged source bytes only
    # requires a hash recheck, not another preparation allowance.
    sources = ManySources(inventory, metadata)
    second = paper.acquire(snapshot, sources, cache, NOW + timedelta(days=8))
    assert len(second) == 6 and not sources.deferred_filings
    assert sources.prepared_count == 1 and preparation.call_count == 5


def test_unavailable_ocr_backlog_rotates_to_unseen_sources_first(monkeypatch) -> None:
    snapshot, inventory, info = fixture()
    metadata = {info["filingId"]: info}
    snapshot["sources"][0]["pdf_sha256"] = paper.sha(PDF + b"217094857")
    for number in range(5):
        fid = str(217999901 + number)
        inventory["filings"].append({"id": fid, "formName": "FPPC Form 497", "formId": paper.FORM_IDS["497"],
            "filerName": paper.COMMITTEE["name"], "filingDate": "2026-08-17"})
        metadata[fid] = {**info, "filingId": fid, "formId": paper.FORM_IDS["497"], "filingDate": "2026-08-17"}
    monkeypatch.setattr(paper, "prepare_pages", lambda *_: {
        "prepared_pages": [{"page": 1, "method": "ocr_unavailable"}], "omitted_pages": 0})
    initial = paper.acquire(snapshot, ManySources(inventory, metadata), {}, NOW)
    cache = {record["core"]["filing_id"]: record for record in initial}
    sources = ManySources(inventory, metadata)
    second = paper.acquire(snapshot, sources, cache, NOW + timedelta(days=1))
    assert "217999905" in {record["core"]["filing_id"] for record in second}
    assert sources.prepared_count == 4 and len(sources.deferred_filings) == 1


def growing_reviewed_fixture(count: int) -> tuple[dict, dict, dict]:
    snapshot, inventory, info = fixture()
    original_source, original_row = snapshot["sources"][0], inventory["filings"][0]
    snapshot["sources"], inventory["filings"], metadata = [], [], {}
    for number in range(count):
        fid = str(217094857 + number)
        metadata[fid] = {**info, "filingId": fid}
        snapshot["sources"].append({**original_source, "filing_id": fid,
            "source_url": f"{paper.CONNECT}/image/{fid}", "pdf_sha256": paper.sha(PDF + fid.encode()),
            "metadata_sha256": paper.sha(paper.canonical(metadata[fid]))})
        inventory["filings"].append({**original_row, "id": fid})
    return snapshot, inventory, metadata


def test_growing_baseline_exceeds_one_run_without_stopping_discovery() -> None:
    snapshot, inventory, metadata = growing_reviewed_fixture(20)
    assert len(paper.validate_snapshot(snapshot)) == 20
    sources = ManySources(inventory, metadata)
    first = paper.acquire(snapshot, sources, {}, NOW)
    assert len(first) == 16 and sources.pdf_reads == 16 and len(sources.deferred_filings) == 4
    cache = {record["core"]["filing_id"]: record for record in first}
    sources = ManySources(inventory, metadata)
    second = paper.acquire(snapshot, sources, cache, NOW + timedelta(days=1))
    assert len(second) == 20 and sources.pdf_reads == 4 and not sources.deferred_filings
    assert not any(record["needs_packet"] for record in second)


def test_byte_budget_defers_without_aborting_and_expired_sources_progress() -> None:
    snapshot, inventory, metadata = growing_reviewed_fixture(20)

    class LargeSources(ManySources):
        def __init__(self):
            super().__init__(inventory, metadata)
            self.bytes = 0

        def get(self, url, cap, local_name=None):
            result = super().get(url, cap, local_name)
            # Model 5 MiB source documents without allocating repeated fixtures.
            self.bytes += 5 * 1024 * 1024 if "/image/" in url else len(result)
            return result

    cache = {}
    for number in range(4):
        sources = LargeSources()
        records = paper.acquire(snapshot, sources, cache, NOW + timedelta(days=number))
        assert sources.bytes <= paper.MAX_RUN_BYTES
        assert sources.pdf_reads <= 6
        cache.update({record["core"]["filing_id"]: record for record in records})
    assert len(cache) == 20 and not sources.deferred_filings
    # Repeat on a fully expired cache: old checks cannot monopolize later polls.
    for number in range(4):
        sources = LargeSources()
        records = paper.acquire(snapshot, sources, cache, NOW + timedelta(days=14 + number))
        assert sources.bytes <= paper.MAX_RUN_BYTES
        cache.update({record["core"]["filing_id"]: record for record in records})
    assert not sources.deferred_filings
    assert all(datetime.fromisoformat(record["last_checked_at"]) >= NOW + timedelta(days=14) for record in cache.values())


def test_snapshot_and_inventory_keep_the_official_hundred_source_bound() -> None:
    snapshot, inventory, _ = growing_reviewed_fixture(100)
    assert len(paper.select_inventory(inventory, snapshot, NOW.date())) == 100
    snapshot, inventory, _ = growing_reviewed_fixture(101)
    with pytest.raises(ValueError):
        paper.select_inventory(inventory, snapshot, NOW.date())


def test_changed_pdf_prepares_private_source_and_address_free_resolve_only_packet(monkeypatch) -> None:
    snapshot, inventory, info = fixture()
    transcript = [{"text": text} for text in ["Monetary contributions", "9140.00", "09/02/2026", "123 Private Street", "Donor Name"]]
    pages = {"prepared_pages": [paper.safe_candidates(transcript, 3)], "omitted_pages": 0,
             "private_transcript": transcript}
    monkeypatch.setattr(paper, "prepare_pages", lambda *_: pages)
    record = paper.acquire(snapshot, Sources(inventory, info, PDF + b"changed"), {}, NOW)[0]
    packet = paper.prepare_packet(record, snapshot["sources"][0], snapshot)
    assert record["needs_packet"] and record["pages"]["private_transcript"] == transcript
    assert packet.kind is None
    assert packet.evidence["source_pdf_sha256"] == paper.sha(PDF + b"changed")
    assert packet.evidence["sources"][0]["url"].endswith("#page=3")
    assert "123 Private Street" not in json.dumps(packet.evidence)
    assert "Donor Name" not in json.dumps(packet.evidence)
    assert packet.evidence["proposed_change"]["unverified_page_candidates"][0]["amount_tokens"] == ["9140.00"]
    same = {**record, "last_checked_at": (NOW + timedelta(days=1)).isoformat()}
    assert paper.prepare_packet(same, snapshot["sources"][0], snapshot).dedup_key == packet.dedup_key


def test_exact_new_snapshot_acceptance_does_not_recreate_the_same_source_proposal(monkeypatch) -> None:
    snapshot, inventory, info = fixture()
    monkeypatch.setattr(paper, "prepare_pages", lambda *_: {"prepared_pages": [], "omitted_pages": 0})
    previous = paper.acquire(snapshot, Sources(inventory, info, PDF + b"changed"), {}, NOW)[0]
    snapshot["sources"][0]["pdf_sha256"] = previous["pdf_sha256"]
    replay = paper.acquire(snapshot, Sources(inventory, info), {"217094857": previous}, NOW)[0]
    assert not replay["needs_packet"] and not replay["write_needed"]


def test_pdf_text_extraction_preserves_source_tokens_without_running_ocr() -> None:
    import pymupdf
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Monetary contributions 9140.00 on 09/02/2026\n123 Private Street")
    pdf = document.tobytes()
    document.close()
    ocr = Mock(side_effect=AssertionError("Text PDF must not use OCR"))
    extracted = paper.prepare_pages(pdf, ocr)
    assert extracted["prepared_pages"][0]["amount_tokens"] == ["9140.00"]
    assert extracted["prepared_pages"][0]["method"] == "pdf_text"
    assert "Private" not in json.dumps(extracted["prepared_pages"])
    assert "Private" in json.dumps(extracted["private_transcript"])
    ocr.assert_not_called()


def test_scan_without_ocr_is_an_explicit_source_review_not_a_zero_result() -> None:
    import pymupdf
    document = pymupdf.open()
    document.new_page()
    pdf = document.tobytes()
    document.close()
    result = paper.prepare_pages(pdf, Mock(side_effect=RuntimeError("unavailable")))
    assert result["prepared_pages"][0]["method"] == "ocr_unavailable"
    assert result["prepared_pages"][0]["amount_tokens"] == []
    assert "zero" not in result["prepared_pages"][0]["status"]


def test_local_source_reader_is_bounded_and_never_refetches_a_retained_pdf(tmp_path, monkeypatch) -> None:
    (tmp_path / "217094857.pdf").write_bytes(PDF)
    get = Mock(side_effect=AssertionError("No duplicate network request"))
    monkeypatch.setattr(paper.requests, "get", get)
    acquisition = paper.Acquisition(tmp_path)
    assert acquisition.get(f"{paper.CONNECT}/image/217094857", 1000, "217094857.pdf") == PDF
    with pytest.raises(ValueError):
        acquisition.get(f"{paper.CONNECT}/image/217094857", 2, "217094857.pdf")
    get.assert_not_called()


def test_tesseract_is_a_bounded_local_tsv_process_and_filters_low_confidence(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(paper.shutil, "which", lambda name: "/usr/bin/tesseract")
    tsv = "left\ttop\twidth\theight\tconf\ttext\n10\t20\t50\t12\t96\t1000.00\n20\t40\t50\t12\t79\t9999.00\n"
    run = Mock(return_value=SimpleNamespace(stdout=tsv.encode()))
    monkeypatch.setattr(paper.subprocess, "run", run)
    tokens = paper.tesseract_page(tmp_path / "page.png")
    assert tokens == [{"text": "1000.00", "confidence": 96, "x": 10, "y": 20, "width": 50, "height": 12}]
    assert run.call_args.args[0] == ["/usr/bin/tesseract", str(tmp_path / "page.png"), "stdout", "-l", "eng", "--psm", "11", "tsv"]
    assert run.call_args.kwargs == {"capture_output": True, "timeout": 30, "check": True}


def test_unavailable_ocr_retries_preparation_without_becoming_a_terminal_zero(monkeypatch) -> None:
    snapshot, inventory, info = fixture()
    incomplete = {"prepared_pages": [{"page": 1, "method": "ocr_unavailable"}], "omitted_pages": 0}
    monkeypatch.setattr(paper, "prepare_pages", lambda *_: incomplete)
    previous = paper.acquire(snapshot, Sources(inventory, info, PDF + b"changed"), {}, NOW)[0]
    complete = {"prepared_pages": [{"page": 1, "method": "local_tesseract", "amount_tokens": ["1000.00"]}], "omitted_pages": 0}
    preparation = Mock(return_value=complete)
    monkeypatch.setattr(paper, "prepare_pages", preparation)
    replay = paper.acquire(snapshot, Sources(inventory, info, PDF + b"changed"), {"217094857": previous}, NOW + timedelta(days=1))[0]
    assert replay["pages"] == complete and replay["needs_packet"]
    preparation.assert_called_once()


def test_workflow_has_no_model_credentials_and_uses_existing_daily_job() -> None:
    workflow = yaml.load((paper.ROOT / ".github/workflows/data-sync.yml").read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["daily-finance-ledger"]["steps"]
    refresh = next(step for step in steps if "paper_finance_review.py" in step.get("run", ""))
    assert set(refresh["env"]) == {"DATABASE_URL"}
    assert "--apply" in refresh["run"]
    assert "data_sync.py" not in refresh["run"]
    assert any("tesseract-ocr" in step.get("run", "") for step in steps)
