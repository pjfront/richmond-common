#!/usr/bin/env python3
"""One-time backfill: populate raw_text from raw_content for archive_center documents.

Context: save_to_documents was storing PDF text as bytes in raw_content but never
setting raw_text. sync_minutes_extraction queries raw_text, so it found 0 docs.
This script decodes raw_content bytes to text (stripping null bytes from PDFs)
and writes the result to raw_text.

Usage:
    cd src && python backfill_raw_text.py [--dry-run]
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection  # noqa: E402


def backfill(dry_run: bool = False) -> None:
    conn = get_connection()

    # Find documents with raw_content but no raw_text
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, octet_length(raw_content)
               FROM documents
               WHERE source_type = 'archive_center'
                 AND raw_content IS NOT NULL
                 AND (raw_text IS NULL OR raw_text = '')"""
        )
        candidates = cur.fetchall()

    print(f"Found {len(candidates)} documents to backfill")

    if not candidates:
        print("Nothing to do.")
        return

    if dry_run:
        total_bytes = sum(size for _, size in candidates)
        print(f"[DRY RUN] Would update {len(candidates)} rows ({total_bytes:,} bytes total)")
        return

    updated = 0
    errors = 0

    for doc_id, size in candidates:
        try:
            with conn.cursor() as cur:
                # Read raw_content as bytes
                cur.execute(
                    "SELECT raw_content FROM documents WHERE id = %s",
                    (doc_id,),
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    continue

                raw_bytes = bytes(row[0])
                # Strip null bytes and decode
                clean_text = raw_bytes.replace(b"\x00", b"").decode("utf-8", errors="replace")

                if not clean_text.strip():
                    continue

                cur.execute(
                    "UPDATE documents SET raw_text = %s WHERE id = %s",
                    (clean_text, doc_id),
                )
                updated += 1

                if updated % 500 == 0:
                    conn.commit()
                    print(f"  ... {updated}/{len(candidates)} updated")

        except Exception as e:
            errors += 1
            print(f"  ERROR on {doc_id}: {e}")

    conn.commit()
    print(f"\nDone: {updated} updated, {errors} errors out of {len(candidates)} candidates")
    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    backfill(dry_run=dry)
