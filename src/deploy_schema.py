#!/usr/bin/env python3
"""
Deploy schema.sql to Supabase PostgreSQL.

Usage:
    python deploy_schema.py [--rls-only]

Reads DATABASE_URL from .env and runs schema.sql against it.
Also runs RLS policies for public read access.
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def get_connection(autocommit=False):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)
    conn = psycopg2.connect(database_url, connect_timeout=15)
    if autocommit:
        conn.autocommit = True
    return conn


def deploy_schema():
    print("Connecting to database...")
    conn = get_connection()

    print("Connected! Running schema.sql...")
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("Schema deployed successfully!")
    except Exception as e:
        conn.rollback()
        print(f"ERROR deploying schema: {e}")
        sys.exit(1)

    # Verify tables
    print("\nVerifying tables...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]
        print(f"Found {len(tables)} tables: {', '.join(tables)}")

    # Verify Richmond seed
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM cities WHERE fips_code = '0660620'")
        row = cur.fetchone()
        if row:
            print(f"\nRichmond seed verified: {row}")
        else:
            print("\nWARNING: Richmond city seed not found!")

    conn.close()


def deploy_rls():
    """Deploy RLS policies using a fresh autocommit connection."""
    print("\nDeploying RLS policies for public read access...")

    # Fresh connection in autocommit mode — each statement is its own transaction
    conn = get_connection(autocommit=True)

    rls_tables = [
        "cities", "officials", "meetings", "meeting_attendance",
        "agenda_items", "motions", "votes", "contributions",
        "donors", "committees", "conflict_flags", "closed_session_items",
        "public_comments", "friendly_amendments",
    ]
    for table in rls_tables:
        try:
            with conn.cursor() as cur:
                cur.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;')
                cur.execute(
                    f"""DO $$ BEGIN
                        CREATE POLICY "Public read" ON {table}
                            FOR SELECT USING (true);
                    EXCEPTION WHEN duplicate_object THEN NULL;
                    END $$;"""
                )
            print(f"  ✓ {table}")
        except Exception as e:
            print(f"  WARNING on {table}: {e}")

    conn.close()
    print("Done! RLS policies deployed.")


if __name__ == "__main__":
    rls_only = "--rls-only" in sys.argv
    if not rls_only:
        deploy_schema()
    deploy_rls()
