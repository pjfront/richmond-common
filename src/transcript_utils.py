"""
Shared transcript utilities for YouTube and Granicus transcript pipelines.

Provides source-aware transcript loading with quality-based fallback:
Granicus (professional STT) > YouTube (auto-captions).
"""
from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"

# Minimum transcript length to be considered usable (~2 min of speech)
MIN_TRANSCRIPT_CHARS = 5_000


def fetch_best_transcript(meeting_date: str) -> tuple[str, str] | None:
    """Return (transcript_text, source) using best available local transcript.

    Prefers granicus > youtube. Returns None if neither exists or both
    are below the minimum quality threshold.
    """
    granicus_path = TRANSCRIPT_DIR / f"{meeting_date}_granicus.txt"
    youtube_path = TRANSCRIPT_DIR / f"{meeting_date}_youtube.txt"
    # Legacy path (before source separation)
    clean_path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"

    for path, source in [
        (granicus_path, "granicus"),
        (youtube_path, "youtube"),
        (clean_path, "unknown"),
    ]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if len(text) >= MIN_TRANSCRIPT_CHARS:
                return (text, source)

    return None


def get_transcript_for_source(
    meeting_date: str, source: str,
) -> str | None:
    """Load transcript for a specific source. Returns text or None."""
    if source == "granicus":
        path = TRANSCRIPT_DIR / f"{meeting_date}_granicus.txt"
    elif source == "youtube":
        path = TRANSCRIPT_DIR / f"{meeting_date}_youtube.txt"
    else:
        path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"

    if path.exists():
        text = path.read_text(encoding="utf-8")
        if len(text) >= MIN_TRANSCRIPT_CHARS:
            return text
    return None


def available_sources(meeting_date: str) -> list[str]:
    """List which transcript sources are available for a meeting date."""
    sources = []
    for suffix, source in [("_granicus.txt", "granicus"), ("_youtube.txt", "youtube")]:
        path = TRANSCRIPT_DIR / f"{meeting_date}{suffix}"
        if path.exists() and path.stat().st_size >= MIN_TRANSCRIPT_CHARS:
            sources.append(source)
    return sources
