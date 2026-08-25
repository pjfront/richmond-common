"""Bounded offline-OCR guards for image-only Form 497 Part 1 filings."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml


OCR_TEXT = """497 Contribution Report
Date of This Filing
8/17/2026
Ahmad Anderson for Richmond Mayor 2026
1. Contribution(s) Received
Michael Bush
IND
Executive - Great Places to Work
2,500
5/16/2026
Oakland, CA 94618
"""


def _pdf(tmp_path: Path, pages: int = 1) -> Path:
    import fitz

    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()
    return path


def _rapidocr_module(lines: list[str], scores: list[float], observed: list[Path]):
    def run(image_path: str):
        path = Path(image_path)
        assert path.exists()
        observed.append(path)
        return SimpleNamespace(txts=tuple(lines), scores=tuple(scores))

    engine = MagicMock(side_effect=run)
    factory = MagicMock(return_value=engine)
    return SimpleNamespace(RapidOCR=factory), factory, engine


def test_local_ocr_is_bounded_filtered_and_temporary(tmp_path, monkeypatch):
    from netfile_paper_extractor import extract_form497_text_with_local_ocr

    lines = OCR_TEXT.splitlines() + ["untrusted low-confidence noise"]
    scores = [0.99] * (len(lines) - 1) + [0.79]
    observed: list[Path] = []
    module, factory, engine = _rapidocr_module(lines, scores, observed)
    monkeypatch.setitem(sys.modules, "rapidocr", module)

    text = extract_form497_text_with_local_ocr(_pdf(tmp_path))

    assert "Michael Bush" in text
    assert "untrusted low-confidence noise" not in text
    factory.assert_called_once_with()
    assert engine.call_count == 1
    assert observed and all(not path.exists() for path in observed)


def test_local_ocr_accepts_numpy_real_confidence_values(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    from netfile_paper_extractor import extract_form497_text_with_local_ocr

    lines = OCR_TEXT.splitlines()
    observed: list[Path] = []
    scores = list(np.asarray([0.99] * len(lines), dtype=np.float32))
    module, _, engine = _rapidocr_module(lines, scores, observed)
    monkeypatch.setitem(sys.modules, "rapidocr", module)

    text = extract_form497_text_with_local_ocr(_pdf(tmp_path))

    assert "Michael Bush" in text
    assert engine.call_count == 1


def test_local_ocr_rejects_oversized_form_before_model_init(tmp_path, monkeypatch):
    from netfile_paper_extractor import (
        LocalOCRUnavailableError,
        MAX_FORM497_LOCAL_OCR_PAGES,
        extract_form497_text_with_local_ocr,
    )

    module = SimpleNamespace(RapidOCR=MagicMock())
    monkeypatch.setitem(sys.modules, "rapidocr", module)

    with pytest.raises(LocalOCRUnavailableError, match="bounded to"):
        extract_form497_text_with_local_ocr(
            _pdf(tmp_path, pages=MAX_FORM497_LOCAL_OCR_PAGES + 1)
        )

    module.RapidOCR.assert_not_called()


def test_local_ocr_rejects_accepted_text_over_character_cap(tmp_path, monkeypatch):
    import netfile_paper_extractor as extractor

    lines = OCR_TEXT.splitlines()
    observed: list[Path] = []
    module, _, _ = _rapidocr_module(lines, [0.99] * len(lines), observed)
    monkeypatch.setitem(sys.modules, "rapidocr", module)
    monkeypatch.setattr(extractor, "MAX_FORM497_LOCAL_OCR_CHARS", 10)

    with pytest.raises(extractor.LocalOCRUnavailableError, match="accepted characters"):
        extractor.extract_form497_text_with_local_ocr(_pdf(tmp_path))

    assert observed and all(not path.exists() for path in observed)


@pytest.mark.parametrize(
    "text, missing",
    [
        (OCR_TEXT.replace("497 Contribution Report", "497 Report"), "Form 497 title"),
        (OCR_TEXT.replace("Contribution(s) Received", "Contribution(s) Made"), "Part 1"),
        (OCR_TEXT.replace("5/16/2026", "not-a-date"), "filing and contribution dates"),
        (OCR_TEXT.replace("2,500", "amount unavailable"), "contribution amount"),
    ],
)
def test_local_ocr_requires_positive_part1_transaction_evidence(text, missing):
    from netfile_paper_extractor import (
        LocalOCRUnavailableError,
        _validate_form497_local_ocr_text,
    )

    with pytest.raises(LocalOCRUnavailableError, match=missing):
        _validate_form497_local_ocr_text(text)


def test_deepseek_rows_must_be_grounded_in_local_ocr():
    from netfile_paper_extractor import validate_form497_local_ocr_rows

    validate_form497_local_ocr_rows(
        [{"contributor_name": "Michael Bush", "amount": 2500.0, "date": "2026-05-16"}],
        OCR_TEXT,
    )


@pytest.mark.parametrize(
    "row, message",
    [
        ({"contributor_name": "Invented Donor", "amount": 2500.0, "date": "2026-05-16"}, "name"),
        ({"contributor_name": "Michael Bush", "amount": 5000.0, "date": "2026-05-16"}, "amount"),
        ({"contributor_name": "Michael Bush", "amount": 2500.0, "date": "2026-05-17"}, "date"),
    ],
)
def test_deepseek_rows_fail_closed_when_not_grounded(row, message):
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        validate_form497_local_ocr_rows,
    )

    with pytest.raises(TextExtractionIncompleteError, match=message):
        validate_form497_local_ocr_rows([row], OCR_TEXT)


def test_name_grounding_cannot_cross_ocr_line_boundaries():
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        validate_form497_local_ocr_rows,
    )

    text = OCR_TEXT + "\nInvented\nDonor\n"
    row = {
        "contributor_name": "Invented Donor",
        "amount": 2500.0,
        "date": "2026-05-16",
    }
    with pytest.raises(TextExtractionIncompleteError, match="name"):
        validate_form497_local_ocr_rows([row], text)


def test_local_ocr_zero_rows_remain_pending():
    from netfile_paper_extractor import (
        TextExtractionIncompleteError,
        validate_form497_local_ocr_rows,
    )

    with pytest.raises(TextExtractionIncompleteError, match="returned zero rows"):
        validate_form497_local_ocr_rows([], OCR_TEXT)


def test_image_only_form497_uses_local_ocr_then_deepseek(tmp_path):
    from netfile_paper_extractor import extract_committee

    row = {
        "contributor_name": "Michael Bush",
        "amount": 2500.0,
        "date": "2026-05-16",
        "filing_id": "filing-497",
        "entity_code": "IND",
        "city": "Oakland",
        "state": "CA",
        "zip": "94618",
        "occupation": "Executive",
        "contributor_employer": "Great Places to Work",
    }
    filing = {"filing_id": "filing-497", "form_type": "Form 497"}
    client = MagicMock()

    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing", return_value=_pdf(tmp_path)
    ), patch("netfile_paper_extractor.extract_text_from_pdf", return_value=""), patch(
        "netfile_paper_extractor.extract_form497_text_with_local_ocr",
        return_value=OCR_TEXT,
    ) as local_ocr, patch(
        "netfile_paper_extractor.parse_filing_with_claude", return_value=[row]
    ) as deepseek, patch(
        "netfile_paper_extractor.parse_filing_with_vision"
    ) as vision:
        result = extract_committee(
            "Anderson for Mayor 2026",
            [filing],
            client,
            dry_run=True,
        )

    assert result["contributions"] == [row]
    local_ocr.assert_called_once()
    deepseek.assert_called_once_with(
        OCR_TEXT,
        "497",
        "filing-497",
        "Anderson for Mayor 2026",
        client,
    )
    vision.assert_not_called()


def test_failed_local_ocr_grounding_falls_back_to_existing_kimi_path(tmp_path):
    from netfile_paper_extractor import extract_committee

    filing = {"filing_id": "filing-497", "form_type": "Form 497"}
    vision_row = {
        "contributor_name": "Michael Bush",
        "amount": 2500.0,
        "date": "2026-05-16",
    }
    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing", return_value=_pdf(tmp_path)
    ), patch("netfile_paper_extractor.extract_text_from_pdf", return_value=""), patch(
        "netfile_paper_extractor.extract_form497_text_with_local_ocr",
        return_value=OCR_TEXT,
    ), patch(
        "netfile_paper_extractor.parse_filing_with_claude", return_value=[]
    ), patch(
        "netfile_paper_extractor.parse_filing_with_vision", return_value=[vision_row]
    ) as vision:
        result = extract_committee(
            "Anderson for Mayor 2026",
            [filing],
            MagicMock(),
            dry_run=True,
        )

    assert result["contributions"] == [vision_row]
    vision.assert_called_once()


def test_kimi_zero_after_positive_local_ocr_remains_pending(tmp_path):
    from netfile_paper_extractor import extract_committee

    filing = {"filing_id": "filing-497", "form_type": "Form 497"}
    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing", return_value=_pdf(tmp_path)
    ), patch("netfile_paper_extractor.extract_text_from_pdf", return_value=""), patch(
        "netfile_paper_extractor.extract_form497_text_with_local_ocr",
        return_value=OCR_TEXT,
    ), patch(
        "netfile_paper_extractor.parse_filing_with_claude", return_value=[]
    ), patch(
        "netfile_paper_extractor.parse_filing_with_vision", return_value=[]
    ):
        result = extract_committee(
            "Anderson for Mayor 2026",
            [filing],
            MagicMock(),
            dry_run=True,
        )

    assert result["filings"] == []
    assert result["contributions"] == []


def test_kimi_ungrounded_row_after_positive_local_ocr_remains_pending(tmp_path):
    from netfile_paper_extractor import extract_committee

    filing = {"filing_id": "filing-497", "form_type": "Form 497"}
    ungrounded = {
        "contributor_name": "Invented Donor",
        "amount": 2500.0,
        "date": "2026-05-16",
    }
    with patch("netfile_paper_extractor.find_committee_json", return_value=None), patch(
        "netfile_paper_extractor.download_paper_filing", return_value=_pdf(tmp_path)
    ), patch("netfile_paper_extractor.extract_text_from_pdf", return_value=""), patch(
        "netfile_paper_extractor.extract_form497_text_with_local_ocr",
        return_value=OCR_TEXT,
    ), patch(
        "netfile_paper_extractor.parse_filing_with_claude", return_value=[]
    ), patch(
        "netfile_paper_extractor.parse_filing_with_vision", return_value=[ungrounded]
    ):
        result = extract_committee(
            "Anderson for Mayor 2026",
            [filing],
            MagicMock(),
            dry_run=True,
        )

    assert result["filings"] == []
    assert result["contributions"] == []


def test_only_netfile_jobs_install_the_pinned_offline_ocr_dependencies():
    repo = Path(__file__).resolve().parent.parent
    workflow = (repo / ".github" / "workflows" / "data-sync.yml").read_text(
        encoding="utf-8"
    )
    ocr_requirements = (repo / "requirements-ocr.txt").read_text(encoding="utf-8")
    shared_requirements = (repo / "requirements.txt").read_text(encoding="utf-8")

    assert "rapidocr==3.9.2" in ocr_requirements
    assert "onnxruntime==1.29.0" in ocr_requirements
    assert "rapidocr" not in shared_requirements.casefold()
    assert "onnxruntime" not in shared_requirements.casefold()
    assert workflow.count("pip install -r requirements-ocr.txt") == 3
    assert "if: steps.inputs.outputs.source == 'netfile'" in workflow

    parsed = yaml.safe_load(workflow)
    installers = {
        job_name: [
            step
            for step in job["steps"]
            if step.get("run") == "pip install -r requirements-ocr.txt"
        ]
        for job_name, job in parsed["jobs"].items()
        if any(
            step.get("run") == "pip install -r requirements-ocr.txt"
            for step in job.get("steps", [])
        )
    }
    assert set(installers) == {"sync", "daily-netfile", "weekly-pipeline"}
    assert installers["sync"] == [{
        "name": "Install bounded offline OCR for NetFile",
        "if": "steps.inputs.outputs.source == 'netfile'",
        "run": "pip install -r requirements-ocr.txt",
    }]
    for job_name in installers:
        setup = next(
            step
            for step in parsed["jobs"][job_name]["steps"]
            if step.get("uses") == "actions/setup-python@v6"
        )
        assert setup["with"]["cache-dependency-path"] == (
            "requirements.txt\nrequirements-ocr.txt\n"
        )


def test_docs_distinguish_local_image_privacy_from_optional_kimi_fallback():
    repo = Path(__file__).resolve().parent.parent
    decision = (repo / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    audit = (
        repo / "docs" / "audits" / "2026-08-24-form497-local-ocr-containment.md"
    ).read_text(encoding="utf-8")

    for text in (decision, audit):
        normalized = " ".join(text.split())
        assert "Images do not leave the runner during that stage" in text or (
            "local-OCR stage keeps source images on the runner" in text
        )
        assert "MOONSHOT_API_KEY" in text
        assert "send the filing's page images to Kimi" in normalized
