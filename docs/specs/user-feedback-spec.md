# User Feedback System Spec

*Created: 2026-02-20*
*Status: Draft — awaiting review before implementation*

---

## 1. Motivation

The conflict scanner and structured extraction pipeline are only as good as their data. Right now, quality assurance depends entirely on the developer manually reviewing output. This doesn't scale — and more importantly, it misses the people who know the most: **residents**.

A Richmond resident attending a council meeting knows things no algorithm can:
- "That vendor changed their name last year — your scanner missed the connection."
- "Council Member X recused themselves verbally but it's not in the minutes."
- "This vote was actually about the amendment, not the original motion."
- "The real conflict here isn't campaign donations — it's that council member's spouse works for the contractor."

Crowdsourced feedback turns passive readers into active data quality contributors. It also:

1. **Feeds the bias audit system.** The existing ground truth review process (see `bias-audit-spec.md`) requires labeled flags. User feedback provides labels at scale — no developer CLI session needed.
2. **Builds community trust.** When users see a "Report an error" button, they know the platform takes accuracy seriously.
3. **Creates accountability loops.** If users consistently flag a pattern the scanner misses, that's a signal to improve the matching logic.

### Monetization filter

- **Path A (Freemium):** Users who contribute feedback are more engaged. Feedback-driven accuracy improvements make the product better for everyone. — ✓
- **Path B (Horizontal):** Feedback schema is city-agnostic. Every city has residents who know things. — ✓
- **Path C (Data Infrastructure):** Structured corrections and tips create ground truth data that improves the scanner. — ✓

All three. High priority for data quality and community engagement.

---

## 2. Feedback Types

### 2.1 Flag Accuracy Feedback

The most targeted feedback type. Appears on every conflict flag displayed to the public.

**User actions:**
- **Confirm** — "This flag is correct. I can verify this connection."
- **Dispute** — "This flag is wrong. Here's why: [free text]"
- **Add context** — "This flag is directionally right, but here's additional context: [free text]"

**Maps to bias audit:** Confirm → `ground_truth: true`. Dispute → `ground_truth: false`. Add context → `ground_truth: null` (requires manual review).

### 2.2 Data Corrections

For errors in the structured data (votes, attendance, agenda items, officials).

**Examples:**
- Wrong vote recorded (aye vs. nay)
- Misspelled official name
- Wrong agenda item category
- Incorrect meeting date
- Wrong employer listed for a donor
- Missing attendance record

**Each correction includes:**
- Entity type (vote, official, agenda_item, contribution, meeting)
- Entity identifier (UUID or human-readable reference)
- Field being corrected
- Current value (auto-populated)
- Suggested correct value
- Source/evidence (optional — "I was at the meeting", "the minutes say X on page Y")

### 2.3 Tips & Leads

For information the scanner can't detect from public data alone.

**Examples:**
- "Council Member X's brother-in-law owns the company on agenda item H-4."
- "That consulting firm is a subsidiary of [larger company] which donated $50K."
- "There's a Form 700 amendment that hasn't been filed yet — I heard about it at the Planning Commission meeting."

**Tips are:**
- Free-form text with optional category tags
- Anonymous by default (no login required to submit)
- Reviewed by moderator before any action is taken
- Never published directly — only used as investigative leads

### 2.4 Missing Conflict Reports

When a user sees a connection the scanner missed.

**Structured fields:**
- Agenda item reference (meeting date + item number)
- Official involved
- Nature of conflict (contribution, property interest, business relationship, family tie, other)
- Description of the connection
- Evidence links (optional)

### 2.5 Document Submissions

Users can submit documents the pipeline is missing.

**Examples:**
- Scanned Form 700 that isn't available online
- Council member newsletter not yet in our system
- Historical minutes from pre-digital era
- News article covering a relevant topic

**Handled as:**
- Upload to Supabase Storage (with size/type limits)
- Queued for moderator review before ingestion
- Tagged with credibility tier upon review

### 2.6 General Feedback

Catch-all for UX issues, feature requests, and "the site is broken" reports. Not structured — just a text box with optional category.

---

## 3. Data Model

### 3.1 `user_feedback` Table

```sql
CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    feedback_type VARCHAR(30) NOT NULL,
        -- 'flag_accuracy', 'data_correction', 'tip', 'missing_conflict',
        -- 'document_submission', 'general'

    -- What the feedback is about (polymorphic reference)
    entity_type VARCHAR(50),            -- 'conflict_flag', 'vote', 'official', 'agenda_item', 'contribution', 'meeting'
    entity_id UUID,                      -- FK to the referenced entity

    -- Flag accuracy specific
    flag_verdict VARCHAR(20),            -- 'confirm', 'dispute', 'add_context' (for flag_accuracy type)

    -- Data correction specific
    field_name VARCHAR(100),             -- which field is wrong
    current_value TEXT,                  -- what the system currently shows
    suggested_value TEXT,                -- what the user thinks it should be

    -- Missing conflict specific
    conflict_nature VARCHAR(50),         -- 'contribution', 'property', 'business', 'family', 'other'
    official_name VARCHAR(200),          -- who the conflict involves

    -- Universal fields
    description TEXT,                    -- free-form explanation
    evidence_url TEXT,                   -- link to supporting evidence
    evidence_text TEXT,                  -- pasted text evidence

    -- Document submission
    document_storage_path TEXT,          -- Supabase Storage path if a file was uploaded
    document_filename VARCHAR(500),
    document_mime_type VARCHAR(100),

    -- Submitter info (anonymous by default)
    submitter_email VARCHAR(255),        -- optional, for follow-up
    submitter_name VARCHAR(200),         -- optional
    is_anonymous BOOLEAN NOT NULL DEFAULT TRUE,
    session_id VARCHAR(100),             -- browser session for spam detection, NOT for identity

    -- Moderation
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- 'pending', 'reviewing', 'accepted', 'rejected', 'duplicate', 'acted_on'
    moderator_notes TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(200),

    -- If this feedback resulted in a data change
    action_taken TEXT,                   -- 'flag_marked_false_positive', 'vote_corrected', 'tip_forwarded', etc.
    action_entity_id UUID,              -- FK to the entity that was modified

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_feedback_city ON user_feedback(city_fips);
CREATE INDEX idx_feedback_type ON user_feedback(feedback_type);
CREATE INDEX idx_feedback_entity ON user_feedback(entity_type, entity_id);
CREATE INDEX idx_feedback_status ON user_feedback(status);
CREATE INDEX idx_feedback_pending ON user_feedback(city_fips) WHERE status = 'pending';
CREATE INDEX idx_feedback_created ON user_feedback(created_at);
```

### 3.2 Feedback-to-Bias-Audit Bridge

When a `flag_accuracy` feedback has `flag_verdict = 'confirm'` or `'dispute'`, it can be mapped to the bias audit system:

```sql
-- View for feeding feedback into bias audit ground truth
CREATE VIEW v_feedback_ground_truth AS
SELECT
    uf.id AS feedback_id,
    uf.entity_id AS conflict_flag_id,
    cf.scan_run_id,
    CASE uf.flag_verdict
        WHEN 'confirm' THEN TRUE
        WHEN 'dispute' THEN FALSE
        ELSE NULL  -- 'add_context' requires manual review
    END AS ground_truth,
    'user_feedback' AS ground_truth_source,
    uf.description AS audit_notes,
    uf.created_at
FROM user_feedback uf
JOIN conflict_flags cf ON uf.entity_id = cf.id
WHERE uf.feedback_type = 'flag_accuracy'
  AND uf.status IN ('accepted', 'acted_on');
```

This view can be consumed by `bias_audit.py` alongside the existing CLI-labeled ground truth data.

---

## 4. UI Integration

### 4.1 Per-Flag Feedback (Transparency Report Pages)

On each displayed conflict flag, show inline action buttons:

```
┌─────────────────────────────────────────────────────┐
│ ⚠️ Potential Conflict — Agenda Item H-4             │
│                                                     │
│ Council Member X received $2,500 from Developer Y   │
│ (CAL-ACCESS filing 2024-Q3).                       │
│                                                     │
│ Confidence: High (0.85)                             │
│                                                     │
│   [✓ Correct]   [✗ Incorrect]   [💡 I know more]  │
└─────────────────────────────────────────────────────┘
```

- **[✓ Correct]** → Creates `flag_accuracy` feedback with `verdict = 'confirm'`. One click. Optional follow-up text.
- **[✗ Incorrect]** → Opens small form: "Why is this incorrect?" (required text). Creates `flag_accuracy` with `verdict = 'dispute'`.
- **[💡 I know more]** → Opens form: "What additional context can you provide?" Creates `flag_accuracy` with `verdict = 'add_context'`.

### 4.2 Per-Vote "Report an Error" Link

On each vote record in meeting detail and official profile pages:

```
Aye: Martinez, Willis, Jimenez, Bates    [Report an error]
Nay: Zepeda, Brown
Abstain: (none)
```

Clicking "Report an error" opens a small form:
- Which part is wrong? (dropdown: vote choice, official name, motion text, tally)
- What should it be? (text input)
- How do you know? (optional text — "I was at the meeting", "minutes page 12")

### 4.3 Per-Official "Suggest a correction"

On official profile pages, below contact/term info:

```
See something wrong? [Suggest a correction]
```

Opens form for correcting: name, role, term dates, party affiliation, contact info.

### 4.4 Global "Submit a Tip" Button

Persistent in the site footer or navbar. Opens a modal:

```
┌─────────────────────────────────────────────────────┐
│             Submit a Tip                            │
│                                                     │
│ What kind of feedback?                              │
│  ○ I spotted an error in the data                   │
│  ○ I know about a conflict of interest not shown    │
│  ○ I have a document to share                       │
│  ○ General feedback about the site                  │
│                                                     │
│ Tell us more:                                       │
│ ┌─────────────────────────────────────────────────┐ │
│ │                                                 │ │
│ │                                                 │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ Email (optional, for follow-up):                    │
│ ┌─────────────────────────────────────────────────┐ │
│ │                                                 │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ 🔒 Submissions are anonymous by default.            │
│                                                     │
│                           [Submit]   [Cancel]       │
└─────────────────────────────────────────────────────┘
```

### 4.5 Confirmation & Transparency

After submission, show:
- "Thank you! Your feedback has been received."
- A reference number (first 8 chars of UUID) for follow-up
- "We review all submissions. Corrections that are verified get applied within [X] days."

Do NOT show a public feed of all feedback. That invites spam and gaming. Feedback is reviewed internally.

---

## 5. Spam & Abuse Prevention

Since feedback is anonymous by default and no login is required, we need lightweight anti-abuse measures:

### 5.1 Rate Limiting
- Maximum 10 submissions per session (browser session ID tracked via cookie)
- Maximum 5 submissions per IP per hour
- Enforced at the API level (Supabase Edge Function or Next.js API route)

### 5.2 Content Validation
- Minimum 10 characters for description field
- Maximum 5,000 characters
- Document uploads limited to 10MB, allowed types: PDF, PNG, JPG, DOCX
- No executable file uploads

### 5.3 Automated Filtering
- Flag submissions with known spam patterns (URLs to unrelated sites, repeated text)
- Heuristic: if 3+ submissions from same session/IP in 5 minutes, mark all as `status = 'reviewing'` (auto-quarantine)

### 5.4 Moderation Queue
- All feedback starts as `status = 'pending'`
- Moderator dashboard (Phase 2 admin UI) shows pending items sorted by type and recency
- Until admin UI exists: weekly manual review via Supabase dashboard or SQL query

---

## 6. Implementation Plan

### Phase 1: Backend & Data Layer (Week 1)

1. **Schema migration:** Create `user_feedback` table and `v_feedback_ground_truth` view.
2. **API endpoint:** Next.js API route `POST /api/feedback` that validates and inserts feedback.
3. **Rate limiting:** Implement per-session and per-IP limits in the API route.
4. **Supabase RLS:** Row-level security — anyone can INSERT, only authenticated admin can SELECT/UPDATE.

### Phase 2: UI Components (Week 2)

5. **FeedbackButton component:** Reusable `[✓] [✗] [💡]` button group for conflict flags.
6. **ReportErrorLink component:** Inline "Report an error" for vote records.
7. **FeedbackModal component:** Global tip submission modal.
8. **Integrate into existing pages:**
   - Transparency report detail → FeedbackButton on each flag
   - Meeting detail → ReportErrorLink on each vote
   - Official profile → "Suggest a correction" link
   - Site footer → "Submit a Tip" link

### Phase 3: Bias Audit Integration (Week 3)

9. **Update `bias_audit.py`** to read from `v_feedback_ground_truth` view in addition to JSON sidecars.
10. **Feedback-to-flag linking:** Ensure `entity_id` correctly references `conflict_flags.id` for seamless joins.
11. **Acceptance workflow:** When moderator accepts a `flag_accuracy` feedback, auto-update `conflict_flags.false_positive` and `conflict_flags.reviewed` fields.

### Phase 4: Admin & Moderation (Week 4 — or deferred)

12. **Admin moderation page** (or SQL-based workflow until admin UI exists).
13. **Email notification** when new feedback arrives (optional — n8n could handle this).
14. **Weekly feedback summary** in pipeline reporting.

---

## 7. Privacy Considerations

- **No login required.** Feedback is anonymous by default. This lowers the barrier to participation and protects whistleblowers.
- **Email is optional.** If provided, used only for follow-up. Never displayed publicly. Never shared.
- **Session IDs are for spam detection only.** Not linked to user identity. No tracking across sessions.
- **No personal data in feedback about officials.** If a tip includes personal information about a private citizen (not an official), moderator removes it before acting on it.
- **CCPA/CPRA compliance.** If a user provides email, they can request deletion. Since most feedback is anonymous, there's nothing to delete.

---

## 8. What This Spec Does NOT Cover

- **Admin dashboard UI** — the moderation interface is its own feature. Initial moderation is manual (Supabase dashboard or SQL).
- **Gamification** — no points, badges, or leaderboards for feedback contributors. This invites gaming.
- **Public-facing feedback display** — feedback is internal. We don't show "3 users confirmed this flag" publicly (yet). Maybe in a future trust indicator feature.
- **Automated action** — no feedback is automatically acted upon. All changes require moderator review. This prevents coordinated abuse.
- **User accounts / authentication** — this spec assumes anonymous feedback. Authenticated feedback (with user accounts) is a future feature that would enable richer feedback workflows.

---

## 9. Success Metrics

- **Volume:** >10 feedback submissions per month within 3 months of launch.
- **Signal-to-noise:** >50% of submissions are actionable (not spam, not duplicate, contain useful information).
- **Ground truth contribution:** >30 flag_accuracy verdicts per quarter, feeding the bias audit system.
- **Correction rate:** >80% of accepted data corrections applied within 7 days.
- **Conversion:** At least 1 user tip leads to a scanner improvement within 6 months.

---

## 10. File Locations

| File | Purpose |
|------|---------|
| `web/src/app/api/feedback/route.ts` | Next.js API route for feedback submission |
| `web/src/components/FeedbackButton.tsx` | Per-flag [✓] [✗] [💡] button group |
| `web/src/components/ReportErrorLink.tsx` | Per-vote "Report an error" link |
| `web/src/components/FeedbackModal.tsx` | Global tip submission modal |
| `docs/specs/user-feedback-spec.md` | This spec |
