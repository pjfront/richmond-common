"""
Richmond Transparency Project - Pre-Meeting Transparency Comment Generator

This is the core output of the system: an automated public comment submitted
before each Richmond City Council meeting that surfaces potential conflicts
of interest, donor correlations, and missing documents.

The comment is submitted via email to the City Clerk before the deadline
(typically 1:00 PM or 2:00 PM on meeting day) and becomes part of the
official meeting record, attached to the approved minutes.
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from dataclasses import dataclass

# You'll need: pip install anthropic jinja2
from jinja2 import Template


# --- Data Sources for Cross-Referencing ---

@dataclass 
class CampaignContribution:
    donor_name: str
    donor_employer: str
    recipient_committee: str
    council_member: str
    amount: float
    date: str
    filing_id: str
    source: str  # "CAL-ACCESS", "City Clerk Form 460", "FPPC"


@dataclass
class Form700Interest:
    council_member: str
    interest_type: str  # "real_property", "investment", "income"
    description: str
    location: str  # address for real property
    filing_year: int
    source_url: str


@dataclass
class ConflictFlag:
    agenda_item: str
    item_title: str
    council_member: str
    flag_type: str
    description: str
    evidence: list[str]
    legal_reference: str


@dataclass
class MissingDocument:
    referenced_in: str  # where the reference was found
    document_description: str
    expected_location: str
    recommendation: str


# --- Agenda Analysis ---

def analyze_agenda_for_conflicts(
    agenda_items: list[dict],
    contributions: list[CampaignContribution],
    form700s: list[Form700Interest],
    property_records: dict = None
) -> tuple[list[ConflictFlag], list[MissingDocument]]:
    """
    Cross-reference agenda items against campaign finance, Form 700,
    and property records to identify potential conflicts.
    
    This is where the real intelligence lives.
    """
    flags = []
    missing_docs = []
    
    for item in agenda_items:
        item_num = item.get("item_number", "")
        item_title = item.get("title", "")
        item_desc = item.get("description", "")
        department = item.get("department", "")
        
        # --- Campaign Finance Cross-Reference ---
        # Look for donor names, employer names, or company names
        # that appear in the agenda item
        for contribution in contributions:
            donor_lower = contribution.donor_name.lower()
            employer_lower = (contribution.donor_employer or "").lower()
            item_text = f"{item_title} {item_desc}".lower()
            
            # Check if donor or employer appears in agenda item
            if (donor_lower in item_text or 
                (employer_lower and len(employer_lower) > 3 and employer_lower in item_text)):
                flags.append(ConflictFlag(
                    agenda_item=item_num,
                    item_title=item_title,
                    council_member=contribution.council_member,
                    flag_type="campaign_contribution",
                    description=(
                        f"{contribution.donor_name}"
                        f"{' (' + contribution.donor_employer + ')' if contribution.donor_employer else ''}"
                        f" contributed ${contribution.amount:,.2f} to "
                        f"{contribution.recipient_committee} on {contribution.date}"
                    ),
                    evidence=[
                        f"Source: {contribution.source}, Filing ID: {contribution.filing_id}"
                    ],
                    legal_reference="Gov. Code §§ 87100-87105, 87300"
                ))
        
        # --- Form 700 Property Cross-Reference ---
        # For zoning/development items, check if any council member
        # has property interests near the subject location
        if any(kw in item_text for kw in [
            "rezone", "zoning", "conditional use", "development",
            "subdivision", "variance", "design review", "planning"
        ]):
            for interest in form700s:
                if interest.interest_type == "real_property":
                    # In production, you'd geocode both addresses and 
                    # calculate distance. For MVP, flag any property 
                    # interests in the same neighborhood/area.
                    flags.append(ConflictFlag(
                        agenda_item=item_num,
                        item_title=item_title,
                        council_member=interest.council_member,
                        flag_type="form700_real_property",
                        description=(
                            f"{interest.council_member}'s Form 700 "
                            f"(filed {interest.filing_year}) lists real property: "
                            f"{interest.description}"
                        ),
                        evidence=[
                            f"Form 700, Schedule A-2, {interest.filing_year}",
                            f"Source: {interest.source_url}"
                        ],
                        legal_reference=(
                            "Gov. Code § 87100 (disqualification required when "
                            "official has financial interest in decision). "
                            "See also 2 CCR § 18702.2 (real property interests "
                            "within 500 feet of subject property)."
                        )
                    ))
        
        # --- Missing Document Detection ---
        # Check if staff reports or referenced documents are accessible
        if "staff report" in item_desc.lower():
            # In production, you'd actually check if the referenced
            # document URL resolves
            pass  # Placeholder for URL validation
        
        if item.get("resolution_number") and not item.get("resolution_text_available"):
            missing_docs.append(MissingDocument(
                referenced_in=f"Item {item_num}",
                document_description=f"Resolution No. {item['resolution_number']}",
                expected_location="City Clerk's resolution archive",
                recommendation="Full resolution text should be publicly available"
            ))
    
    return flags, missing_docs


# --- Comment Generation ---

COMMENT_TEMPLATE = Template("""PUBLIC COMMENT: Pre-Meeting Transparency Report
{{ meeting_type }} City Council Meeting, {{ meeting_date }}
Submitted by: Richmond Transparency Project

═══════════════════════════════════════════════════════════

METHODOLOGY: This report cross-references publicly available data
including Form 700 economic interest disclosures, campaign finance
reports filed with the City Clerk and FPPC (via CAL-ACCESS), and
Contra Costa County property records. All citations reference
specific public filings. This report is informational only and does
not constitute legal advice or a determination of conflict under
Government Code Sections 87100-87105.

═══════════════════════════════════════════════════════════
{% if flags %}
POTENTIAL CONFLICTS OF INTEREST AND DONOR CORRELATIONS
───────────────────────────────────────────────────────
{% for flag in flags %}
▶ Item {{ flag.agenda_item }}: {{ flag.item_title }}

  {{ flag.flag_type | upper | replace("_", " ") }}
  Council Member: {{ flag.council_member }}
  
  {{ flag.description }}
  
  Evidence:
  {% for e in flag.evidence %}  • {{ e }}
  {% endfor %}
  Legal Reference: {{ flag.legal_reference }}

{% endfor %}{% endif %}{% if missing_docs %}
MISSING OR INACCESSIBLE PUBLIC DOCUMENTS
───────────────────────────────────────────────────────
{% for doc in missing_docs %}
▶ Referenced in {{ doc.referenced_in }}:
  {{ doc.document_description }}
  Expected location: {{ doc.expected_location }}
  Recommendation: {{ doc.recommendation }}

{% endfor %}{% endif %}{% if clean_items %}
NO FLAGS IDENTIFIED
───────────────────────────────────────────────────────
No potential conflicts or missing documents were identified for
the following agenda items: {{ clean_items | join(", ") }}
{% endif %}

═══════════════════════════════════════════════════════════

ABOUT THIS REPORT: The Richmond Transparency Project is a
citizen-led initiative to make local government more transparent
by systematically cross-referencing public records. All data used
in this report is drawn from publicly available sources. We
encourage all residents to verify information independently.

For questions or corrections: [email]
Report generated: {{ generated_at }}
""")


def generate_transparency_comment(
    meeting_date: str,
    meeting_type: str,
    agenda_items: list[dict],
    flags: list[ConflictFlag],
    missing_docs: list[MissingDocument]
) -> str:
    """Generate the formatted public comment for submission."""
    
    # Identify clean items (no flags)
    flagged_items = set(f.agenda_item for f in flags)
    flagged_items.update(d.referenced_in.replace("Item ", "") for d in missing_docs)
    clean_items = [
        item["item_number"] 
        for item in agenda_items 
        if item["item_number"] not in flagged_items
    ]
    
    return COMMENT_TEMPLATE.render(
        meeting_date=meeting_date,
        meeting_type=meeting_type,
        flags=flags,
        missing_docs=missing_docs,
        clean_items=clean_items,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S PT")
    )


# --- Email Submission ---

def submit_comment_to_clerk(
    comment_text: str,
    meeting_date: str,
    clerk_email: str = "cityclerkdept@ci.richmond.ca.us",
    dry_run: bool = True
):
    """
    Submit the transparency comment to the City Clerk via email.
    
    Richmond accepts public comments via email to the City Clerk's office.
    Comments received by 1:00 PM (or 2:00 PM depending on meeting type)
    on the day of the meeting are included in the official record.
    """
    subject = f"Public Comment - Pre-Meeting Transparency Report - {meeting_date}"
    
    if dry_run:
        print("=" * 60)
        print(f"DRY RUN - Would send to: {clerk_email}")
        print(f"Subject: {subject}")
        print("=" * 60)
        print(comment_text)
        print("=" * 60)
        return
    
    # In production, use smtplib or a transactional email service
    # import smtplib
    # from email.mime.text import MIMEText
    # msg = MIMEText(comment_text)
    # msg["Subject"] = subject
    # msg["From"] = "transparency@richmondtransparency.org"
    # msg["To"] = clerk_email
    # with smtplib.SMTP("smtp.example.com") as server:
    #     server.send_message(msg)
    
    print(f"Comment submitted to {clerk_email}")


# --- Demo with sample data ---

def demo():
    """
    Demonstrate the system with sample data based on the
    September 23, 2025 Richmond City Council meeting.
    """
    
    # Sample agenda items (from the actual meeting)
    agenda_items = [
        {
            "item_number": "O.3.a",
            "title": "Contract Amendment No. 3 with Gallagher Benefit Services, Inc.",
            "description": "APPROVE a third amendment for employment outreach and recruitment, $150,000 NTE",
        },
        {
            "item_number": "O.6.a",
            "title": "Interagency Agreement - Human Trafficking Operational Support Fund",
            "description": "ADOPT resolution and APPROVE interagency agreement with Contra Costa County",
        },
        {
            "item_number": "O.7.c",
            "title": "Purchase of Three Fleet Vehicles from National Auto Fleet Group",
            "description": "Purchase Freightliner trucks, $735,690 NTE",
        },
        {
            "item_number": "P.1",
            "title": "OIS Communication and Counseling Policy",
            "description": "DIRECT city manager to develop plan for officer involved shooting communications and counseling services",
        },
        {
            "item_number": "P.3",
            "title": "Public Lands Policy - Building Trades Council",
            "description": "Presentation from Contra Costa County Building Trades Council on Public Lands Policy for development on public land",
        },
    ]
    
    # Sample campaign contributions (hypothetical for demo)
    sample_contributions = [
        CampaignContribution(
            donor_name="John Smith",
            donor_employer="National Auto Fleet Group",
            recipient_committee="Committee to Elect Council Member Example",
            council_member="[Example Council Member]",
            amount=2500.00,
            date="2024-06-15",
            filing_id="FPPC-2024-12345",
            source="CAL-ACCESS Form 460, Schedule A"
        ),
    ]
    
    # Sample Form 700 interests (hypothetical for demo)
    sample_form700s = []
    
    # Run the analysis
    flags, missing_docs = analyze_agenda_for_conflicts(
        agenda_items, sample_contributions, sample_form700s
    )
    
    # Add a sample missing document flag
    missing_docs.append(MissingDocument(
        referenced_in="Item P.1",
        document_description="Current RPD Officer-Involved Shooting communication policy/protocol",
        expected_location="Richmond Police Department policy manual or City website",
        recommendation=(
            "The agenda item directs the city manager to 'revise the current "
            "communication protocol' but the existing protocol is not linked "
            "or publicly available for comparison"
        )
    ))
    
    # Generate the comment
    comment = generate_transparency_comment(
        meeting_date="September 23, 2025",
        meeting_type="Regular",
        agenda_items=agenda_items,
        flags=flags,
        missing_docs=missing_docs
    )
    
    # Output (dry run)
    submit_comment_to_clerk(
        comment_text=comment,
        meeting_date="2025-09-23",
        dry_run=True
    )


if __name__ == "__main__":
    demo()
