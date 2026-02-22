"""
Richmond Transparency Project — CivicPlus Archive Center Discovery Engine

Enumerates all Archive Module IDs (AMIDs) on a CivicPlus city website,
catalogs available document categories, and downloads documents by
priority tier into Layer 1.

Architecture:
  - Discovery: enumerate_amids scans AMID range, identifies active modules
  - Listing: _parse_document_list extracts ADID + title + date per module
  - Download: download_document fetches PDFs via /Archive.aspx?ADID=
  - Text extraction: extract_text via PyMuPDF (same as batch_extract.py)
  - Storage: save_to_documents upserts into documents table (Layer 1)

CivicPlus powers ~3,000+ city websites with identical URL patterns.
This engine works for any CivicPlus site by swapping CIVICPLUS_BASE_URL.

Usage:
  python archive_center_discovery.py --discover
  python archive_center_discovery.py --download 67
  python archive_center_discovery.py --download-tier 1
  python archive_center_discovery.py --stats
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests as req
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

CIVICPLUS_BASE_URL = "https://www.ci.richmond.ca.us"
ARCHIVE_CENTER_PATH = "/ArchiveCenter/"
ARCHIVE_MODULE_URL = "/ArchiveCenter/?AMID={amid}"
ARCHIVE_DOCUMENT_URL = "/Archive.aspx?ADID={adid}"
AMID_RANGE = (1, 250)
CITY_FIPS = "0660620"
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw" / "archive_center"
CACHE_DIR = DATA_DIR / "cache"

CIVICPLUS_PLATFORM_PROFILE = {
    "platform": "CivicPlus (CivicEngage)",
    "archive_center_path": "/ArchiveCenter/",
    "archive_url_pattern": "/ArchiveCenter/?AMID={amid}",
    "document_url_pattern": "/Archive.aspx?ADID={adid}",
    "document_center_path": "/DocumentCenter/",
    "uses_javascript_rendering": False,
    "amid_range": (1, 250),
    "notes": "Powers ~3,000+ city websites. Archive Center URL patterns identical across cities.",
}

# Priority tiers — which AMIDs to download first
TIER_1_AMIDS = {67, 66, 87, 132, 133}   # Resolutions, Ordinances, CM Reports, Personnel Board
TIER_2_AMIDS = {168, 169, 61, 77, 78, 75}  # Rent Board, Design Review, Planning, Housing Authority

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RTP-Bot/1.0",
    "Accept": "text/html",
}


def get_download_tier(amid: int) -> int:
    """Get download priority tier for an AMID."""
    if amid in TIER_1_AMIDS:
        return 1
    elif amid in TIER_2_AMIDS:
        return 2
    return 3


# ── Session management ────────────────────────────────────────

def create_session() -> req.Session:
    """Create HTTP session with proper headers."""
    session = req.Session()
    session.headers.update(HEADERS)
    return session


# ── Parsing ───────────────────────────────────────────────────

def _parse_archive_module(html: str, amid: int) -> dict | None:
    """Parse an archive module page to get name and document count.

    Returns dict with: amid, name, document_count, or None if AMID doesn't exist.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check if this is a valid archive
    archive_div = soup.select_one("#ArchiveCenter")
    if not archive_div:
        return None

    # Check for "does not exist" messages
    text = archive_div.get_text()
    if "does not exist" in text.lower() or "not found" in text.lower():
        return None

    # Get module name from h1
    h1 = archive_div.select_one("h1")
    name = h1.get_text(strip=True) if h1 else f"Archive Module {amid}"

    # Count documents (links with ADID pattern)
    doc_links = archive_div.select("a[href*='ADID=']")
    document_count = len(doc_links)

    return {
        "amid": amid,
        "name": name,
        "document_count": document_count,
    }


def _parse_document_list(html: str) -> list[dict]:
    """Parse document listing from an archive module page.

    Returns list of dicts with: adid, title, date.
    """
    soup = BeautifulSoup(html, "html.parser")
    doc_links = soup.select("a[href*='ADID=']")

    results = []
    for link in doc_links:
        href = link.get("href", "")
        adid_match = re.search(r"ADID=(\d+)", href)
        if not adid_match:
            continue

        adid = adid_match.group(1)
        title = link.get_text(strip=True)

        # Try to find date in parent row/cell
        parent_row = link.find_parent("tr")
        date_str = None
        if parent_row:
            cells = parent_row.find_all("td")
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                # Look for date patterns
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", cell_text)
                if date_match:
                    try:
                        date_str = datetime.strptime(
                            date_match.group(1), "%m/%d/%Y"
                        ).strftime("%Y-%m-%d")
                    except ValueError:
                        pass

        results.append({
            "adid": adid,
            "title": title,
            "date": date_str,
        })

    return results


# ── Discovery ─────────────────────────────────────────────────

def enumerate_amids(
    session: req.Session,
    base_url: str = CIVICPLUS_BASE_URL,
    amid_range: tuple = AMID_RANGE,
) -> dict[int, dict]:
    """Enumerate all active AMIDs on a CivicPlus site.

    Scans the AMID range, parsing each to detect active modules.
    Returns dict mapping AMID to module info.

    Caches results to avoid re-scanning.
    """
    cache_path = CACHE_DIR / "amids.json"
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24 * 7:  # 7-day cache
            cached = json.loads(cache_path.read_text())
            logger.info(f"Using cached AMID data ({len(cached)} modules, {age_hours:.1f}h old)")
            return {int(k): v for k, v in cached.items()}

    logger.info(f"Enumerating AMIDs {amid_range[0]}-{amid_range[1]}...")
    modules = {}

    for amid in range(amid_range[0], amid_range[1] + 1):
        url = f"{base_url}{ARCHIVE_MODULE_URL.format(amid=amid)}"
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                continue

            result = _parse_archive_module(resp.text, amid)
            if result:
                modules[amid] = result
                tier = get_download_tier(amid)
                logger.info(
                    f"  AMID {amid:3d}: {result['name'][:50]:50s} "
                    f"({result['document_count']:4d} docs) [Tier {tier}]"
                )

            time.sleep(0.2)  # Rate limit: 5 req/sec

        except Exception as e:
            logger.debug(f"  AMID {amid}: error — {e}")
            continue

    # Cache results
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(modules, indent=2))
    logger.info(f"Found {len(modules)} active AMIDs (cached to {cache_path})")

    return modules


# ── Document download ─────────────────────────────────────────

def download_document(
    session: req.Session,
    adid: str,
    dest_dir: Path,
    base_url: str = CIVICPLUS_BASE_URL,
) -> Path | None:
    """Download a document PDF from the Archive Center.

    Returns local file path, or None on failure.
    """
    url = f"{base_url}{ARCHIVE_DOCUMENT_URL.format(adid=adid)}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"ADID_{adid}.pdf"

    if dest_path.exists():
        logger.debug(f"Already downloaded ADID {adid}")
        return dest_path

    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.debug(f"Downloaded ADID {adid} ({dest_path.stat().st_size:,} bytes)")
        return dest_path
    except Exception as e:
        logger.error(f"Failed to download ADID {adid}: {e}")
        return None


def extract_text(filepath: Path) -> str | None:
    """Extract text from PDF using PyMuPDF. Same pattern as batch_extract.py."""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed — skipping extraction")
        return None

    try:
        doc = fitz.open(str(filepath))
        text_parts = [page.get_text() for page in doc]
        doc.close()
        text = "\n".join(text_parts).strip()
        return text if text else None
    except Exception as e:
        logger.error(f"Failed to extract text from {filepath}: {e}")
        return None


# ── Database operations ───────────────────────────────────────

def save_to_documents(conn, docs: list[dict], city_fips: str) -> dict:
    """Save archive documents to Layer 1 documents table.

    Returns stats dict.
    """
    from db import ingest_document

    saved = 0
    skipped = 0

    for doc in docs:
        try:
            ingest_document(
                conn,
                city_fips=city_fips,
                source_type="archive_center",
                raw_content=(doc.get("text") or "").encode("utf-8") if doc.get("text") else None,
                credibility_tier=1,
                source_url=f"{CIVICPLUS_BASE_URL}{ARCHIVE_DOCUMENT_URL.format(adid=doc['adid'])}",
                source_identifier=f"archive_center_ADID_{doc['adid']}",
                mime_type="application/pdf",
                metadata={
                    "amid": doc.get("amid"),
                    "amid_name": doc.get("amid_name"),
                    "adid": doc["adid"],
                    "title": doc.get("title"),
                    "date": doc.get("date"),
                    "pipeline": "archive_center_discovery",
                },
            )
            saved += 1
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                skipped += 1
            else:
                logger.error(f"Failed to save ADID {doc.get('adid')}: {e}")
                skipped += 1

    conn.commit()
    return {"saved": saved, "skipped": skipped}


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — Archive Center Discovery Engine",
    )
    parser.add_argument("--discover", action="store_true", help="Enumerate all AMIDs")
    parser.add_argument("--download", type=int, help="Download all docs from one AMID")
    parser.add_argument("--download-tier", type=int, choices=[1, 2, 3],
                       help="Download all docs from tier N AMIDs")
    parser.add_argument("--since", type=str, help="Only docs since YYYY-MM-DD")
    parser.add_argument("--stats", action="store_true", help="Print archive statistics")
    parser.add_argument("--output", type=str, help="Save JSON output to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = create_session()

    if args.discover or args.stats:
        modules = enumerate_amids(session)

        if args.stats:
            total_docs = sum(m["document_count"] for m in modules.values())
            print(f"\n{'='*60}")
            print(f"Archive Center Statistics")
            print(f"  Active modules: {len(modules)}")
            print(f"  Total documents: {total_docs:,}")
            for tier in [1, 2, 3]:
                tier_modules = {k: v for k, v in modules.items() if get_download_tier(k) == tier}
                tier_docs = sum(m["document_count"] for m in tier_modules.values())
                print(f"  Tier {tier}: {len(tier_modules)} modules, {tier_docs:,} docs")
            print(f"{'='*60}")
        else:
            print(f"\nActive AMIDs: {len(modules)}")
            for amid, info in sorted(modules.items()):
                tier = get_download_tier(amid)
                print(f"  AMID {amid:3d}: {info['name'][:50]:50s} ({info['document_count']:4d} docs) [Tier {tier}]")

    elif args.download:
        url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_MODULE_URL.format(amid=args.download)}"
        resp = session.get(url)
        docs = _parse_document_list(resp.text)

        if args.since:
            docs = [d for d in docs if not d.get("date") or d["date"] >= args.since]

        dest = RAW_DIR / f"AMID_{args.download}"
        print(f"Downloading {len(docs)} documents from AMID {args.download}...")
        for doc in docs:
            download_document(session, doc["adid"], dest)
            time.sleep(0.2)

    elif args.download_tier is not None:
        modules = enumerate_amids(session)
        tier_modules = {k: v for k, v in modules.items()
                       if get_download_tier(k) == args.download_tier}
        print(f"Downloading Tier {args.download_tier}: {len(tier_modules)} modules")
        for amid, info in sorted(tier_modules.items()):
            print(f"\n  AMID {amid}: {info['name']}")
            url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_MODULE_URL.format(amid=amid)}"
            resp = session.get(url)
            docs = _parse_document_list(resp.text)
            dest = RAW_DIR / f"AMID_{amid}"
            for doc in docs:
                download_document(session, doc["adid"], dest)
                time.sleep(0.2)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
