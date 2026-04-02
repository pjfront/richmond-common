#!/usr/bin/env python3
"""
Search downloaded NextRequest CPRA documents.

Downloads and indexes documents from a NextRequest public records request,
then provides full-text search across all released documents.

Usage:
    python search_nextrequest_docs.py "search term"
    python search_nextrequest_docs.py "search term" --request 24-428
    python search_nextrequest_docs.py "search term" --context 200
    python search_nextrequest_docs.py --list               # list all documents
    python search_nextrequest_docs.py --stats               # show corpus stats
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "raw" / "nextrequest"
DEFAULT_REQUEST = "24-428"
DEFAULT_CONTEXT = 150  # chars of context around matches


def load_corpus(request_id: str) -> list[dict]:
    corpus_path = DATA_DIR / request_id / "searchable_corpus.json"
    if not corpus_path.exists():
        print(f"Error: No corpus found at {corpus_path}")
        print(f"Run the download/extract pipeline first.")
        sys.exit(1)
    with open(corpus_path) as f:
        return json.load(f)


def search(corpus: list[dict], query: str, context_chars: int = DEFAULT_CONTEXT) -> list[dict]:
    """Search corpus for query string. Returns matches with context."""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results = []

    for doc in corpus:
        text = doc.get("text", "")
        if not text:
            continue

        matches_in_doc = []
        for match in pattern.finditer(text):
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            snippet = text[start:end].strip()
            # Clean up whitespace
            snippet = re.sub(r"\s+", " ", snippet)
            matches_in_doc.append({
                "snippet": snippet,
                "position": match.start(),
            })

        if matches_in_doc:
            results.append({
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "match_count": len(matches_in_doc),
                "matches": matches_in_doc,
                "page_count": doc.get("page_count", 0),
                "upload_date": doc.get("upload_date", ""),
            })

    # Sort by match count descending
    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results


def print_results(results: list[dict], query: str) -> None:
    if not results:
        print(f'No results for "{query}"')
        return

    total_matches = sum(r["match_count"] for r in results)
    print(f'\n=== {total_matches} matches for "{query}" across {len(results)} documents ===\n')

    for r in results:
        print(f"--- {r['title']} ({r['match_count']} matches, {r['page_count']} pages) ---")
        print(f"    Doc ID: {r['doc_id']} | {r['upload_date']}")
        # Show up to 3 snippets per doc
        for m in r["matches"][:3]:
            snippet = m["snippet"]
            # Highlight the match
            highlighted = re.sub(
                re.escape(query),
                lambda x: f">>>{x.group()}<<<",
                snippet,
                flags=re.IGNORECASE,
            )
            print(f"    ...{highlighted}...")
        if len(r["matches"]) > 3:
            print(f"    ... and {len(r['matches']) - 3} more matches")
        print()


def print_stats(corpus: list[dict]) -> None:
    total = len(corpus)
    with_text = sum(1 for d in corpus if d.get("text", "").strip())
    total_chars = sum(d.get("char_count", 0) for d in corpus)
    total_pages = sum(d.get("page_count", 0) for d in corpus)
    total_bytes = sum(d.get("file_size_bytes", 0) for d in corpus)

    print(f"Documents: {total}")
    print(f"With searchable text: {with_text}")
    print(f"Total pages: {total_pages}")
    print(f"Total text: {total_chars:,} chars ({total_chars/1024:.0f} KB)")
    print(f"Total file size: {total_bytes/1024/1024:.1f} MB")

    # By extension
    from collections import Counter
    exts = Counter(d.get("file_extension", "?") for d in corpus)
    print(f"File types: {dict(exts)}")


def print_list(corpus: list[dict]) -> None:
    for i, doc in enumerate(corpus, 1):
        has_text = "+" if doc.get("text", "").strip() else "-"
        chars = doc.get("char_count", 0)
        print(f"  {i:3d}. [{has_text}] {doc['title']} ({chars:,} chars)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search NextRequest CPRA documents")
    parser.add_argument("query", nargs="?", help="Search term")
    parser.add_argument("--request", default=DEFAULT_REQUEST, help="Request ID (default: 24-428)")
    parser.add_argument("--context", type=int, default=DEFAULT_CONTEXT, help="Context chars around matches")
    parser.add_argument("--list", action="store_true", help="List all documents")
    parser.add_argument("--stats", action="store_true", help="Show corpus statistics")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    corpus = load_corpus(args.request)

    if args.stats:
        print_stats(corpus)
        return

    if args.list:
        print_list(corpus)
        return

    if not args.query:
        parser.print_help()
        return

    results = search(corpus, args.query, args.context)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_results(results, args.query)


if __name__ == "__main__":
    main()
