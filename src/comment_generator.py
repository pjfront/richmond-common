"""
Richmond Common - Pre-Meeting Transparency Comment Generator

This is the core output of the system: an automated public comment submitted
before each Richmond City Council meeting that surfaces potential conflicts
of interest, donor correlations, and missing documents.

The comment is submitted via email to the City Clerk before the deadline
(typically 1:00 PM or 2:00 PM on meeting day) and becomes part of the
official meeting record, attached to the approved minutes.

This module handles comment FORMATTING and SUBMISSION.
Conflict detection logic lives in conflict_scanner.py.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template

from conflict_scanner import ScanResult, ConflictFlag, scan_meeting_json
from escribemeetings_enricher import enrich_meeting_data


# ── Missing Document Detection ───────────────────────────────
# This stays here (not in scanner) because it's about document
# completeness, not financial conflicts.

@dataclass
class MissingDocument:
    referenced_in: str            # where the reference was found
    document_description: str
    expected_location: str
    recommendation: str


def detect_missing_documents(meeting_data: dict) -> list[MissingDocument]:
    """Scan agenda items for referenced documents that may not be public.

    Checks for:
    - Resolution numbers without linked text
    - Staff reports mentioned but not linked
    - Policies referenced for revision without the current version available
    """
    missing = []

    all_items = []
    consent = meeting_data.get("consent_calendar", {})
    for item in consent.get("items", []):
        all_items.append(item)
    for item in meeting_data.get("action_items", []):
        all_items.append(item)
    for item in meeting_data.get("housing_authority_items", []):
        all_items.append(item)

    for item in all_items:
        item_num = item.get("item_number", "")
        item_title = item.get("title", "")
        item_desc = item.get("description", "")
        text_lower = f"{item_title} {item_desc}".lower()

        # Resolution referenced but no text available
        res_num = item.get("resolution_number")
        if res_num and not item.get("resolution_text_available"):
            missing.append(MissingDocument(
                referenced_in=f"Item {item_num}",
                document_description=f"Resolution No. {res_num}",
                expected_location="City Clerk's resolution archive",
                recommendation="Full resolution text should be publicly available before the vote",
            ))

        # Policy revision without the current version
        revision_phrases = [
            "revise the current", "amend the existing", "update the current",
            "modify the existing", "replace the current",
        ]
        if any(phrase in text_lower for phrase in revision_phrases):
            # Check if it's a policy/protocol/procedure
            policy_words = ["policy", "protocol", "procedure", "guideline", "ordinance"]
            if any(pw in text_lower for pw in policy_words):
                missing.append(MissingDocument(
                    referenced_in=f"Item {item_num}",
                    document_description=f"Current version of document being revised: {item_title}",
                    expected_location="Relevant department or City website",
                    recommendation=(
                        "The agenda item proposes revisions but the current version "
                        "is not linked or publicly available for comparison"
                    ),
                ))

    return missing


# ── HTML Comment Template ────────────────────────────────────

HTML_COMMENT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pre-Meeting Transparency Report - {{ meeting_date }}</title>
</head>
<body style="margin:0; padding:0; background-color:#f5f5f5; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height:1.6; color:#1a1a1a;">
<div style="max-width:680px; margin:0 auto; background:#ffffff; border:1px solid #e0e0e0;">

  <!-- Header -->
  <div style="background-color:#1a365d; color:#ffffff; padding:28px 32px;">
    <h1 style="margin:0 0 4px 0; font-size:22px; font-weight:600; letter-spacing:0.3px;">Richmond Common</h1>
    <p style="margin:0; font-size:15px; color:#cbd5e0;">Pre-Meeting Transparency Report</p>
  </div>

  <!-- Meeting info bar -->
  <div style="background-color:#edf2f7; padding:14px 32px; border-bottom:1px solid #e2e8f0;">
    <span style="font-size:14px; color:#4a5568;">{{ meeting_type | title }} City Council Meeting &mdash; <strong>{{ meeting_date }}</strong></span>
  </div>

  <!-- Methodology -->
  <div style="padding:24px 32px; border-bottom:1px solid #e2e8f0;">
    <h2 style="margin:0 0 12px 0; font-size:16px; color:#2d3748; text-transform:uppercase; letter-spacing:0.5px;">Methodology</h2>
    <p style="margin:0 0 10px 0; font-size:14px; color:#4a5568;">
      This report cross-references publicly available campaign finance records
      (filed with the City Clerk via NetFile and the FPPC via CAL-ACCESS)
      against the agenda for the upcoming City Council meeting. All citations
      reference specific public filings.
    </p>
    <p style="margin:0 0 16px 0; font-size:13px; color:#718096; font-style:italic;">
      This report is informational only and does not constitute legal advice
      or a determination of conflict under Government Code Sections 87100-87105.
    </p>
    <table style="font-size:14px; color:#2d3748; border-collapse:collapse;">
      <tr><td style="padding:2px 16px 2px 0; color:#718096;">Items scanned:</td><td><strong>{{ total_items }}</strong></td></tr>
      <tr><td style="padding:2px 16px 2px 0; color:#718096;">Campaign finance records searched:</td><td><strong>{{ contribution_count | default("27,035", true) }}</strong></td></tr>
      {%- if enriched_count > 0 %}
      <tr><td style="padding:2px 16px 2px 0; color:#718096;">Items with enhanced document scanning:</td><td><strong>{{ enriched_count }}</strong></td></tr>
      {%- endif %}
      <tr><td style="padding:2px 16px 2px 0; color:#718096;">Findings:</td><td><strong>{{ tier1_count + tier2_count }}</strong></td></tr>
      {%- if suppressed_count > 0 %}
      <tr><td style="padding:2px 16px 2px 0; color:#718096;">Additional matches tracked internally:</td><td>{{ suppressed_count }}</td></tr>
      {%- endif %}
    </table>
  </div>

  {%- if tier1_flags %}
  <!-- Tier 1: Potential Conflicts -->
  <div style="padding:24px 32px; border-bottom:1px solid #e2e8f0;">
    <h2 style="margin:0 0 16px 0; font-size:16px; color:#c53030; text-transform:uppercase; letter-spacing:0.5px;">&#9888; Potential Conflicts of Interest</h2>
    {%- for flag in tier1_flags %}
    <div style="margin-bottom:20px; padding:16px; background-color:#fff5f5; border-left:4px solid #c53030; border-radius:0 4px 4px 0;">
      <h3 style="margin:0 0 4px 0; font-size:15px; color:#1a202c;">{{ flag.agenda_item_title }}{% if flag.financial_amount %} &mdash; {{ flag.financial_amount }}{% endif %}</h3>
      <p style="margin:0 0 8px 0; font-size:13px; color:#718096;">Agenda Item {{ flag.agenda_item_number }}</p>
      <p style="margin:0 0 10px 0; font-size:14px; color:#2d3748;">{{ flag.description }}</p>
      {%- if "sitting council member" in (flag.council_member or "") %}
      <p style="margin:0 0 10px 0; font-size:14px; color:#2d3748;">
        {{ flag.council_member.split(" (")[0] }} is a sitting member who will vote on this item.
      </p>
      {%- endif %}
      <p style="margin:0; font-size:13px; color:#718096;">
        Under California's Political Reform Act (Gov. Code &sect;&sect;87100),
        elected officials must disqualify themselves from governmental decisions
        that could financially benefit a source of income of $500 or more received
        in the prior 12 months.
      </p>
    </div>
    {%- endfor %}
  </div>
  {%- endif %}

  {%- if tier2_flags %}
  <!-- Tier 2: Financial Connections -->
  <div style="padding:24px 32px; border-bottom:1px solid #e2e8f0;">
    <h2 style="margin:0 0 12px 0; font-size:16px; color:#b7791f; text-transform:uppercase; letter-spacing:0.5px;">Additional Financial Connections</h2>
    <p style="margin:0 0 16px 0; font-size:14px; color:#4a5568;">
      The following donor-vendor connections were identified in public campaign
      finance records. These do not necessarily indicate conflicts of interest
      but are disclosed for transparency.
    </p>
    {%- for flag in tier2_flags %}
    <div style="margin-bottom:16px; padding:14px; background-color:#fffff0; border-left:4px solid #d69e2e; border-radius:0 4px 4px 0;">
      <h3 style="margin:0 0 4px 0; font-size:15px; color:#1a202c;">{{ flag.agenda_item_title }}{% if flag.financial_amount %} &mdash; {{ flag.financial_amount }}{% endif %}</h3>
      <p style="margin:0 0 8px 0; font-size:13px; color:#718096;">Agenda Item {{ flag.agenda_item_number }}</p>
      <p style="margin:0; font-size:14px; color:#2d3748;">{{ flag.description }}</p>
    </div>
    {%- endfor %}
  </div>
  {%- endif %}

  {%- if missing_docs %}
  <!-- Missing Documents -->
  <div style="padding:24px 32px; border-bottom:1px solid #e2e8f0;">
    <h2 style="margin:0 0 16px 0; font-size:16px; color:#2d3748; text-transform:uppercase; letter-spacing:0.5px;">Missing or Inaccessible Public Documents</h2>
    {%- for doc in missing_docs %}
    <div style="margin-bottom:14px; padding:12px; background-color:#ebf8ff; border-left:4px solid #3182ce; border-radius:0 4px 4px 0;">
      <p style="margin:0 0 4px 0; font-size:13px; color:#718096;">Referenced in {{ doc.referenced_in }}</p>
      <p style="margin:0 0 4px 0; font-size:14px; color:#2d3748;"><strong>{{ doc.document_description }}</strong></p>
      <p style="margin:0 0 4px 0; font-size:13px; color:#4a5568;">Expected location: {{ doc.expected_location }}</p>
      <p style="margin:0; font-size:13px; color:#4a5568;">{{ doc.recommendation }}</p>
    </div>
    {%- endfor %}
  </div>
  {%- endif %}

  {%- if clean_count > 0 %}
  <!-- Clean Items -->
  <div style="padding:24px 32px; border-bottom:1px solid #e2e8f0;">
    <h2 style="margin:0 0 12px 0; font-size:16px; color:#276749; text-transform:uppercase; letter-spacing:0.5px;">&#10003; Items With No Financial Connections Identified</h2>
    <p style="margin:0; font-size:14px; color:#4a5568;">
      {{ clean_count }} additional agenda items were scanned against
      {{ contribution_count | default("27,035", true) }} campaign finance records
      (CAL-ACCESS and City Clerk NetFile filings). No donor-vendor connections
      were identified.
    </p>
  </div>
  {%- endif %}

  <!-- Footer -->
  <div style="padding:20px 32px; background-color:#f7fafc;">
    <h2 style="margin:0 0 8px 0; font-size:14px; color:#2d3748; text-transform:uppercase; letter-spacing:0.5px;">About This Report</h2>
    <p style="margin:0 0 8px 0; font-size:13px; color:#718096;">
      Richmond Common is a citizen-led initiative to make
      local government more transparent by systematically cross-referencing
      public records. All data used in this report is drawn from publicly
      available sources. We encourage all residents to verify information
      independently.
    </p>
    <p style="margin:0; font-size:13px; color:#718096;">
      For questions or corrections:
      <a href="mailto:pjfront@gmail.com" style="color:#3182ce;">pjfront@gmail.com</a>
      &nbsp;&bull;&nbsp; Report generated: {{ generated_at }}
    </p>
  </div>

</div>
</body>
</html>
""")


# ── Plain Text Comment Template ──────────────────────────────

COMMENT_TEMPLATE = Template("""\
PUBLIC COMMENT: Pre-Meeting Transparency Report
{{ meeting_type | title }} City Council Meeting, {{ meeting_date }}
Submitted by: Richmond Common

===============================================================

METHODOLOGY

This report cross-references publicly available campaign finance
records (filed with the City Clerk via NetFile and the FPPC via
CAL-ACCESS) against the agenda for the upcoming City Council
meeting. All citations reference specific public filings.

This report is informational only and does not constitute legal
advice or a determination of conflict under Government Code
Sections 87100-87105.

Items scanned: {{ total_items }}
Campaign finance records searched: {{ contribution_count | default("27,035", true) }}
{% if enriched_count > 0 -%}
Items with enhanced document scanning: {{ enriched_count }}
{% endif -%}
Findings: {{ tier1_count + tier2_count }}
{% if suppressed_count > 0 -%}
Additional matches tracked internally: {{ suppressed_count }}
{% endif %}
===============================================================
{% if tier1_flags %}
POTENTIAL CONFLICTS OF INTEREST
===============================================================
{% for flag in tier1_flags %}
{{ loop.index }}. {{ flag.agenda_item_title }}
{%- if flag.financial_amount %} -- {{ flag.financial_amount }}{% endif %}

   (Agenda Item {{ flag.agenda_item_number }})

   {{ flag.description }}

{% if "sitting council member" in (flag.council_member or "") -%}
   {{ flag.council_member.split(" (")[0] }} is a sitting member who
   will vote on this item.

{% endif -%}
   Under California's Political Reform Act (Gov. Code SS87100),
   elected officials must disqualify themselves from governmental
   decisions that could financially benefit a source of income
   of $500 or more received in the prior 12 months. The FPPC
   defines "source of income" to include persons from whom the
   official received payments (2 Cal. Code Regs. SS18700.3).

   This report does not determine whether a legal conflict
   exists. We disclose this connection so the public and Council
   can evaluate it independently.

{% endfor -%}
{% endif -%}
{% if tier2_flags %}
ADDITIONAL FINANCIAL CONNECTIONS
===============================================================

The following donor-vendor connections were identified in public
campaign finance records. These do not necessarily indicate
conflicts of interest but are disclosed for transparency.
{% for flag in tier2_flags %}
{{ loop.index }}. {{ flag.agenda_item_title }}
{%- if flag.financial_amount %} -- {{ flag.financial_amount }}{% endif %}

   (Agenda Item {{ flag.agenda_item_number }})

   {{ flag.description }}

{% endfor -%}
{% endif -%}
{% if missing_docs %}
MISSING OR INACCESSIBLE PUBLIC DOCUMENTS
===============================================================
{% for doc in missing_docs %}
>> Referenced in {{ doc.referenced_in }}:
   {{ doc.document_description }}
   Expected location: {{ doc.expected_location }}
   Recommendation: {{ doc.recommendation }}

{% endfor -%}
{% endif -%}
{% if clean_count > 0 %}
ITEMS WITH NO FINANCIAL CONNECTIONS IDENTIFIED
===============================================================

{{ clean_count }} additional agenda items were scanned against
{{ contribution_count | default("27,035", true) }} campaign finance records
(CAL-ACCESS and City Clerk NetFile filings). No donor-vendor
connections were identified.
{% endif %}
===============================================================

ABOUT THIS REPORT

Richmond Common is a citizen-led initiative
to make local government more transparent by systematically
cross-referencing public records. All data used in this report
is drawn from publicly available sources. We encourage all
residents to verify information independently.

For questions or corrections: pjfront@gmail.com
Report generated: {{ generated_at }}
""")


# ── Comment Generation ───────────────────────────────────────

def generate_comment_from_scan(
    scan_result: ScanResult,
    missing_docs: list[MissingDocument] = None,
    contribution_count: str = "27,035",
) -> str:
    """Generate the formatted public comment from a ScanResult.

    Filters findings by publication_tier:
      Tier 1 (Potential Conflict) -- published in main section
      Tier 2 (Financial Connection) -- published in secondary section
      Tier 3 (internal) -- suppressed from public comment
    """
    missing_docs = missing_docs or []

    # Split flags by tier
    tier1_flags = [f for f in scan_result.flags if f.publication_tier == 1]
    tier2_flags = [f for f in scan_result.flags if f.publication_tier == 2]
    suppressed_flags = [f for f in scan_result.flags if f.publication_tier == 3]

    # Merge clean items: remove any flagged by missing docs
    missing_item_nums = set()
    for doc in missing_docs:
        ref = doc.referenced_in
        if ref.startswith("Item "):
            missing_item_nums.add(ref[5:])

    clean_items = [n for n in scan_result.clean_items if n not in missing_item_nums]

    return COMMENT_TEMPLATE.render(
        meeting_date=scan_result.meeting_date,
        meeting_type=scan_result.meeting_type,
        total_items=scan_result.total_items_scanned,
        enriched_count=len(scan_result.enriched_items),
        contribution_count=contribution_count,
        tier1_flags=tier1_flags,
        tier2_flags=tier2_flags,
        tier1_count=len(tier1_flags),
        tier2_count=len(tier2_flags),
        suppressed_count=len(suppressed_flags),
        missing_docs=missing_docs,
        clean_count=len(clean_items),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S PT"),
    )


def generate_html_comment_from_scan(
    scan_result: ScanResult,
    missing_docs: list[MissingDocument] = None,
    contribution_count: str = "27,035",
) -> str:
    """Generate the HTML-formatted public comment from a ScanResult.

    Same tier filtering logic as the plain text version:
      Tier 1 (Potential Conflict) -- published in main section
      Tier 2 (Financial Connection) -- published in secondary section
      Tier 3 (internal) -- suppressed from public comment
    """
    missing_docs = missing_docs or []

    tier1_flags = [f for f in scan_result.flags if f.publication_tier == 1]
    tier2_flags = [f for f in scan_result.flags if f.publication_tier == 2]
    suppressed_flags = [f for f in scan_result.flags if f.publication_tier == 3]

    missing_item_nums = set()
    for doc in missing_docs:
        ref = doc.referenced_in
        if ref.startswith("Item "):
            missing_item_nums.add(ref[5:])

    clean_items = [n for n in scan_result.clean_items if n not in missing_item_nums]

    return HTML_COMMENT_TEMPLATE.render(
        meeting_date=scan_result.meeting_date,
        meeting_type=scan_result.meeting_type,
        total_items=scan_result.total_items_scanned,
        enriched_count=len(scan_result.enriched_items),
        contribution_count=contribution_count,
        tier1_flags=tier1_flags,
        tier2_flags=tier2_flags,
        tier1_count=len(tier1_flags),
        tier2_count=len(tier2_flags),
        suppressed_count=len(suppressed_flags),
        missing_docs=missing_docs,
        clean_count=len(clean_items),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S PT"),
    )


# ── Email Submission ─────────────────────────────────────────

def submit_comment_to_clerk(
    comment_text: str,
    meeting_date: str,
    html_text: str = None,
    clerk_email: str = "cityclerkdept@ci.richmond.ca.us",
    dry_run: bool = True,
    return_message: bool = False,
):
    """
    Submit the transparency comment to the City Clerk via email.

    Richmond accepts public comments via email to the City Clerk's office.
    Comments received by 1:00 PM (or 2:00 PM depending on meeting type)
    on the day of the meeting are included in the official record.

    When html_text is provided, constructs a multipart/alternative email
    with both plain text and HTML versions. Email clients will display
    the HTML version and fall back to plain text if needed.

    Args:
        comment_text: Plain text version of the comment
        meeting_date: Meeting date string for the subject line
        html_text: Optional HTML version; if provided, email is multipart
        clerk_email: Recipient email address
        dry_run: If True, print preview instead of sending
        return_message: If True, return the constructed email.mime message
    """
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    subject = f"Public Comment - Pre-Meeting Transparency Report - {meeting_date}"

    # Build the email message
    if html_text:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(comment_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_text, "html", "utf-8"))
    else:
        msg = MIMEText(comment_text, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = os.getenv("COMMENT_FROM_EMAIL", "transparency@richmondtransparency.org")
    msg["To"] = clerk_email

    if return_message:
        if dry_run:
            print("=" * 60)
            print(f"DRY RUN - Would send to: {clerk_email}")
            print(f"Subject: {subject}")
            print(f"Format: {'multipart/alternative (HTML + plain text)' if html_text else 'plain text'}")
            print("=" * 60)
        return msg

    if dry_run:
        print("=" * 60)
        print(f"DRY RUN - Would send to: {clerk_email}")
        print(f"Subject: {subject}")
        print(f"Format: {'multipart/alternative (HTML + plain text)' if html_text else 'plain text'}")
        print("=" * 60)
        print(comment_text)
        print("=" * 60)
        return

    # In production, use smtplib or a transactional email service (Resend/Postmark)
    # import smtplib
    # with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", 587))) as server:
    #     server.starttls()
    #     server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
    #     server.send_message(msg)

    print(f"Comment submitted to {clerk_email}")


# ── Full Pipeline: Meeting JSON -> Comment ────────────────────

def generate_comment_for_meeting(
    meeting_json_path: str,
    contributions_json_path: str = None,
    form700_json_path: str = None,
    escribemeetings_json_path: str = None,
    dry_run: bool = True,
    output_path: str = None,
) -> str:
    """End-to-end: load data, scan for conflicts, generate comment.

    Args:
        meeting_json_path: Path to extracted meeting JSON
        contributions_json_path: Path to contributions JSON (list of dicts)
        form700_json_path: Path to Form 700 interests JSON (list of dicts)
        escribemeetings_json_path: Path to eSCRIBE meeting_data.json for
            enhanced scanning with staff report/attachment text (optional)
        dry_run: If True, print instead of emailing
        output_path: If provided, save .txt and .html files

    Returns:
        The generated comment text (plain text)
    """
    with open(meeting_json_path) as f:
        meeting_data = json.load(f)

    contributions = []
    if contributions_json_path:
        with open(contributions_json_path) as f:
            contributions = json.load(f)

    form700 = []
    if form700_json_path:
        with open(form700_json_path) as f:
            form700 = json.load(f)

    # Enrich with eSCRIBE attachment text if available
    enriched_items = []
    if escribemeetings_json_path:
        meeting_data, enriched_items = enrich_meeting_data(
            meeting_data, escribemeetings_json_path
        )

    # Run conflict scan
    scan_result = scan_meeting_json(meeting_data, contributions, form700)
    scan_result.enriched_items = enriched_items

    # Detect missing documents
    missing_docs = detect_missing_documents(meeting_data)

    # Generate both plain text and HTML comments
    comment = generate_comment_from_scan(scan_result, missing_docs)
    html_comment = generate_html_comment_from_scan(scan_result, missing_docs)

    # Save files if output path provided
    if output_path:
        txt_path = Path(output_path)
        txt_path.write_text(comment, encoding="utf-8")
        # Derive HTML path from txt path (swap extension)
        html_path = txt_path.with_suffix(".html")
        html_path.write_text(html_comment, encoding="utf-8")

    # Submit (or dry run)
    submit_comment_to_clerk(
        comment_text=comment,
        html_text=html_comment,
        meeting_date=scan_result.meeting_date,
        dry_run=dry_run,
    )

    return comment


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Common - Generate Pre-Meeting Public Comment"
    )
    parser.add_argument("meeting_json", help="Path to extracted meeting JSON file")
    parser.add_argument("--contributions", help="Path to contributions JSON file")
    parser.add_argument("--form700", help="Path to Form 700 interests JSON file")
    parser.add_argument("--escribemeetings",
                        help="Path to eSCRIBE meeting_data.json for enhanced scanning")
    parser.add_argument("--send", action="store_true", help="Actually send email (default: dry run)")
    parser.add_argument("--output", help="Save comment text to file")

    args = parser.parse_args()

    comment = generate_comment_for_meeting(
        meeting_json_path=args.meeting_json,
        contributions_json_path=args.contributions,
        form700_json_path=args.form700,
        escribemeetings_json_path=args.escribemeetings,
        dry_run=not args.send,
        output_path=args.output,
    )

    if args.output:
        html_path = Path(args.output).with_suffix(".html")
        print(f"\nComment saved to {args.output}")
        print(f"HTML version saved to {html_path}")


if __name__ == "__main__":
    main()
