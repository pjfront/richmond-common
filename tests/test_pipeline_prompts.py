"""Resolve every `Path(__file__).parent[.parent...] / "prompts" / "X.txt"`
reference in `src/**.py` and verify the target file exists.

Catches the 2026-05-19 P0 class: a Phase 2.3 refactor moved
`sync_proceeding_classification` from `src/data_sync.py` to
`src/pipelines/enrichments.py` without updating the `.parent` chain on
the prompt path. `__file__` now resolved one directory deeper, so
`Path(__file__).parent / "prompts"` pointed at `src/pipelines/prompts/`
(doesn't exist) instead of `src/prompts/` (real). The sync silently
failed for two weeks before the SessionStart health check surfaced it.

The bug shape is: refactoring code that uses `Path(__file__).parent`
into a subdirectory while keeping the original `.parent` count. This
test catches the whole class — for every prompt-path expression of
the form above, it simulates the resolution from the caller file's
location and asserts the target file exists. Typos in prompt filenames
fail the same way, by intent.

What this DOESN'T catch:
  - Prompt loading via a runtime variable: `Path(some_var) / "X.txt"`
  - Dynamic prompt filenames (very rare in this codebase)
  - Prompts loaded outside `src/` (none currently)

If a new caller pattern emerges that this regex doesn't match,
generalize the regex rather than disabling the test.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"

# Matches: Path(__file__).parent[.parent ...] / "prompts" / "<filename>.txt"
# Captures the `.parent` chain (so we know how many directories up) and
# the prompt filename. Whitespace around `/` is tolerated because Python
# linters sometimes reformat the expression across lines.
PROMPT_PATH_RE = re.compile(
    r'Path\(__file__\)((?:\.parent)+)\s*/\s*"prompts"\s*/\s*"([^"]+\.txt)"'
)


def test_every_prompt_path_in_src_resolves_to_real_file() -> None:
    """Every `Path(__file__).parent.../prompts/X.txt` must point at an existing file.

    Catches refactor-class bugs where a sync function gets moved into
    a subdirectory but its prompt path keeps the original `.parent`
    count. Also catches typos in prompt filenames and missing prompt
    files generally.
    """
    broken: list[dict[str, object]] = []
    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8")
        if "prompts" not in text:
            # Fast path: no prompt loading possible in this file.
            continue
        for parent_chain, prompt_name in PROMPT_PATH_RE.findall(text):
            # Each ".parent" walks one directory up from the caller file.
            parents = parent_chain.count(".parent")
            resolved_dir = py_file
            for _ in range(parents):
                resolved_dir = resolved_dir.parent
            target = resolved_dir / "prompts" / prompt_name
            if not target.exists():
                broken.append(
                    {
                        "caller": str(py_file.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "prompt": prompt_name,
                        "parent_chain": parent_chain,
                        "resolved_to": str(target).replace("\\", "/"),
                    }
                )
    assert not broken, (
        f"Pipeline prompt paths that don't resolve to a real file:\n"
        + "\n".join(f"  - {b}" for b in broken)
        + "\n\nFix the `.parent` chain in the caller, or add the missing "
        "prompt file under src/prompts/. The chain count must equal the "
        "depth of the caller file relative to src/."
    )


def test_regex_catches_known_callers() -> None:
    """Sanity: the regex actually matches the known caller patterns.

    If someone changes the regex and it starts matching zero lines,
    this test fails loudly so the broader test doesn't silently pass
    by matching nothing.
    """
    callers_with_match = 0
    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8")
        if PROMPT_PATH_RE.search(text):
            callers_with_match += 1
    # Known callers as of 2026-05-20: at least 6 files in src/ use this
    # pattern (community_voice_extractor, granicus_transcripts,
    # youtube_comments, theme_extractor, pipelines/enrichments, plus
    # vote_explainer and plain_language_summarizer which load multiple).
    # Pick a conservative lower bound that catches "regex matches
    # nothing" without locking in the exact count.
    assert callers_with_match >= 3, (
        f"Regex matched {callers_with_match} callers — expected >= 3. "
        f"If the prompt-loading pattern changed, generalize PROMPT_PATH_RE; "
        f"don't lower this floor."
    )
