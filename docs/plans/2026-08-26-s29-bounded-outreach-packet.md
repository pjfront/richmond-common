# S29 bounded November outreach packet

**Prepared:** 2026-08-26

**Status:** Copy and protocol drafted; channel names and exact calendar dates
remain pending. Nothing in this packet authorizes an early treatment release,
paid promotion, or posting before the treatment window is fixed.

## Purpose

Use one identical, unpaid public launch message in no more than three
operator-controlled Richmond channels. This is a combined release-and-demand
observation. It is not a randomized experiment and cannot isolate the effect of
the front door, the message, a channel, election interest, or any other part of
the release.

The authoritative phase gates remain in
`docs/plans/2026-08-15-s29-analytics-baseline-release-runbook.md`. `A0` is still
pending. The baseline must finish and `B14` must be frozen before the visible
treatment or this outreach can begin.

The machine-readable copy and boundary contract is `docs/s29-outreach.json`.
CI rejects changes that add tracking, widen the channel or posting count, move
the post outside the fixed release slot, or detach this packet from the
authoritative runbook.

## Fixed public message

Post this text without edits, added hashtags, channel-specific introductions,
images, or link changes:

```text
Richmond Commons is ready for Richmond residents to try. It is a free, independent guide to city government in Richmond, California. See the November 3 mayor's race, follow City Council meetings and votes, find your council district, and sign up for meeting briefings. Plain-language explanations link to public records, and AI-generated explanations are clearly labeled.

Take a look:
https://richmondcommons.org/elections/2026-general

If something looks unclear or wrong, please use the Submit Feedback button.
```

The direct election link is the one measured November route. It does not
promise election alerts; the subscription offer remains meeting briefings.

## Fixed date protocol

The repository cannot truthfully name calendar dates yet: `A0`, baseline day
1, `B14`, and `T0` are still null and the resource gates can move them. Inventing
a calendar date now would conflict with the approved gate-driven release
contract.

The schedule itself is fixed:

1. After `B14` is frozen and the exact treatment SHA is approved, record `T0`
   and the first treatment midnight in `docs/s29-measurement.json`.
2. Treatment day 1 begins at that exact `00:00:00Z`.
3. Post the fixed message in every approved channel from `00:05:00Z` through
   `00:35:00Z` on treatment day 1. This is one 30-minute release slot, not a
   rolling campaign.
4. Treatment ends exactly 14 complete UTC days after treatment day 1 begins.
5. Once the treatment start is committed, the resulting calendar date and
   14-day window are frozen. Do not move, extend, or restart them silently.

Treatment day 1 must begin no later than `2026-10-20T00:00:00Z`, so all 14
complete days end by `2026-11-03T00:00:00Z`, before Election Day begins in
Richmond. If the readiness gates cannot meet that cutoff, this packet expires:
post nothing and seek a new decision for any post-election release or copy.

If a readiness gate fails before the release slot, post nothing. Keep the
measurement contract pending and choose a new fixed window after the gate is
healthy. If a channel delays moderation, record the actual publication time;
do not repost, bump, or replace the message.

## Channel boundary

The operator chooses one to three channels that they control and whose rules
allow this post. Use each channel once. Do not add paid reach, automated direct
messages, a partner mailing, influencer outreach, or another channel during the
14-day treatment.

Channel names and coarse source hostnames belong only in the private operator
log, not in this public repository. Do not retain a source post permalink or
referring path. Until the operator supplies the channel names, no external post
is authorized.

## Link and privacy protocol

- Use exactly `https://richmondcommons.org/elections/2026-general` in every
  post.
- Do not add UTM parameters, query strings, fragments, redirectors, or URL
  shorteners.
- Do not add custom analytics events, pixels, cookies, fingerprints, form
  fields, or person-level identifiers.
- Vercel reporting remains aggregate pageviews, daily-reset visitors, and
  referrer hostnames under the existing small-cell rule. Two groups on the same
  platform cannot be separated analytically and must not be presented as if
  they can.
- Do not retain commenter names, profile links, reactions, or person-level
  engagement in the operator log.

## Private posting log

At treatment activation, create
`src/data/analytics_checkpoints/s29-outreach-log.json`. That directory is
already gitignored. The log records the release, not individual visitors.

Record:

- treatment start and end in UTC;
- the fixed copy version (`s29-outreach-v1`) and canonical landing URL;
- for each of no more than three slots: platform, exact channel name, coarse
  source hostname, scheduled UTC time, actual UTC time, and status;
- moderation delay, removal, or material outside coverage; and
- no click counts, visitor names, profiles, comments, reactions, source post
  permalinks, referring paths, or full Vercel referrer URLs.

Allowed status values are `posted`, `moderation_pending`, `removed`, and
`skipped`. A skipped or removed post stays in the log and is not replaced.

## Closeout rules

Use the existing `B14` and `T14` packet. Report raw counts and descriptive
changes only:

- November election route views;
- homepage, meeting-index, council-index, and district-finder views;
- pageviews, daily-reset visitors, visitor-days, and bounce rate;
- initial subscriptions and re-subscriptions separately, plus their total;
- coarse acquisition surfaces and welcome/orientation delivery health;
- referrer hostnames only when the existing five-visitor-day rule permits; and
- outages, analytics pauses, moderation delays, removals, and material outside
  coverage.

Fewer than 50 November-route treatment pageviews is `insufficient exposure`,
not success or rejection. Do not claim that the message, any channel, the UX,
SEO, Richmond 101, or election timing caused a change. Do not extend the window
or add a second post to rescue a low count.

## Remaining operator input

**ACTION:** Supply one to three exact channel names in this format; omit unused
slots:

```text
CHANNELS: 1) [platform — exact channel name]; 2) [platform — exact channel name]; 3) [platform — exact channel name]
```

After that reply, populate the private log template. The exact calendar dates
will be calculated from the approved `T0` and committed in a reviewed change.
No additional scheduling judgment is needed unless a readiness gate fails or
the pre-election cutoff cannot be met.
