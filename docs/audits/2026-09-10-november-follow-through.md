# November money trails and story follow-through

This release continues the accepted Richmond, California resident work on top of the September 6–9 numeric-integrity release. It adds source-backed starting points and removes two newly discovered accounting ambiguities. It does not add rankings, inferred election cycles, campaign totals from transaction rows, a new service, a migration, a model call, or an email send.

## Resident changes

The money page always links to the two dated mayoral campaign summaries. Two reviewed organization reports provide starting points for Safe Richmond Neighborhoods and East Bay Working Families. Each sponsor claim links to its exact original page and stays dated to that report. A sponsor, donor, recipient and spender are different relationships; names and common addresses do not establish ownership or control.

One cash-contribution filter includes both recipient and contributor reports. Committee direction is filtered independently because a matched outgoing report can become a canonical receipt event. Search, committee, activity and direction use one shared interpretation for the page, pagination and CSV. The native form resets to the URL state on client navigation so its controls cannot disagree with the displayed records. Loans, noncash values, signed adjustments and outside spending retain their separate meanings.

Source coverage is readable by form, with checked dates, search windows and pending source-entry counts. Those counts explicitly cover the whole Richmond index, across all filters. Failed reads remain unavailable, and a truncated acquisition cannot produce a complete CSV. No filtered row sum is presented as fundraising or spending.

The three existing stories separate the earliest matching upcoming meeting from the recent agenda trail. A direct jump link helps mobile readers reach the next step. Official agendas supply time and participation details; matching titles do not prove outcomes. The existing bounded source query and cache are unchanged. Missing, unavailable and clipped coverage remain distinct. New story explanations are also available in Spanish.

## Evidence and routine operation

See [the finance source-conflict audit](../research/2026-09-10-finance-source-conflicts.md) for the exact original records. Schedule H now supplies reported loans made. Four matching receipt/transfer claims for the May 29 RPOA payment wait for interpretation alongside the lender's source. Two EBWF mailer claims in distinct reports wait for comparison. Original assertion values and source versions remain intact; neither conflict is silently resolved by deduplication.

The existing review producer packages both groups for a judgment. The official `pub-richmond.escribemeetings.com` agenda host is now accepted by the same story-packet producer. No new review system is introduced.

The existing paper-finance command also watches the two source-pinned organization reports. It checks exact identities and metadata daily, rechecks unchanged PDFs weekly, and queues changed evidence with the old claims and original links. It uses no sponsor extraction, OCR or model for those reports. A reviewed JSON change and release publish a revised explanation. Rejected unchanged source versions stay suppressed. See [the source-review runbook](../paper-finance-review.md) for byte, request, source and judgment bounds.

## Verification and release boundary

Meaningful regressions cover reporting direction, paired sources, real amendment/repetition examples, immutable evidence, source-wide coverage, matching exports, client-navigation filter state, source identity/hash changes, queue rejection/approval and failed reads. Isolated PostgreSQL proofs execute the real finance batch and private packet writers. Browser checks cover mobile/desktop money views, sponsor source links, direction/activity navigation and the story jump/Spanish controls. The local production build uses the existing two-worker bound and actual public data access.

The release evidence must separately attest the deployed source and the finance data repair. The bounded repair retains old assertion hashes and verifies protected legacy finance, subscriber and publication rows before commit; it only rebuilds the existing current-year source projection and creates the two private source-comparison decisions. Existing source schedules own later refreshes. No migration is required; migration 134 remains prohibited. Paid preview databases remain disabled. Email activation remains separately held on the existing canary verification.
