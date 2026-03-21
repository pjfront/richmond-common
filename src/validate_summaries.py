"""
Post-R1 readability validator for generated summaries and headlines.

Checks all plain_language_summary and summary_headline fields against
the S12.1 plain language standards:
- Word count limits (75 words summary, 20 words headline)
- Sentence count limits (4 sentences summary, 1 sentence headline)
- Sentence length ceiling (25 words per sentence)
- Readability metrics (Flesch-Kincaid grade level target: ≤8)
- Banned patterns (shall, passive voice markers, jargon)
- JSON parse success rate (for batch run diagnostics)

Usage:
  python validate_summaries.py                  # Full validation report
  python validate_summaries.py --meeting-id UUID  # Single meeting
  python validate_summaries.py --sample 100     # Random sample
  python validate_summaries.py --fix-missing    # List items with summary but no headline
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402

# ── Rules from S12.1 research ───────────────────────────────

MAX_SUMMARY_WORDS = 75
MAX_HEADLINE_WORDS = 20
MAX_SENTENCES_SUMMARY = 4
MAX_SENTENCE_WORDS = 25
TARGET_GRADE_LEVEL = 8  # Flesch-Kincaid target

BANNED_WORDS = {"shall", "whereas", "hereby", "thereof", "pursuant"}
PASSIVE_PATTERN = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+\w+ed\b", re.IGNORECASE
)
JARGON_TERMS = {
    "ordinance": "law",
    "appropriation": "spending",
    "resolution": "formal decision",
    "promulgate": "issue",
    "adjudicate": "decide",
}


def _count_words(text: str) -> int:
    return len(text.split())


def _count_sentences(text: str) -> int:
    # Split on sentence-ending punctuation
    sentences = re.split(r"[.!?]+", text.strip())
    return len([s for s in sentences if s.strip()])


def _max_sentence_length(text: str) -> int:
    sentences = re.split(r"[.!?]+", text.strip())
    lengths = [len(s.split()) for s in sentences if s.strip()]
    return max(lengths) if lengths else 0


def _flesch_kincaid_grade(text: str) -> float:
    """Approximate Flesch-Kincaid grade level without textstat dependency."""
    words = text.split()
    if not words:
        return 0.0

    sentences = _count_sentences(text)
    if sentences == 0:
        sentences = 1

    # Count syllables (rough approximation)
    syllable_count = 0
    for word in words:
        word = word.lower().strip(".,!?;:'\"()-")
        if not word:
            continue
        # Count vowel groups
        count = len(re.findall(r"[aeiouy]+", word))
        # At least one syllable per word
        count = max(1, count)
        # Silent e
        if word.endswith("e") and count > 1:
            count -= 1
        syllable_count += count

    word_count = len(words)
    return (
        0.39 * (word_count / sentences)
        + 11.8 * (syllable_count / word_count)
        - 15.59
    )


def validate_item(item: dict[str, Any]) -> dict[str, Any]:
    """Validate a single item's summary and headline."""
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    summary = item.get("plain_language_summary")
    headline = item.get("summary_headline")

    # Summary checks
    if summary:
        word_count = _count_words(summary)
        sentence_count = _count_sentences(summary)
        max_sent_len = _max_sentence_length(summary)
        grade = _flesch_kincaid_grade(summary)

        metrics["summary_words"] = word_count
        metrics["summary_sentences"] = sentence_count
        metrics["summary_max_sentence_words"] = max_sent_len
        metrics["summary_grade_level"] = round(grade, 1)

        if word_count > MAX_SUMMARY_WORDS:
            issues.append(f"summary too long: {word_count} words (max {MAX_SUMMARY_WORDS})")
        if sentence_count > MAX_SENTENCES_SUMMARY:
            issues.append(f"summary too many sentences: {sentence_count} (max {MAX_SENTENCES_SUMMARY})")
        if max_sent_len > MAX_SENTENCE_WORDS:
            issues.append(f"summary sentence too long: {max_sent_len} words (max {MAX_SENTENCE_WORDS})")
        if grade > TARGET_GRADE_LEVEL + 2:
            issues.append(f"summary reading level high: grade {grade:.1f} (target ≤{TARGET_GRADE_LEVEL})")

        # Check banned words
        summary_lower = summary.lower()
        for word in BANNED_WORDS:
            if word in summary_lower:
                issues.append(f"summary contains banned word: '{word}'")

        # Check passive voice
        passive_matches = PASSIVE_PATTERN.findall(summary)
        if passive_matches:
            metrics["summary_passive_count"] = len(passive_matches)
            if len(passive_matches) >= 2:
                issues.append(f"summary has {len(passive_matches)} passive voice instances")

        # Check jargon
        for jargon, replacement in JARGON_TERMS.items():
            if jargon in summary_lower:
                issues.append(f"summary uses jargon '{jargon}' (use '{replacement}')")
    else:
        issues.append("missing summary")

    # Headline checks
    if headline:
        hw_count = _count_words(headline)
        hs_count = _count_sentences(headline)

        metrics["headline_words"] = hw_count
        metrics["headline_sentences"] = hs_count

        if hw_count > MAX_HEADLINE_WORDS:
            issues.append(f"headline too long: {hw_count} words (max {MAX_HEADLINE_WORDS})")
        if hs_count > 1:
            issues.append(f"headline has {hs_count} sentences (should be 1)")
    elif summary:
        issues.append("missing headline (summary exists)")

    return {
        "id": item["id"],
        "title": (item.get("title") or "")[:60],
        "issues": issues,
        "metrics": metrics,
        "has_summary": summary is not None,
        "has_headline": headline is not None,
    }


def run_validation(
    city_fips: str = RICHMOND_FIPS,
    *,
    meeting_id: str | None = None,
    sample: int | None = None,
) -> list[dict[str, Any]]:
    """Run validation on all summaries in the database."""
    conn = get_connection()

    conditions = ["m.city_fips = %s", "ai.plain_language_summary IS NOT NULL"]
    params: list[Any] = [city_fips]

    if meeting_id:
        conditions.append("ai.meeting_id = %s")
        params.append(meeting_id)

    where_clause = " AND ".join(conditions)
    order = "ORDER BY RANDOM()" if sample else "ORDER BY m.meeting_date DESC"
    limit_clause = f"LIMIT {sample}" if sample else ""

    query = f"""
        SELECT ai.id, ai.title, ai.plain_language_summary,
               ai.summary_headline, ai.category
        FROM agenda_items ai
        JOIN meetings m ON ai.meeting_id = m.id
        WHERE {where_clause}
        {order}
        {limit_clause}
    """

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [desc[0] for desc in cur.description]
        items = [dict(zip(cols, row)) for row in cur.fetchall()]

    conn.close()

    return [validate_item(item) for item in items]


def print_report(results: list[dict[str, Any]]) -> None:
    """Print validation summary report."""
    total = len(results)
    if total == 0:
        print("No summaries found to validate.")
        return

    with_issues = [r for r in results if r["issues"]]
    with_headline = sum(1 for r in results if r["has_headline"])
    clean = total - len(with_issues)

    print("=" * 60)
    print("SUMMARY READABILITY VALIDATION REPORT")
    print("=" * 60)
    print(f"\nTotal items validated: {total}")
    print(f"  Clean (no issues): {clean} ({clean/total*100:.0f}%)")
    print(f"  With issues: {len(with_issues)} ({len(with_issues)/total*100:.0f}%)")
    print(f"  Has headline: {with_headline} ({with_headline/total*100:.0f}%)")
    print(f"  Missing headline: {total - with_headline}")

    # Aggregate metrics
    summary_words = [r["metrics"].get("summary_words", 0) for r in results if r["has_summary"]]
    summary_grades = [r["metrics"].get("summary_grade_level", 0) for r in results if r["has_summary"]]
    headline_words = [r["metrics"].get("headline_words", 0) for r in results if r["has_headline"]]

    if summary_words:
        print(f"\nSummary word count: avg={sum(summary_words)/len(summary_words):.0f}, "
              f"max={max(summary_words)}, min={min(summary_words)}")
    if summary_grades:
        print(f"Summary grade level: avg={sum(summary_grades)/len(summary_grades):.1f}, "
              f"max={max(summary_grades):.1f}, min={min(summary_grades):.1f}")
    if headline_words:
        print(f"Headline word count: avg={sum(headline_words)/len(headline_words):.0f}, "
              f"max={max(headline_words)}, min={min(headline_words)}")

    # Issue breakdown
    issue_counts: dict[str, int] = {}
    for r in with_issues:
        for issue in r["issues"]:
            # Normalize issue type (strip specific values)
            issue_type = re.sub(r": \d+.*", "", issue)
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

    if issue_counts:
        print(f"\nIssue breakdown:")
        for issue_type, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            print(f"  {count:>5d}  {issue_type}")

    # Worst offenders (top 10 by issue count)
    worst = sorted(with_issues, key=lambda r: len(r["issues"]), reverse=True)[:10]
    if worst:
        print(f"\nTop issues (worst {min(10, len(worst))} items):")
        for r in worst:
            print(f"  {r['id'][:8]}... {r['title']}")
            for issue in r["issues"]:
                print(f"    - {issue}")


def list_missing_headlines(city_fips: str = RICHMOND_FIPS) -> None:
    """List items that have a summary but no headline."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM agenda_items ai
               JOIN meetings m ON ai.meeting_id = m.id
               WHERE m.city_fips = %s
               AND ai.plain_language_summary IS NOT NULL
               AND ai.summary_headline IS NULL""",
            (city_fips,),
        )
        count = cur.fetchone()[0]
    conn.close()
    print(f"Items with summary but no headline: {count}")
    if count > 0:
        print("These will need regeneration via batch_summarize.py or generate_summaries.py --force")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate generated summaries against plain language standards"
    )
    parser.add_argument("--meeting-id", help="Validate single meeting")
    parser.add_argument("--sample", type=int, help="Random sample size")
    parser.add_argument("--fips", default=RICHMOND_FIPS)
    parser.add_argument(
        "--fix-missing",
        action="store_true",
        help="List items needing headline generation",
    )
    args = parser.parse_args()

    if args.fix_missing:
        list_missing_headlines(args.fips)
        return

    results = run_validation(args.fips, meeting_id=args.meeting_id, sample=args.sample)
    print_report(results)


if __name__ == "__main__":
    main()
