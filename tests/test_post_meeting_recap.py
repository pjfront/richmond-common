"""Focused contracts for the bounded KCRT -> Granicus recap path."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import post_meeting_recap as recap  # noqa: E402


MEETING_DATE = "2026-06-16"
HELD_MEETING_DATES = (
    "2026-07-07",
    "2026-07-21",
    "2026-07-28",
)
HELD_DATE_INPUTS = (
    *HELD_MEETING_DATES,
    *(date.fromisoformat(value) for value in HELD_MEETING_DATES),
    *(datetime.fromisoformat(f"{value}T12:00:00") for value in HELD_MEETING_DATES),
    *(f" {value} " for value in HELD_MEETING_DATES),
)
UNSUPPORTED_DATE_INPUTS = (
    "July 7, 2026",
    "07/07/2026",
)


@pytest.fixture
def transcript_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(recap, "TRANSCRIPT_DIR", tmp_path)
    return tmp_path


def _clean_transcript(transcript_dir: Path) -> Path:
    path = transcript_dir / f"{MEETING_DATE}_clean.txt"
    path.write_text("[0:00:00]\nThe council discussed an agenda item.", encoding="utf-8")
    return path


def _skip_speaker_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recap, "_get_meeting_id", lambda _date: "meeting-1")
    monkeypatch.setattr(
        recap,
        "_extract_speaker_counts",
        lambda *_args, **_kwargs: (False, None),
    )


def test_youtube_success_is_primary_and_persists_source(
    transcript_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _clean_transcript(transcript_dir)
    # Remove it so this test exercises the collector rather than local reuse.
    path.unlink()

    def fetch_youtube(_date: str, **_kwargs: object) -> Path:
        return _clean_transcript(transcript_dir)

    granicus = MagicMock()
    monkeypatch.setattr(recap, "_fetch_youtube_transcript", fetch_youtube)
    monkeypatch.setattr(recap, "_fetch_granicus_transcript", granicus)
    _skip_speaker_extraction(monkeypatch)

    result = recap.run_transcript_pipeline(MEETING_DATE)

    assert result["transcript_source"] == "youtube"
    assert result["sources_attempted"] == ["youtube"]
    granicus.assert_not_called()
    assert json.loads(
        (transcript_dir / f"{MEETING_DATE}_source.json").read_text()
    ) == {"meeting_date": MEETING_DATE, "source": "youtube"}


def test_granicus_is_used_only_after_youtube_fails(
    transcript_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    youtube = MagicMock(return_value=None)

    def fetch_granicus(_date: str) -> Path:
        path = _clean_transcript(transcript_dir)
        (transcript_dir / f"{MEETING_DATE}_granicus.pdf").write_bytes(b"pdf")
        return path

    monkeypatch.setattr(recap, "_fetch_youtube_transcript", youtube)
    monkeypatch.setattr(recap, "_fetch_granicus_transcript", fetch_granicus)
    _skip_speaker_extraction(monkeypatch)

    result = recap.run_transcript_pipeline(MEETING_DATE)

    assert result["transcript_source"] == "granicus"
    assert result["sources_attempted"] == ["youtube", "granicus"]
    youtube.assert_called_once()
    assert recap._read_transcript_source(MEETING_DATE) == "granicus"


def test_youtube_exception_still_takes_bounded_granicus_fallback(
    transcript_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch_granicus(_date: str) -> Path:
        return _clean_transcript(transcript_dir)

    monkeypatch.setattr(
        recap,
        "_fetch_youtube_transcript",
        MagicMock(side_effect=TimeoutError("YouTube timed out")),
    )
    monkeypatch.setattr(recap, "_fetch_granicus_transcript", fetch_granicus)
    _skip_speaker_extraction(monkeypatch)

    result = recap.run_transcript_pipeline(MEETING_DATE)

    assert result["transcript_source"] == "granicus"
    assert result["sources_attempted"] == ["youtube", "granicus"]


def test_unknown_existing_transcript_fails_closed_instead_of_mislabeling(
    transcript_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clean_transcript(transcript_dir)
    youtube = MagicMock()
    granicus = MagicMock()
    monkeypatch.setattr(recap, "_fetch_youtube_transcript", youtube)
    monkeypatch.setattr(recap, "_fetch_granicus_transcript", granicus)

    result = recap.run_transcript_pipeline(MEETING_DATE)

    assert result["transcript_fetched"] is False
    assert result["transcript_source"] is None
    assert "ACTION:" in capsys.readouterr().out
    youtube.assert_not_called()
    granicus.assert_not_called()


def test_source_inference_requires_exactly_one_proof_marker(
    transcript_dir: Path,
) -> None:
    _clean_transcript(transcript_dir)
    assert recap._infer_transcript_source(MEETING_DATE) is None

    vtt = transcript_dir / f"{MEETING_DATE}.en.vtt"
    vtt.write_text("WEBVTT", encoding="utf-8")
    assert recap._infer_transcript_source(MEETING_DATE) == "youtube"

    (transcript_dir / f"{MEETING_DATE}_granicus.pdf").write_bytes(b"pdf")
    assert recap._infer_transcript_source(MEETING_DATE) is None

    vtt.unlink()
    assert recap._infer_transcript_source(MEETING_DATE) == "granicus"


def test_dry_run_does_not_write_new_source_sidecar(
    transcript_dir: Path,
) -> None:
    recap._record_transcript_source(MEETING_DATE, "granicus", dry_run=True)
    assert not (transcript_dir / f"{MEETING_DATE}_source.json").exists()


def test_granicus_date_ambiguity_refuses_to_guess(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fetch = MagicMock()
    module = SimpleNamespace(
        discover_granicus_meetings=lambda: [
            {"meeting_date": MEETING_DATE, "clip_id": "1", "doc_id": "a"},
            {"meeting_date": MEETING_DATE, "clip_id": "2", "doc_id": "b"},
        ],
        fetch_transcript=fetch,
    )
    monkeypatch.setitem(sys.modules, "granicus_transcripts", module)

    assert recap._fetch_granicus_transcript(MEETING_DATE) is None
    assert "refusing to guess" in capsys.readouterr().out
    fetch.assert_not_called()


@pytest.mark.parametrize(
    ("source", "flat_source", "channel", "prompt_marker"),
    [
        ("youtube", "youtube", "kcrt", "KCRT YouTube"),
        ("granicus", "granicus", "granicus", "Granicus"),
    ],
)
def test_generated_recap_writes_actual_flat_and_structured_provenance(
    source: recap.TranscriptSource,
    flat_source: str,
    channel: str,
    prompt_marker: str,
    transcript_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _clean_transcript(transcript_dir)
    monkeypatch.setattr(recap, "_get_meeting_id", lambda _date: "meeting-1")
    monkeypatch.setattr(recap, "_load_canonical_names", lambda: "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")

    response = SimpleNamespace(
        content=[SimpleNamespace(text='{"transcript_recap":"A bounded recap."}')],
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )
    create = MagicMock(return_value=response)
    monkeypatch.setattr(
        recap,
        "LLMClient",
        lambda **_kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )

    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setitem(
        sys.modules,
        "psycopg2",
        SimpleNamespace(connect=MagicMock(return_value=connection)),
    )

    result = recap.generate_transcript_recap(
        MEETING_DATE,
        force=True,
        transcript_path=path,
        transcript_source=source,
    )

    assert result == "A bounded recap."
    sql, params = cursor.execute.call_args.args
    assert "transcript_recap_source = %s" in sql
    assert params[1] == flat_source
    assert json.loads(params[2])["channel"] == channel
    request = create.call_args.kwargs
    assert prompt_marker in request["system"]
    assert prompt_marker in request["messages"][0]["content"]
    connection.commit.assert_called_once()


def test_generate_recap_rejects_unknown_local_source_before_llm_or_db(
    transcript_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _clean_transcript(transcript_dir)
    monkeypatch.setattr(recap, "_get_meeting_id", lambda _date: "meeting-1")
    client = MagicMock()
    monkeypatch.setattr(recap, "LLMClient", client)

    result = recap.generate_transcript_recap(
        MEETING_DATE,
        force=True,
        transcript_path=path,
    )

    assert result is None
    assert "refusing to generate" in capsys.readouterr().out
    client.assert_not_called()


def _pipeline_args() -> argparse.Namespace:
    return argparse.Namespace(
        meeting_date=MEETING_DATE,
        dry_run=False,
        force=False,
        skip_transcript=False,
        skip_agenda_recap=False,
        only_transcript_recap=False,
        video_id=None,
        transcript_source=None,
    )


@pytest.mark.parametrize("meeting_date", HELD_MEETING_DATES)
def test_t14_hold_stops_full_pipeline_before_any_stage(
    meeting_date: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript = MagicMock()
    agenda = MagicMock()
    generated = MagicMock()
    state = MagicMock()
    monkeypatch.setattr(recap, "run_transcript_pipeline", transcript)
    monkeypatch.setattr(recap, "run_agenda_recap", agenda)
    monkeypatch.setattr(recap, "generate_transcript_recap", generated)
    monkeypatch.setattr(recap, "_get_recap_state", state)
    args = _pipeline_args()
    args.meeting_date = meeting_date
    args.force = True

    with pytest.raises(
        recap.RecapHeldError,
        match=r"ACTION: None through T14\..*Do not rerun, force, replay, or cascade",
    ):
        recap._run_pipeline(args)

    transcript.assert_not_called()
    agenda.assert_not_called()
    generated.assert_not_called()
    state.assert_not_called()


@pytest.mark.parametrize("meeting_date", HELD_DATE_INPUTS)
def test_t14_hold_cannot_be_bypassed_by_direct_stage_calls(
    meeting_date: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_lookup = MagicMock()
    youtube_fetch = MagicMock()
    granicus_fetch = MagicMock()
    llm_client = MagicMock()
    monkeypatch.setattr(recap, "_get_meeting_id", meeting_lookup)
    monkeypatch.setattr(recap, "_fetch_youtube_transcript", youtube_fetch)
    monkeypatch.setattr(recap, "_fetch_granicus_transcript", granicus_fetch)
    monkeypatch.setattr(recap, "LLMClient", llm_client)

    with pytest.raises(recap.RecapHeldError, match="ACTION:"):
        recap.run_transcript_pipeline(meeting_date, dry_run=True)
    with pytest.raises(recap.RecapHeldError, match="ACTION:"):
        recap.run_agenda_recap(meeting_date, dry_run=True, force=True)
    with pytest.raises(recap.RecapHeldError, match="ACTION:"):
        recap.generate_transcript_recap(meeting_date, dry_run=True, force=True)

    meeting_lookup.assert_not_called()
    youtube_fetch.assert_not_called()
    granicus_fetch.assert_not_called()
    llm_client.assert_not_called()


@pytest.mark.parametrize("meeting_date", UNSUPPORTED_DATE_INPUTS)
def test_unsupported_date_spelling_fails_before_direct_stage_calls(
    meeting_date: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_lookup = MagicMock()
    youtube_fetch = MagicMock()
    granicus_fetch = MagicMock()
    llm_client = MagicMock()
    monkeypatch.setattr(recap, "_get_meeting_id", meeting_lookup)
    monkeypatch.setattr(recap, "_fetch_youtube_transcript", youtube_fetch)
    monkeypatch.setattr(recap, "_fetch_granicus_transcript", granicus_fetch)
    monkeypatch.setattr(recap, "LLMClient", llm_client)

    with pytest.raises(recap.RecapUnavailableError, match="ACTION: Stop.*YYYY-MM-DD"):
        recap.run_transcript_pipeline(meeting_date, dry_run=True)
    with pytest.raises(recap.RecapUnavailableError, match="ACTION: Stop.*YYYY-MM-DD"):
        recap.run_agenda_recap(meeting_date, dry_run=True, force=True)
    with pytest.raises(recap.RecapUnavailableError, match="ACTION: Stop.*YYYY-MM-DD"):
        recap.generate_transcript_recap(meeting_date, dry_run=True, force=True)

    meeting_lookup.assert_not_called()
    youtube_fetch.assert_not_called()
    granicus_fetch.assert_not_called()
    llm_client.assert_not_called()


def test_t14_hold_cli_exits_with_novice_safe_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_meeting_recap.py",
            "--meeting-date",
            HELD_MEETING_DATES[0],
            "--force",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        recap.main()

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert output.startswith(
        "::error title=July recap intentionally held::ACTION: None through T14."
    )
    assert "Do not rerun, force, replay, or cascade" in output


def test_pipeline_fails_actionably_when_neither_source_leaves_a_recap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recap,
        "run_transcript_pipeline",
        lambda *_args, **_kwargs: {
            "transcript_fetched": False,
            "transcript_path": None,
            "transcript_source": None,
            "sources_attempted": ["youtube", "granicus"],
            "speakers_extracted": False,
            "speaker_stats": None,
        },
    )
    monkeypatch.setattr(recap, "run_agenda_recap", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        recap, "generate_transcript_recap", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(recap, "_get_recap_state", lambda _date: (True, False))

    with pytest.raises(recap.RecapUnavailableError, match="ACTION:.*KCRT/YouTube"):
        recap._run_pipeline(_pipeline_args())


def test_pipeline_is_idempotently_green_when_recap_already_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recap,
        "run_transcript_pipeline",
        lambda *_args, **_kwargs: {
            "transcript_fetched": False,
            "transcript_path": None,
            "transcript_source": None,
            "sources_attempted": ["youtube", "granicus"],
            "speakers_extracted": False,
            "speaker_stats": None,
        },
    )
    monkeypatch.setattr(recap, "run_agenda_recap", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        recap, "generate_transcript_recap", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(recap, "_get_recap_state", lambda _date: (True, True))

    recap._run_pipeline(_pipeline_args())


def test_transcript_prompt_is_channel_neutral() -> None:
    prompt = (ROOT / "src/prompts/transcript_recap_system.txt").read_text(
        encoding="utf-8"
    )
    assert "actual source" in prompt
    assert "from a YouTube recording" not in prompt
