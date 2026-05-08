#!/usr/bin/env python3
"""Stop-hook over-prompt detector.

Reads a Stop-event JSON envelope on stdin, extracts the most recent
assistant text turn from the session transcript, and blocks the stop
if that text matches "asking the user to decide something AI-delegable"
patterns (per .claude/rules/judgment-boundaries.md).

Output protocol (Claude Code Stop hook):
  - Print {"decision": "block", "reason": "..."} on stdout to force the
    model to continue rather than stop. This is the enforcement mechanism
    that survives model inattention.
  - Exit 0 silently to allow the stop.

Escape hatch: append `<!-- ai-override: <reason> -->` anywhere in the
assistant message and the hook will allow it. Forces an articulated
justification when the question genuinely needs human judgment.

Test mode:
  python check-overprompt.py --test "Want me to merge this PR?"
  → prints the would-be block JSON
  python check-overprompt.py --test "Done. Merged as 1234abc."
  → exit 0, no output
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


# ── Patterns ────────────────────────────────────────────────────────
#
# Two categories:
#
#   ALWAYS_PATTERNS  — fire regardless of nearby punctuation. These
#     are explicit-punt phrases that don't need a `?` to be over-
#     prompts ("Your call: …", "Let me know if you'd like …").
#
#   QUESTION_PATTERNS — fire only when a `?` appears within ~400 chars
#     of the match. Catches real questions while letting through
#     rhetorical or hypothetical mentions ("I should i" doesn't exist
#     but "should i?" does).
#
# Names are stable identifiers logged in the block message.
ALWAYS_PATTERNS = [
    (r"\byour\s+call\b", "your_call"),
    (r"\blet\s+me\s+know\s+if\b", "let_me_know"),
    (r"\bwould\s+you\s+like\s+me\s+to\b", "would_you_like"),
    (r"\bwant\s+me\s+to\s+do\s+anything\s+else\b", "anything_else"),
]
QUESTION_PATTERNS = [
    (r"\bwant\s+me\s+to\b", "want_me_to"),
    (r"\bshould\s+i\b", "should_i"),
    (r"\(a\)\s.{1,400}?\(b\)\s", "ab_options"),
    (r"\(1\)\s.{1,400}?\(2\)\s", "12_options"),
    (r"\b\(recommended\)", "recommended"),
]

# Where in the message we look — the last 2000 chars are the "tail"
# where over-prompts cluster. Trying to match the whole message
# produces false positives from earlier exposition.
TAIL_CHARS = 2000

# Override sentinel — exact case-sensitive match. Tight format on
# purpose so it can't be triggered by accident or by mentions in
# code blocks discussing the hook itself.
OVERRIDE_RE = re.compile(r"<!--\s*ai-override:\s*(.+?)\s*-->")

# Catalog reference shown in the block message. Project-specific paths
# are resolved at runtime via CLAUDE_PROJECT_DIR.
CATALOG_REL = ".claude/rules/judgment-boundaries.md"


def strip_code_blocks(text: str) -> str:
    """Drop fenced code blocks and inline code so patterns inside them
    don't trigger. The hook is policing user-facing prose, not code."""
    # Fenced ```...```
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Inline `...`
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


def strip_quoted(text: str) -> str:
    """Drop blockquoted lines (`> `) — quoting an over-prompt the user
    sent earlier shouldn't itself trigger."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(">")
    )


def has_question_mark_near(haystack: str, idx: int, window: int = 400) -> bool:
    """True if there's a `?` within `window` chars of `idx`. Cheap proxy
    for 'this match is part of a question, not declarative prose.'"""
    start = max(0, idx - window)
    end = min(len(haystack), idx + window)
    return "?" in haystack[start:end]


def detect(text: str) -> tuple[str, str] | None:
    """Return (pattern_name, matched_phrase) on first hit, else None."""
    if OVERRIDE_RE.search(text):
        return None  # explicit human-judgment escape

    cleaned = strip_quoted(strip_code_blocks(text))
    # Only check the tail — over-prompts cluster at end of turn.
    tail = cleaned[-TAIL_CHARS:] if len(cleaned) > TAIL_CHARS else cleaned

    # Always-fire patterns first — explicit punts don't need a ?
    for pattern, name in ALWAYS_PATTERNS:
        m = re.search(pattern, tail, re.IGNORECASE)
        if m:
            snippet = tail[max(0, m.start() - 40):m.end() + 60].strip()
            return (name, snippet)

    # Question-proximate patterns — match only when ? is nearby.
    for pattern, name in QUESTION_PATTERNS:
        for m in re.finditer(pattern, tail, re.IGNORECASE):
            if has_question_mark_near(tail, m.start()):
                snippet = tail[max(0, m.start() - 40):m.end() + 60].strip()
                return (name, snippet)
    return None


def find_transcript(envelope: dict) -> Path | None:
    """Stop hook envelope sometimes carries `transcript_path` directly.
    Otherwise: ~/.claude/projects/<sanitized-cwd>/<session_id>.jsonl
    where sanitized-cwd is the cwd with `/` replaced by `-` (and a
    leading `-` for absolute paths)."""
    tp = envelope.get("transcript_path")
    if tp:
        p = Path(tp)
        if p.exists():
            return p

    session_id = envelope.get("session_id")
    if not session_id:
        return None

    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    sanitized = cwd.replace("/", "-")
    candidate = Path.home() / ".claude" / "projects" / sanitized / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # Last-resort: walk projects/ for the session file.
    projects = Path.home() / ".claude" / "projects"
    if projects.exists():
        for match in projects.rglob(f"{session_id}.jsonl"):
            return match
    return None


def last_assistant_text(transcript: Path) -> str | None:
    """Read the JSONL transcript and return the text of the most recent
    assistant turn. Skips tool-use-only turns (no text content)."""
    last_text: str | None = None
    try:
        with transcript.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                content = msg.get("content")
                if isinstance(content, str):
                    last_text = content
                elif isinstance(content, list):
                    parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    joined = "\n".join(p for p in parts if p)
                    if joined.strip():
                        last_text = joined
    except OSError:
        return None
    return last_text


def block_message(pattern_name: str, snippet: str, project_dir: str) -> str:
    catalog_path = os.path.join(project_dir, CATALOG_REL)
    return (
        f"OVER-PROMPT DETECTED (pattern: {pattern_name}).\n\n"
        f"Matched span:\n  …{snippet}…\n\n"
        f"Per {catalog_path}:\n"
        f'  "Before prompting the operator for any decision, check this catalog. '
        f"If the action is AI-delegable, make the decision, briefly note what "
        f'you decided, and move on. Do not prompt. Do not ask for confirmation."\n\n'
        f"Re-decide and act. If this genuinely requires human judgment, append "
        f"`<!-- ai-override: <one-line reason citing the catalog or values "
        f"justification> -->` to your final message and stop again."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", help="Run pattern detection on this string and exit")
    args = ap.parse_args()

    if args.test is not None:
        result = detect(args.test)
        if result is None:
            return 0  # no over-prompt, silent allow
        name, snippet = result
        print(json.dumps({
            "decision": "block",
            "reason": block_message(name, snippet, os.environ.get("CLAUDE_PROJECT_DIR", ".")),
        }))
        return 0

    # Production: read Stop envelope from stdin.
    try:
        envelope = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # malformed input — never block, exit silently

    transcript = find_transcript(envelope)
    if transcript is None:
        return 0  # can't locate transcript — never block

    text = last_assistant_text(transcript)
    if not text:
        return 0  # tool-only turn or empty — nothing to police

    result = detect(text)
    if result is None:
        return 0  # clean turn

    name, snippet = result
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    print(json.dumps({
        "decision": "block",
        "reason": block_message(name, snippet, project_dir),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
