# Community Comment Submission — Feature Spec

_Residents discuss agenda items on Richmond Commons. Discussions are batch-submitted to the City Clerk as part of the public record before meeting deadlines._

**Status:** Spec (reference implementation exists on branch `claude/community-comments-submission-khmuM`)
**Publication tier:** Graduated (operator review before public launch)
**Date:** 2026-03-28

---

## Problem

Public comment at Richmond City Council meetings requires showing up at 6:30 PM on a Tuesday or figuring out how to email the clerk before the deadline. The information asymmetry is massive — most residents don't know what's on the agenda, don't know the deadline, and wouldn't know where to submit even if they did.

Meanwhile, organized interests (developers, unions, corporate lobbyists) submit comments routinely. The barrier isn't interest — it's friction.

## Proposal

Add threaded community discussions to agenda items on Richmond Commons. Comments are collected on the platform, displayed as a public discussion, and batch-submitted to the City Clerk before the meeting deadline as part of the official public record.

Think of it as submitting a structured community forum thread into the record — not individual emails, but a packaged community discussion.

## What Makes This Different

Every comment platform lets people talk. This one **puts their words into the democratic process**. The clerk submission pipeline is the feature, not the comment box.

---

## Open Decisions (Judgment Calls)

These must be resolved before shipping. Each is a human decision.

### 1. Disclosure & Consent Language

What do commenters agree to when they post? The current prototype says:

> "Comments are submitted to the Richmond City Clerk before the meeting. By commenting, you agree to have your name and comment included in the public record."

Questions:
- Is this sufficient informed consent?
- Should it be a checkbox or is posting implied consent?
- Do we need a separate terms/policy page?

### 2. Clerk Submission Format

What does the email to the clerk actually look like? Proposed format:

> Subject: Community Discussion — [Agenda Item Title] — [Meeting Date]
>
> The following community discussion on [item title] took place on Richmond Commons (richmondcommons.org) between [first comment date] and [submission date]. [N] residents participated.
>
> Comments are reproduced below with attribution. Each commenter consented to inclusion in the public record.
>
> ---
> [Comment 1: Author Name — Date]
> [Comment text]
>
>   [Reply 1.1: Author Name — Date]
>   [Reply text]
>
> [Comment 2: Author Name — Date]
> [Comment text]
> ---
>
> Submitted by Richmond Commons (hello@richmondcommons.org)
> richmondcommons.org — Making Richmond's public decisions accessible

Questions:
- Plain text only, or HTML version too?
- Does the clerk need a specific format or subject line convention?
- Should we include comment count and participant count in the subject line?
- One email per agenda item, or one email per meeting with all items?

### 3. Identity Requirements

Current prototype requires name only, email optional. Options:

| Level | What's required | Trade-off |
|-------|----------------|-----------|
| **Minimal** | Display name only | Highest participation, lowest verification, astroturf risk |
| **Email verified** | Name + verified email | Moderate friction, prevents pure spam, email not displayed |
| **Resident signal** | Name + email + optional address/zip | Strongest signal, highest friction, Richmond-relevant filtering |

Recommendation: Start with **email verified** — name displayed publicly, email stored for clerk submission records but not shown. Email verification via magic link or one-time code.

### 4. Moderation Policy

What gets filtered before submission to the clerk?

Proposed minimum:
- No threats of violence
- No hate speech / slurs
- No doxxing (personal addresses, phone numbers of private individuals)
- No spam / commercial solicitation

What does NOT get filtered:
- Strong opinions, even angry ones
- Criticism of officials (they're public figures)
- Factual inaccuracies (not our job to fact-check community discussion)

Implementation options:
- **Post-publish moderation** (current prototype): comments appear immediately, flagged content removed by operator
- **Pre-publish moderation**: operator reviews before display (kills discussion momentum)
- **Automated + manual**: basic keyword filter on submit, operator review queue for flagged content

Recommendation: Post-publish with automated flagging. Discussion momentum matters more than pre-screening.

### 5. City Relationship

This is the biggest question. Richmond Commons currently has a collaborative relationship with city government. Comment submission changes the dynamic.

Options:
- **Heads-up first**: Contact the clerk's office, explain the feature, ask about preferred format. Collaborative approach.
- **Just do it**: Public comment submission is a legal right. No permission needed.
- **Pilot with the clerk**: Offer to do a test run on one meeting, get feedback on format.

Recommendation: **Pilot with the clerk**. Send a sample formatted submission for one past meeting (dry run), ask for feedback. This is the collaborative stance the project is built on.

---

## Technical Design

### What's Already Built (Reference Implementation)

The branch `claude/community-comments-submission-khmuM` contains:

**Database (migration 068):**
- `community_comments` — threaded comments with author name/email, status tracking, clerk batch reference
- `clerk_submission_batches` — tracks when comments were packaged and sent, method, status
- RLS: anonymous INSERT + SELECT (published only), service_role full access

**API:**
- `POST /api/community-comments` — rate limited (10/hr/IP, 30/session), validates input, verifies agenda item exists, hashes IP
- Session cookie for cross-request rate limiting

**Frontend:**
- `CommunityCommentSection` — comment form (name, optional email, text), threaded reply display, deadline-aware open/closed state, optimistic UI updates, clerk submission badges

**Integration:**
- Renders on agenda item detail pages below existing public comments section

### What's Not Built Yet

1. **Email verification flow** — if we go with email-verified identity (Decision 3)
2. **Clerk submission pipeline** — batch assembly, formatting, SMTP send (skeleton exists in `src/comment_generator.py` with `submit_comment_to_clerk()`)
3. **Deadline awareness** — query meeting dates, compute submission windows, trigger batch send
4. **Moderation tooling** — flagging UI, operator review queue
5. **Comment count on item cards** — show community comment count alongside existing public comment count on meeting pages

### Existing Infrastructure to Build On

- `src/comment_generator.py` already has `submit_comment_to_clerk()` with SMTP skeleton and `cityclerkdept@ci.richmond.ca.us`
- `cities.clerk_email` field in database (multi-city ready)
- Feedback API (`/api/feedback`) provides the pattern for rate limiting, session tracking, RLS
- `OperatorGate` component for graduated feature gating

### Submission Pipeline (Proposed)

```
community_comments (database)
  → batch assembly (group by agenda_item_id, filter by meeting deadline)
  → format as plain text email (one per item with threads)
  → operator review (dashboard showing pending batches)
  → submit to clerk via SMTP
  → mark comments as submitted_to_clerk = true
  → record in clerk_submission_batches
```

Trigger: Scheduled job runs daily, checks for meetings in next 48 hours with unsubmitted comments. Operator gets a notification with the formatted batch for review. One-click approve sends to clerk.

---

## Phasing

### Phase 1: Community Discussion (ship first)
- Comment form on agenda items for upcoming meetings
- Threaded replies
- Deadline display ("Comments close [date]")
- Operator reviews discussions via direct database/admin
- Manual submission to clerk (operator copies formatted text)
- Behind OperatorGate initially

### Phase 2: Automated Submission
- Batch assembly pipeline
- Operator review dashboard
- One-click approve → SMTP send to clerk
- Submission confirmation badges on comments
- Email verification for commenters

### Phase 3: Scale
- Notification when items you commented on are voted on
- "Your comment was submitted" email confirmation
- Comment activity on homepage ("Most discussed this week")
- Cross-meeting discussion threads for recurring topics

---

## Success Metrics

- Comments submitted per meeting (target: >0 within first month)
- Unique commenters per month
- Reply rate (threaded discussion vs. standalone comments)
- Clerk confirmation of receipt
- Zero moderation incidents in first 3 months

---

## References

- Reference implementation: branch `claude/community-comments-submission-khmuM`
- Existing clerk submission code: `src/comment_generator.py` lines 444-517
- Clerk email: `cityclerkdept@ci.richmond.ca.us`
- Contact email: `hello@richmondcommons.org`
- Judgment boundary: comment template framing is a judgment call (see `docs/audits/2026-Q1-judgment-boundary-audit.md`)
