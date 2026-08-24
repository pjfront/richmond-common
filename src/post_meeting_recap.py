"""
S24: Post-meeting recap orchestrator.

Combines recording transcript fetch, speaker count extraction, agenda-based
recap generation, and transcript-based recap generation into one workflow.
KCRT/YouTube is attempted first; the official City Granicus transcript is the
bounded fallback when YouTube discovery or caption fetch fails.

Reads the source-closest cleaned recording transcript from
``data/transcripts/{date}_clean.txt`` plus its source sidecar. Does NOT read
``meetings.transcript_recap`` or another derivative to generate a recap.

Pipeline:
  1. Fetch transcript from KCRT YouTube (yt-dlp), then Granicus if needed
  2. Extract per-item speaker counts (DeepSeek API)
  3. Generate agenda-based recap (meetings.meeting_recap)
  4. Generate transcript-based recap (meetings.transcript_recap)

Usage:
  python post_meeting_recap.py --meeting-date 2026-04-07
  python post_meeting_recap.py --meeting-date 2026-04-07 --dry-run
  python post_meeting_recap.py --meeting-date 2026-04-07 --skip-transcript
  python post_meeting_recap.py --meeting-date 2026-04-07 --only-transcript-recap
"""
from __future__ import annotations

from llm_client import LLMClient

import argparse
import json
import os
import re
from pathlib import Path
from typing import Literal, TypedDict

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import provenance as prov  # noqa: E402

# ── Config ────────────────────────────────────────────────────────

MODEL = "deepseek-v4-pro"
MAX_TOKENS_TRANSCRIPT_RECAP = 2000
PROMPTS_DIR = Path(__file__).parent / "prompts"
TRANSCRIPT_DIR = Path(__file__).parent.parent / "data" / "transcripts"

TranscriptSource = Literal["youtube", "granicus"]


class TranscriptPipelineResult(TypedDict):
    transcript_fetched: bool
    transcript_path: Path | None
    transcript_source: TranscriptSource | None
    sources_attempted: list[TranscriptSource]
    speakers_extracted: bool
    speaker_stats: dict[str, int] | None


class RecapUnavailableError(RuntimeError):
    """Raised when a completed pipeline run still has no transcript recap."""


def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _load_canonical_names() -> str:
    """Load canonical_names.md if present.

    The file is a hand-curated authority on civic name spellings. Auto-generated
    YouTube transcripts misspell names phonetically (e.g., "Joya" for "Gioia");
    appending this file to the system prompt lets the model correct those
    mistranscriptions before they leak into public-facing recaps.

    Returns empty string if the file doesn't exist (fail open — no crash if
    the file is removed in the future). Returns content stripped of leading
    metadata sections that don't help the model (the explanatory header).
    """
    path = PROMPTS_DIR / "canonical_names.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


# ── Step 1+2: Transcript fetch + speaker extraction ──────────────


def _transcript_source_path(meeting_date: str) -> Path:
    """Return the sidecar that binds a clean transcript to its real source."""
    return TRANSCRIPT_DIR / f"{meeting_date}_source.json"


def _record_transcript_source(
    meeting_date: str,
    source: TranscriptSource,
    *,
    dry_run: bool = False,
) -> None:
    """Persist source identity next to the source-closest transcript artifact."""
    if dry_run:
        return
    path = _transcript_source_path(meeting_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"meeting_date": meeting_date, "source": source}, indent=2),
        encoding="utf-8",
    )


def _read_transcript_source(meeting_date: str) -> TranscriptSource | None:
    """Read a validated source sidecar; malformed/unknown values fail closed."""
    path = _transcript_source_path(meeting_date)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    source = data.get("source")
    if data.get("meeting_date") != meeting_date or source not in {
        "youtube",
        "granicus",
    }:
        return None
    return source


def _infer_transcript_source(meeting_date: str) -> TranscriptSource | None:
    """Infer legacy local artifacts only when exactly one source is provable."""
    recorded = _read_transcript_source(meeting_date)
    if recorded:
        return recorded

    has_granicus_pdf = (
        TRANSCRIPT_DIR / f"{meeting_date}_granicus.pdf"
    ).exists()
    has_youtube_vtt = any(TRANSCRIPT_DIR.glob(f"{meeting_date}*.vtt"))
    if has_granicus_pdf == has_youtube_vtt:
        # Neither marker or both markers: source is not safely knowable.
        return None
    return "granicus" if has_granicus_pdf else "youtube"


def _fetch_youtube_transcript(
    meeting_date: str,
    *,
    video_id_override: str | None = None,
) -> Path | None:
    """Attempt the primary KCRT/YouTube transcript path."""
    from youtube_comments import (
        discover_videos,
        fetch_transcript,
        match_videos_to_meetings,
    )

    if video_id_override:
        print(f"  Using YouTube video override: {video_id_override}")
        return fetch_transcript(video_id_override, meeting_date)

    print("  Discovering KCRT videos...")
    matched = [
        meeting
        for meeting in match_videos_to_meetings(discover_videos())
        if meeting["meeting_date"] == meeting_date
    ]
    if not matched:
        print(f"  No KCRT video found for {meeting_date}")
        return None

    meeting = matched[0]
    print(f"  Fetching YouTube transcript for {meeting['video_id']}...")
    return fetch_transcript(
        meeting["video_id"],
        meeting_date,
        alt_video_ids=meeting.get("alt_video_ids", []),
    )


def _fetch_granicus_transcript(meeting_date: str) -> Path | None:
    """Attempt the official Granicus transcript path for one unambiguous date."""
    from granicus_transcripts import (
        discover_granicus_meetings,
        fetch_transcript,
    )

    print("  Checking the official Granicus meeting archive...")
    matched = [
        meeting
        for meeting in discover_granicus_meetings()
        if meeting["meeting_date"] == meeting_date
    ]
    if not matched:
        print(f"  No Granicus transcript found for {meeting_date}")
        return None
    if len(matched) > 1:
        print(
            f"  ERROR: Found {len(matched)} Granicus transcripts for "
            f"{meeting_date}; refusing to guess which recording is the "
            "regular council meeting"
        )
        return None

    meeting = matched[0]
    return fetch_transcript(
        meeting["clip_id"],
        meeting["doc_id"],
        meeting_date,
    )


def _extract_speaker_counts(
    transcript_path: Path,
    meeting_id: str,
    meeting_date: str,
    source: TranscriptSource,
    *,
    dry_run: bool,
) -> tuple[bool, dict[str, int] | None]:
    """Extract counts with the implementation paired to the real source."""
    if source == "granicus":
        from granicus_transcripts import extract_speakers, import_speaker_counts
    else:
        from youtube_comments import extract_speakers, import_speaker_counts

    print("\n  Extracting speaker counts...")
    speakers = extract_speakers(transcript_path, meeting_id, meeting_date)
    if not speakers:
        return False, None

    stats = import_speaker_counts(
        speakers,
        meeting_id,
        meeting_date,
        dry_run=dry_run,
    )
    result_path = TRANSCRIPT_DIR / f"{meeting_date}_result.json"
    result_path.write_text(json.dumps(speakers, indent=2), encoding="utf-8")
    return True, stats


def run_transcript_pipeline(
    meeting_date: str,
    *,
    dry_run: bool = False,
    video_id_override: str | None = None,
    transcript_source_override: TranscriptSource | None = None,
) -> TranscriptPipelineResult:
    """Fetch a transcript and extract speaker counts.

    KCRT/YouTube is primary. Granicus is attempted only when YouTube does not
    produce the clean transcript. A source override applies only to an
    already-present local artifact; freshly fetched artifacts always use the
    collector that actually returned them.

    Source identity is returned and persisted beside the clean transcript so
    ``--only-transcript-recap`` cannot silently relabel a Granicus artifact as
    YouTube (or vice versa).
    """
    result: TranscriptPipelineResult = {
        "transcript_fetched": False,
        "transcript_path": None,
        "transcript_source": None,
        "sources_attempted": [],
        "speakers_extracted": False,
        "speaker_stats": None,
    }

    clean_path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"
    source: TranscriptSource | None = None
    if clean_path.exists():
        print(f"  Transcript already exists: {clean_path.name}")
        source = transcript_source_override or _infer_transcript_source(meeting_date)
        if source is None:
            print(
                "  ERROR: Existing transcript source is unknown. ACTION: rerun "
                "with --transcript-source youtube|granicus only after verifying "
                "which recording produced the local file."
            )
            return result
        _record_transcript_source(meeting_date, source, dry_run=dry_run)
    else:
        result["sources_attempted"].append("youtube")
        try:
            path = _fetch_youtube_transcript(
                meeting_date,
                video_id_override=video_id_override,
            )
        except Exception as exc:
            # A blocked/changed YouTube endpoint is exactly when Granicus must
            # remain available. Preserve the reason in the run log, then take
            # the one bounded fallback rather than aborting early.
            print(
                "  KCRT/YouTube collector failed: "
                f"{type(exc).__name__}: {exc}"
            )
            path = None
        if path is not None:
            clean_path = path
            source = "youtube"
        else:
            print("  KCRT/YouTube did not yield a transcript; trying Granicus")
            result["sources_attempted"].append("granicus")
            try:
                path = _fetch_granicus_transcript(meeting_date)
            except Exception as exc:
                print(
                    "  Granicus collector failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                path = None
            if path is None:
                print(
                    f"  Neither KCRT/YouTube nor Granicus yielded a transcript "
                    f"for {meeting_date}"
                )
                return result
            clean_path = path
            source = "granicus"

        _record_transcript_source(meeting_date, source, dry_run=dry_run)

    if source is None:
        # Defensive type/runtime guard: every successful path above records a
        # concrete collector. Keep future refactors fail-closed too.
        return result

    result["transcript_fetched"] = True
    result["transcript_path"] = clean_path
    result["transcript_source"] = source

    # Extract speaker counts
    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        print(f"  No meeting found in DB for {meeting_date}")
        return result

    extracted, stats = _extract_speaker_counts(
        clean_path,
        meeting_id,
        meeting_date,
        source,
        dry_run=dry_run,
    )
    result["speakers_extracted"] = extracted
    result["speaker_stats"] = stats

    return result


# ── Step 3: Agenda-based recap ───────────────────────────────────


def run_agenda_recap(
    meeting_date: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """Generate agenda-based recap (meetings.meeting_recap).

    Returns True if recap was generated.
    """
    from generate_meeting_recaps import generate_recaps
    from db import get_connection

    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        print(f"  No meeting found in DB for {meeting_date}")
        return False

    # Check if already generated
    if not force:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT meeting_recap IS NOT NULL FROM meetings WHERE id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                print(f"  Agenda recap already exists (use --force to regenerate)")
                conn.close()
                return True
        conn.close()

    if dry_run:
        print(f"  [DRY RUN] Would generate agenda recap for {meeting_date}")
        return False

    print(f"  Generating agenda-based recap...")
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        stats = generate_recaps(conn, meeting_id=meeting_id, force=force)
        return stats["generated"] > 0
    finally:
        conn.close()


# ── Step 4: Transcript-based recap ───────────────────────────────


def generate_transcript_recap(
    meeting_date: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    transcript_path: Path | None = None,
    transcript_source: TranscriptSource | None = None,
) -> str | None:
    """Generate a recap from a source-identified recording transcript.

    Sends the source-closest transcript to DeepSeek with a transcript-specific
    system prompt. Saves both the legacy flat source and structured provenance
    from the actual collector. Unknown source identity fails closed.

    Returns the recap text, or None on failure.
    """
    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        print(f"  No meeting found in DB for {meeting_date}")
        return None

    # Check if already generated
    if not force:
        from db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT transcript_recap IS NOT NULL FROM meetings WHERE id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                print(f"  Transcript recap already exists (use --force to regenerate)")
                conn.close()
                return None
        conn.close()

    # Load the source-closest transcript. Never silently guess source identity:
    # the value is either threaded from this run's collector or proven by the
    # persisted sidecar / one unambiguous legacy fetch artifact.
    clean_path = transcript_path or TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"
    if not clean_path.exists():
        print(f"  No transcript file for {meeting_date}")
        return None
    source = transcript_source or _infer_transcript_source(meeting_date)
    if source is None:
        print(
            "  ERROR: Transcript source is unknown; refusing to generate a "
            "recap with a false recording label. ACTION: verify the local "
            "artifact, then pass --transcript-source youtube|granicus."
        )
        return None
    _record_transcript_source(meeting_date, source, dry_run=dry_run)

    transcript = clean_path.read_text(encoding="utf-8")
    est_tokens = len(transcript) // 4
    print(f"  Transcript: {len(transcript):,} chars (~{est_tokens:,} tokens)")

    if dry_run:
        print(f"  [DRY RUN] Would send {est_tokens:,} tokens to DeepSeek")
        return None

    # Generate recap via DeepSeek. The checked-in prompt is channel-neutral;
    # this run-specific context tells the model exactly which recording it saw.
    system_prompt = _load_prompt("transcript_recap_system.txt")
    # Append canonical names so the model corrects phonetic mistranscriptions
    # of council members, county officials, etc. (S24.22, 2026-04-25).
    canonical = _load_canonical_names()
    if canonical:
        system_prompt += "\n\n---\n\nCANONICAL NAMES\n\n" + canonical

    source_description = (
        "the official City of Richmond Granicus meeting recording"
        if source == "granicus"
        else "the KCRT YouTube meeting recording"
    )
    system_prompt += (
        "\n\nSOURCE CONTEXT\n\n"
        f"This transcript came from {source_description}."
    )

    print(f"  Sending {source} transcript to DeepSeek...")
    client = LLMClient(timeout=120.0)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_TRANSCRIPT_RECAP,
        temperature=0,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Write a post-meeting recap from this transcript of the "
                       f"Richmond City Council meeting on {meeting_date}. "
                       f"Source: {source_description}.\n\n"
                       f"{transcript}",
        }],
    )

    print(
        f"  API: {response.usage.input_tokens:,} in / "
        f"{response.usage.output_tokens:,} out "
        "(cost recorded by the centralized LLM budget journal)"
    )

    # Parse JSON response
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
        recap = (data.get("transcript_recap") or "").strip()
    except json.JSONDecodeError:
        # Try regex extraction
        match = re.search(r'"transcript_recap"\s*:\s*"(.*)"', text, re.DOTALL)
        if match:
            recap = match.group(1).replace("\\n", "\n").strip()
        else:
            print(f"  WARNING: Could not parse JSON, using raw text")
            recap = text

    if not recap:
        print(f"  No recap content generated")
        return None

    # Save the actual source in both the legacy flat column and the structured
    # provenance used by the public source attribution component.
    print(f"  Saving transcript recap ({len(recap)} chars)...")
    p = prov.meeting_recording(
        channel="granicus" if source == "granicus" else "kcrt",
        generator="post_meeting_recap.py",
    )
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE meetings
                   SET transcript_recap = %s,
                       transcript_recap_source = %s,
                       transcript_recap_provenance = %s,
                       transcript_recap_generated_at = NOW()
                   WHERE id = %s""",
                (recap, source, prov.to_json(p), meeting_id),
            )
        conn.commit()
    finally:
        conn.close()

    return recap


# ── Helpers ──────────────────────────────────────────────────────


def _get_meeting_id(meeting_date: str) -> str | None:
    """Look up meeting UUID by date."""
    from db import get_connection, RICHMOND_FIPS

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM meetings WHERE city_fips = %s AND meeting_date = %s "
            "AND meeting_type = 'regular' LIMIT 1",
            (RICHMOND_FIPS, meeting_date),
        )
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def _get_recap_state(meeting_date: str) -> tuple[bool, bool] | None:
    """Return (agenda recap, transcript recap) state for a regular meeting."""
    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        return None

    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT meeting_recap IS NOT NULL, transcript_recap IS NOT NULL "
                "FROM meetings WHERE id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return bool(row[0]), bool(row[1])


# ── CLI ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-meeting recap pipeline: transcript + agenda + transcript recap"
    )
    parser.add_argument(
        "--meeting-date", required=True,
        help="Meeting date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without DB writes or API calls",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate existing recaps",
    )
    parser.add_argument(
        "--skip-transcript", action="store_true",
        help="Skip recording transcript fetch + speaker extraction",
    )
    parser.add_argument(
        "--skip-agenda-recap", action="store_true",
        help="Skip agenda-based recap generation",
    )
    parser.add_argument(
        "--only-transcript-recap", action="store_true",
        help="Only generate transcript-based recap (skip steps 1-3)",
    )
    parser.add_argument(
        "--video-id",
        help="Override channel discovery with a specific YouTube video ID. "
             "Use when the live-stream title doesn't include a parseable date "
             "(KCRT live-streams often appear before being renamed).",
    )
    parser.add_argument(
        "--transcript-source",
        choices=("youtube", "granicus"),
        help="Verified source of an already-present local clean transcript. "
             "Only needed when its source sidecar/fetch artifact is missing.",
    )

    args = parser.parse_args()

    try:
        _run_pipeline(args)
    except RecapUnavailableError as exc:
        print(f"::error title=Transcript recap unavailable::{exc}")
        raise SystemExit(1) from exc


def _run_pipeline(args: argparse.Namespace) -> None:
    """Run the 4-step recap pipeline. Errors propagate to caller."""
    date = args.meeting_date

    print(f"Post-meeting recap pipeline for {date}")
    print("=" * 50)

    skip_transcript = args.skip_transcript or args.only_transcript_recap
    skip_agenda = args.skip_agenda_recap or args.only_transcript_recap
    transcript_path: Path | None = None
    transcript_source: TranscriptSource | None = getattr(
        args, "transcript_source", None
    )

    # Step 1+2: Transcript fetch + speaker extraction
    if not skip_transcript:
        print(f"\n[1/4] Recording transcript + speaker counts")
        result = run_transcript_pipeline(
            date,
            dry_run=args.dry_run,
            video_id_override=getattr(args, "video_id", None),
            transcript_source_override=transcript_source,
        )
        if result["transcript_fetched"]:
            transcript_path = result["transcript_path"]
            transcript_source = result["transcript_source"]
            print(f"  Transcript: OK ({transcript_source})")
        else:
            print(f"  Transcript: FAILED after all available sources")
        if result["speakers_extracted"]:
            stats = result["speaker_stats"] or {}
            print(f"  Speakers: {stats.get('updated', 0)} items updated, "
                  f"{stats.get('open_forum', 0)} open forum")
    else:
        print(f"\n[1/4] Transcript fetch — skipped")

    # Step 3: Agenda-based recap
    if not skip_agenda:
        print(f"\n[2/4] Agenda-based recap")
        ok = run_agenda_recap(date, dry_run=args.dry_run, force=args.force)
        print(f"  {'OK' if ok else 'No recap generated'}")
    else:
        print(f"\n[2/4] Agenda recap — skipped")

    # Step 4: Transcript-based recap
    print(f"\n[3/4] Transcript-based recap")
    recap = generate_transcript_recap(
        date,
        dry_run=args.dry_run,
        force=args.force,
        transcript_path=transcript_path,
        transcript_source=transcript_source,
    )
    if recap:
        print(f"  OK ({len(recap)} chars)")
        # Print first ~500 chars as preview
        print(f"\n  Preview:")
        for line in recap[:500].split("\n"):
            print(f"    {line}")
        if len(recap) > 500:
            print(f"    ...")
    else:
        print(f"  No transcript recap generated")

    print(f"\n[4/4] Done.")
    print("=" * 50)

    # Summary and fail-closed scheduled-run contract. Existing recaps make the
    # command idempotently successful; a green run may never mean "did nothing
    # and still has no transcript recap."
    state = _get_recap_state(date)
    if state is None:
        raise RecapUnavailableError(
            f"ACTION: Give this run to a coding assistant. No regular Richmond "
            f"City Council meeting record could be verified for {date}; inspect "
            "the meeting gate before retrying."
        )

    has_agenda, has_transcript = state
    print(f"  Agenda recap:     {'yes' if has_agenda else 'no'}")
    print(f"  Transcript recap: {'yes' if has_transcript else 'no'}")
    if not has_transcript and not args.dry_run:
        raise RecapUnavailableError(
            f"ACTION: Give this run to a coding assistant. No transcript recap "
            f"exists for {date} after the KCRT/YouTube and Granicus paths. "
            "Inspect source availability and the source-closest transcript "
            "artifact before retrying; do not repeatedly rerun the workflow."
        )


if __name__ == "__main__":
    main()
