"""Stable, source-closest fingerprints for public upstream artifacts.

This module intentionally uses only the Python standard library.  The
15-minute change-detector workflow sparsely checks it out without installing
project dependencies, while the full source pipelines reuse the exact same
normalization rules before deciding whether an existing record is current.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_ESCRIBE_VOLATILE_HTML = (
    # Cloudflare injects a hidden per-response nonce anchor immediately after
    # <body>.  It is unrelated to the published agenda.
    re.compile(
        r'<a\s+href="[^"]*/cdn-cgi/content\?id=[^"]+"'
        r'[^>]*aria-hidden="true"[^>]*>\s*</a>',
        re.IGNORECASE | re.DOTALL,
    ),
    # ASP.NET signs these hidden fields on every response.  Agenda content is
    # outside the controls, so retaining them would dispatch every 15 minutes.
    re.compile(
        r'<input\b[^>]*\bname="__[^"]+"[^>]*>',
        re.IGNORECASE | re.DOTALL,
    ),
    # Cloudflare's email-protection cipher changes while the visible address
    # and agenda text remain identical.
    re.compile(r'data-cfemail="[0-9a-f]+"', re.IGNORECASE),
    # The same per-response cipher is repeated in the protection link's URL.
    # Keep the link target shape but remove only its volatile hex payload.
    re.compile(
        r'(?<=/cdn-cgi/l/email-protection#)[0-9a-f]+',
        re.IGNORECASE,
    ),
)


def _stable_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonicalize_escribe_agenda_html(html: str) -> str:
    """Remove only observed transport/session nonces from eSCRIBE HTML."""
    canonical = html
    for pattern in _ESCRIBE_VOLATILE_HTML:
        canonical = pattern.sub("", canonical)
    return canonical


def escribe_agenda_html_sha256(html: str) -> str:
    """Hash the published agenda page after transport-noise normalization."""
    return hashlib.sha256(
        canonicalize_escribe_agenda_html(html).encode("utf-8")
    ).hexdigest()


def escribe_meeting_revision(
    meeting: dict,
    *,
    agenda_html: str | None = None,
) -> dict[str, Any]:
    """Return a stable revision packet for one eSCRIBE calendar meeting.

    The calendar response exposes agenda/document publication directly via
    ``HasAgenda`` and ``MeetingDocumentLink``.  The normalized HTML hash closes
    the remaining gap where staff amend an agenda in-place without assigning a
    new document ID.
    """
    document_links = []
    raw_links = meeting.get("MeetingDocumentLink") or []
    if not isinstance(raw_links, list):
        raw_links = []
    for link in raw_links:
        if not isinstance(link, dict):
            continue
        # Video availability is operational state, not agenda/document
        # freshness.  Agenda, cover, and additional-document links are source
        # artifacts and therefore part of the revision.
        if str(link.get("Type") or "").lower() == "video":
            continue
        document_links.append({
            "format": link.get("Format"),
            "language_id": link.get("LanguageId"),
            "sequence": link.get("Sequence"),
            "title": link.get("Title"),
            "type": link.get("Type"),
            "url": link.get("Url"),
        })
    document_links.sort(
        key=lambda link: json.dumps(
            link,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )

    calendar = {
        "description": meeting.get("Description"),
        "document_links": document_links,
        "end_date": meeting.get("EndDate"),
        "has_agenda": bool(meeting.get("HasAgenda")),
        "id": meeting.get("ID"),
        "is_cancelled": bool(meeting.get("IsCancelled")),
        "location": meeting.get("Location"),
        "meeting_name": meeting.get("MeetingName"),
        "start_date": meeting.get("StartDate"),
    }
    agenda_sha256 = (
        escribe_agenda_html_sha256(agenda_html)
        if agenda_html is not None
        else None
    )
    revision_sha256 = _stable_json_sha256({
        "agenda_sha256": agenda_sha256,
        "calendar": calendar,
    })
    return {
        "agenda_sha256": agenda_sha256,
        "calendar_sha256": _stable_json_sha256(calendar),
        "revision_sha256": revision_sha256,
    }
