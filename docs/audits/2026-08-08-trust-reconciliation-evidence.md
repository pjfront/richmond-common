# Trust & Reconciliation evidence — bounded production checks

**Opened:** 2026-08-08

**Production baseline:** 2026-08-09T00:15:00.878681Z

**Scope:** read-only production evidence outside the GUID-scoped eSCRIBE clone work

**Hard boundary:** migration 134 remains a HARD NO-GO. Nothing in this packet authorizes a production migration or an unbounded sync.

## Disposition summary

| Item | Evidence-backed disposition |
|---|---|
| Influence-pattern taxonomy | **Confirmed exposed; containment ready.** Production granted anonymous and authenticated reads to both the base table and aggregate view. Migration 136 removes those grants and the public policy while preserving the operator/service-role path; it remains unapplied. |
| Filing 216779708 / $160,807.33 | **Resolved.** The Form 460 itself says $0 itemized and $160,807.33 unitemized. The synthetic `UNI` row is an accurate reconciliation row, not missed OCR. |
| Donor spot-checks | **Passed, bounded cohort.** Three exact NetFile lines matched production on recipient, donor, date, and amount. |
| Candidacy-cycle mismatches | **No current proven cross-cycle mismatch.** The current expectation returns zero, but seven linked candidacy rows are hidden from the check because their committees have `election_id IS NULL`. Treat this as missing cycle provenance, not as proof of correctness. |
| Liveness | **28/32 expectations pass.** The Rent Board false-positive row was removed by a City-Council body predicate; several remaining rows are genuine ingestion/linking defects, two minutes cases remain source-publication checks, and the new-member Form 700 absence remains an expiry-bound City Clerk follow-up. |
| Supabase idle/growth/RPC | **Baseline captured; +24h endpoint scheduled.** No idle-in-transaction connection existed at baseline. The broader RPC audit found a missing live RPC, unnecessary anonymous grants, and historically expensive calls that require delta measurement before tuning. |

## 0. Influence-taxonomy exposure and forward containment

Independent live checks found identical broad ACLs on
`public.influence_patterns` (table) and
`public.v_influence_pattern_summary` (view): `anon`, `authenticated`, and
`service_role` all had effective `SELECT`. The base table also had a
`Public read` policy to role `public` with `USING (true)`. Anonymous PostgREST
requests returned HTTP 200 for both relations.

The aggregate view returned these five unvalidated labels:

| Label | Flags | Meetings | Average confidence | Maximum confidence |
|---|---:|---:|---:|---:|
| Pay-to-play | 2,493 | 434 | 0.3480385 | 0.83 |
| Contract steering | 14,755 | 514 | 0.4563599 | 0.95 |
| Conflicts of interest (planning/zoning) | 2 | 1 | 0.34 | 0.34 |
| Revolving door | 930 | 298 | 0.5862796 | 0.95 |
| Quid pro quo permit approvals | 40 | 8 | 0.335 | 0.35 |

These are evidence of exposure, not validated findings. A consumer audit found
no repository query of the view beyond generated database types and baseline
DDL/ACL. The classifier reads the base table directly through the internal DB
path; live dependency checks found no dependent relation and no stored-function
reference to the view.

Forward migration 136 is mirrored byte-for-byte in both migration trees. It
drops the public read policy, revokes all table/view/sequence privileges from
`PUBLIC`, `anon`, and `authenticated`, and grants the retained path explicitly
to `service_role`. A clone transaction applied the migration, proved effective
`SELECT=false` for anonymous/authenticated and `true` for service role, then
rolled back and proved the original clone state restored. It does not drop the
view or delete rows. Production migration 136 remains unapplied pending explicit
approval; migration 134 remains untouched and forbidden.

## 1. Filing 216779708: $160,807.33 is disclosed unitemized

The official [NetFile Form 460 PDF](https://netfile.com/Connect2/api/public/image/216779708) is a 24-page pre-election statement for North Coast States Regional Council of Carpenters POWER PAC, filer ID `1463224`, covering 2026-04-19 through 2026-05-16.

Visual verification of the rendered official PDF found:

- Summary page 3, line 1: monetary contributions this period = **$160,807.33**.
- Schedule A page 4, line 1: itemized monetary contributions = **$0.00**.
- Schedule A page 4, line 2: unitemized monetary contributions under $100 = **$160,807.33**.
- Schedule A page 4, line 3: total monetary contributions = **$160,807.33**.

The production record now agrees exactly:

- one synthetic `UNI` contribution for `$160,807.33`, dated 2026-05-16;
- `form_summary_cache`: `monetary_this_period=160807.33`, `itemized_this_period=0`, `unitemized_this_period=160807.33`, `total_this_period=160807.33`;
- cycle totals: monetary `$655,464.45`, nonmonetary `$1,480.04`, total `$656,944.49`;
- cache extraction timestamp `2026-08-08T23:57:58.496Z`.

The `paper_filings_reconcile_to_form_460` liveness expectation passes because the stated unitemized amount covers the reconciliation row. Remove its now-obsolete alert suppression; do not re-run vision for this filing. Richmond's official [campaign reports page](https://www.richmondca.gov/1440/Campaign-Reports) identifies NetFile as the City's public electronic filing system.

## 2. Bounded donor spot-check

Three deliberately different contribution shapes were checked against the official NetFile Connect2 Richmond agency (`AID=RICH`, internal agency ID 163): a PAC contribution, a committee-to-committee transfer, and a late PAC contribution. This is a line-level cohort, not a claim that full committee totals were independently recomputed.

| Recipient / filer | Official NetFile line | Production result |
|---|---|---|
| Cesar Zepeda 2026 / `1450629` | SEIU Local 1021 Candidate PAC; 2026-05-05; `$2,500.00` | Exact match |
| Claudia Jimenez 2024 / `1467767` | Claudia Jimenez 2020 committee transfer; 2024-03-04; `$3,412.84` | Exact match |
| Doria Robinson 2026 / `1485224` | Amalgamated Transit Union Local 1555 PAC; 2026-05-26; `$2,500.00` | Exact match; capitalization only differed |

The official entry point remains the [City campaign reports page](https://www.richmondca.gov/1440/Campaign-Reports), which links the public NetFile portal.

## 3. Candidacy-cycle disposition

The live `candidacy_committee_cycle_matches` query currently returns zero rows, so the historical wrong-cycle links repaired by migrations 097, 100, 101, and 117 are no longer proven live mismatches.

The check is not complete: its inner join to the committee's election drops linked committees whose `election_id` is null. Seven current candidacy rows have that shape:

| Candidate | Election rows | Committee evidence |
|---|---|---|
| Ahmad Anderson | 2026 primary and general | filer `1481105`; committee cycle field null |
| Claudia Jimenez | 2026 primary and general | filer `1488504`; committee cycle field null |
| Eduardo Martinez | 2026 primary | filer `1485208`; committee cycle field null |
| Keycha Gallon | 2026 primary | paper filer/no NetFile filer ID; committee cycle field null |
| Soheila Bana | 2026 primary | filer `1440389`; committee cycle field null |

Official NetFile committee listings corroborate the named 2026 candidacies for the NetFile filers; Gallon is a paper-filer case. The safe disposition is:

1. call the current result **zero proven mismatches**, not “all links verified”;
2. refine the expectation to emit a separate tri-state outcome for `committee.election_id IS NULL`;
3. populate or explicitly waive committee-cycle provenance only in a bounded, source-owned correction; do not infer it from names alone.

## 4. Remaining liveness failures

A read-only production run on 2026-08-08 returned **28 passing / 32 total**, with four failing expectations.

### Transcript recaps — three genuine enrichment gaps

Regular City Council meetings on 2026-07-07, 2026-07-21, and 2026-07-28 have neither `transcript_recap` nor `meeting_recap`. Richmond's official [Council meeting page](https://www.richmondca.gov/4157/City-of-Richmond-Council-Meetings) and [Granicus publisher](https://richmond.granicus.com/ViewPublisher.php?view_id=2) show recordings for July 7 and July 21. These two are confirmed ingestion/enrichment gaps, not false alarms. July 28 remains actionable source verification rather than an assumed false positive.

### Minutes — seven council rows after false-positive repair

The expectation formerly checked every `meeting_type='regular'` meeting and did not constrain the governing body. It now joins `bodies` and requires `body_type='city_council'`; a live read-only rerun returned seven council rows and no Rent Board row.

- **Resolved false positive:** 2026-02-18 Rent Board is excluded by the enforced City Council body predicate and its regression test.
- **Confirmed linking/discovery defects:** City Council 2026-02-17, 2026-02-24, 2026-04-07, 2026-04-21, and 2026-04-28. Official minutes exist in the City's [Archive Center](https://www.richmondca.gov/archive.aspx), but production `minutes_url` is null. April 21 already has a document record, which makes that row specifically a meeting-link defect.
- **Source publication/availability still to verify:** 2026-06-16 and 2026-06-23. The June 23 archive hit inspected was public comments rather than minutes; the June 16 document link returned an upstream error. Keep these actionable without claiming the City has published minutes.

### Current Form 700 — expected absence, still actionable

Jamelia Brown is a current councilmember (term began 2025-01-14) and production has no matched Form 700 filing. Richmond's official [Form 700 page](https://www.richmondca.gov/1439/Form-700---Statement-of-Economic-Interes) says annual statements are due April 1 and links the public filing portal. Keep the expiry-bound suppression through 2026-10-01; if still absent then, ask the City Clerk rather than silently renewing it.

### NextRequest — genuine contract failure

Production contains 2,395 requests; the newest stored update is 2026-07-21. Scheduled attempts fetched zero changes on 2026-08-04 through 2026-08-07, and the 2026-08-08 attempt failed with `NextRequest request visibility enum is unknown`. The City confirms that [NextRequest is its public-records system](https://www.richmondca.gov/4331/Public-Records-Request). This is an upstream-enum ingestion fault, not a cadence false positive.

### Suppression cleanup implied by this run

- Remove `paper_filings_reconcile_to_form_460`: resolved and passing.
- Remove the expired `candidates_have_committee_linked` suppression: the expectation passes.
- Keep recap suppression only until the three named meetings are enriched or explicitly degraded.
- Keep the bounded Jamelia Brown Form 700 suppression through its existing 2026-10-01 expiry.
- The minutes expectation is now City-Council-scoped; its broad suppression was removed so the seven remaining rows stay actionable.

## 5. Supabase 24-hour baseline

The repeatable capture is:

```powershell
powershell -File scripts/capture-supabase-24h.ps1
```

The wrapper reads `SUPABASE_ACCESS_TOKEN` from the local `.env`, never emits it, and sends the single statement in `docs/audits/2026-08-08-supabase-24h-readonly.sql` to Supabase's management `database/query/read-only` endpoint.

### Exact baseline at 2026-08-09T00:15:00.878681Z

| Metric | Value |
|---|---:|
| Database bytes | `1,097,510,035` |
| Public tables | `83` |
| Public relation bytes | `1,080,147,968` |
| Public heap bytes | `306,241,536` |
| Public index bytes | `272,400,384` |
| Estimated live / dead rows | `447,349` / `10,413` |
| Public cumulative inserts / updates / deletes | `566,329` / `12,131,091` / `853,808` |
| Public sequential / index scans | `686,349` / `219,516,199` |
| Client connections | `12 idle`; no active or idle-in-transaction client observed after excluding the snapshot query |
| Oldest idle client state | `40 days 04:57:25.237777` |

Database-level cumulative counters at the same instant:

| Counter | Value |
|---|---:|
| commits / rollbacks | `9,392,718` / `329,256` |
| blocks hit / read | `6,074,205,092` / `120,807,473` |
| tuples returned / fetched | `16,997,693,519` / `4,000,937,491` |
| tuples inserted / updated / deleted | `743,081` / `12,158,186` / `900,652` |
| temp files / bytes | `159,337` / `375,037,760,770` |
| sessions / abandoned / fatal / killed | `753,014` / `968` / `24` / `0` |
| deadlocks / conflicts | `0` / `0` |
| cumulative idle-in-transaction milliseconds | `1,027,402,593.014` |

The five largest relations were `documents` (`189,898,752` bytes), `agenda_item_attachments` (`115,662,848`), `agenda_items_embeddings` (`102,334,464`), `motions` (`97,894,400`), and `city_permits` (`87,588,864`). The +24h capture must compare each relation and the aggregate counters, not only total database size.

### RPC surface baseline

- PostgreSQL exposes 24 public-schema functions: 16 executable by `anon`, 16 by `authenticated`, all 24 by `service_role`, 14 `SECURITY DEFINER`, and 6 both anonymous-executable and `SECURITY DEFINER`.
- `track_functions=none`; usage is therefore a bounded `pg_stat_statements` name-match heuristic. Its reset timestamp is `2026-04-16T12:04:50.800362Z`. A reset change invalidates call/runtime deltas.
- Migration-135 functions, cumulative history at baseline:

| RPC | Calls | Total execution ms | Rows | Temp blocks written |
|---|---:|---:|---:|---:|
| `get_controversial_items` | `301` | `493,879.076685` | `13,393` | `0` |
| `get_meeting_flag_counts` | `378` | `501,631.259130` | `2,831` | `0` |

These totals include pre-migration history. Only the +24h deltas measure migration 135's current behavior.

Other cumulative hotspots worth delta measurement are `find_similar_items` (`157,698` calls, `84,506,172.0016991` ms), `get_meeting_counts` (`1,825`, `1,748,999.175038` ms), `get_contested_votes` (`203`, `309,219.453845` ms, `20,943` temp blocks), and `get_divergent_motions_detail` (`197`, `291,524.859379` ms, `129,278` temp blocks).

The broader read-only audit found two actionable surface problems:

1. `get_meeting_coverage_stats` is referenced by `web/src/app/api/data-quality/route.ts` and the pipeline manifest but is absent live. The route ignores the RPC error and falls back to only its ten recently fetched meetings, so “overall” document coverage can silently become a ten-meeting sample.
2. Unnecessary anonymous grants exist on mutation-capable or internal functions. The clearest case is volatile `SECURITY DEFINER` function `cleanup_rate_limit_buckets()`, which deletes old rate-limit rows and has anonymous execute. `merge_official_pair(uuid,uuid)` also has anonymous execute (invoker security, so table permissions should still block it). `rls_auto_enable()` and `update_meeting_agenda_item_count()` have public grants even though they are event/row trigger functions. Review and revoke unnecessary execute grants in a separate tested forward migration; do not bundle this unreviewed surface into migration 136.

### +24h endpoint

A one-time heartbeat is scheduled for **2026-08-09 17:20 America/Los_Angeles**, at least 24 hours after the baseline. It will rerun the same read-only statement and append exact elapsed-time deltas here. It must not apply migrations or write production data.

**Endpoint status:** pending scheduled capture.

## 6. Guarded eSCRIBE clone proof and bounded production-write incident

The clone-target guard is now implemented. A bounded run against recoverable clone `dmsdbpnluvzjkgudquxu` completed at `2026-08-09T00:17:52Z` with:

- exact GUID-scoped tri-state outcomes: `1 created / 1 updated / 1 unchanged`;
- bounded inventory: `257 total / 3 covered / 254 pending`;
- attachment reconciliation: `4 / 4` attachments accounted for;
- before counts: `2 documents / 1 meeting / 2 agenda items / 4 attachments`;
- after counts: `5 documents / 1 meeting / 2 agenda items / 4 attachments`;
- delta: 3 created documents, 2 changed predecessor documents, 1 changed meeting document pointer, and **0 agenda-item or attachment changes**;
- a legacy executable rollback artifact was generated at that point but was
  never applied. Review then proved the capture omitted writer-mutable fields
  and relations, so that artifact is superseded and non-authoritative.

A replay then exposed legacy-stub non-idempotency: one extra document was created. Exact page comparison found that the meeting and full-calendar inventory were stable while Cloudflare re-encrypted three `/cdn-cgi/l/email-protection#...` href fragments on every response. Those transport ciphers were entering `agenda_html_sha256`, so the supposed source revision changed every run. The fingerprint now removes only that volatile hex payload. Three consecutive public-page fetches produced one canonical agenda hash: `d64642273cf1bfb21700c32d0a76b4de37f474657fe3796f02e82d6ad28ac987`.

The state contract was tightened at the same time:

- complete agendas skip only on the actual `agenda_revision_applied_sha256`, so a crash after the raw observation but before Layer 2 remains retryable;
- no-current and legacy-stub outcomes use the separate observation revision plus full-inventory hash;
- all CLI eSCRIBE full/GUID runs require the proven clone ref and dedicated clone URL variable; production is a hard no-go;
- clone activation rejects backfill, minutes, batch, and enrichment special modes before assigning `DATABASE_URL`.

### Exact idempotency replay

The clone password was rotated in memory only after a management-API read proved exact ref `dmsdbpnluvzjkgudquxu`, status `ACTIVE_HEALTHY`, host `db.dmsdbpnluvzjkgudquxu.supabase.co:5432`, and ref inequality with production. Neither password, token, nor URL was emitted. Both runs used only `--clone-project-ref dmsdbpnluvzjkgudquxu --clone-database-url-env ESCRIBE_CLONE_DATABASE_URL`, full sync, and the same three explicit GUIDs.

The first corrected run at `2026-08-09T00:33:31Z` performed the expected one-time fingerprint transition:

- run result: `0 new / 1 updated / 2 skipped`, with one outcome in each tri-state class;
- snapshot total: `14 -> 15`; `created=1`, `changed=1`, `missing=0`, `unsafe_after_only=0`;
- created current stub document `99decf79-08ea-494f-876e-9934f6a5aa51` with semantic revision `0a0e18cf70a94f2b5b9fca6911565dfab790fc7b2edc40c4d35fa90fac245ae8`;
- predecessor `c9815d17-7670-4633-8880-adc4d52ae3d4` changed only by retirement;
- meetings, agenda items, and attachments had exact zero delta;
- before/after snapshot hashes: `5dad6975875c3424f012c0ccc2e5536cb919164178b20579e3045ea57cedf020` / `9317edf2fcac0bef3a373b1c5d854e6780a18ee53d5f0073d2a27e8c63e15cc4`.

The immediate second run at `2026-08-09T00:33:35Z` is the acceptance proof:

- run result: `0 new / 0 updated / 3 skipped`, again preserving one outcome in each tri-state class;
- exact scoped total: `15 -> 15`; `created=0`, `changed=0`, `missing=0`, `unsafe_after_only=0`;
- documents `8 -> 8`, meetings `1 -> 1`, agenda items `2 -> 2`, attachments `4 -> 4`, with zero per-table deltas;
- before/after snapshot hashes: `a3f6541ac2d423a316c9485937e24587fb72cdc7e05a03b86b31b7909b3f23c2` / `1e45bd5796a7e76d89f545f2214ae3f4efd62d21ad9a370efab2555b06c1da5d`.

### Post-ownership-fence current-path exercise

The `00:33Z` replay occurred before the final agenda/minutes attachment ownership
fence was in the shared code, and its complete-agenda row was still inside the
24-hour verification interval. A second acceptance run therefore exercised the
current loader on the same proven clone and exact three-GUID cohort. This was a
**synthetic clone-only setup**, not a naturally due row: current complete-agenda
document `5a52c653-51c5-4b21-bc04-ff7fb4b2acce` had
`agenda_revision_applied_at=2026-08-08T17:17:59.133926-07:00` and was only
2,578.560 seconds old. A guarded prerequisite changed only that metadata key to
`2026-08-07T01:00:57+00:00`. All other metadata compared equal. Its before/after
metadata hashes were
`6fd38fe8ded034d2d85929b44b620adba2cd73eb5a005a347d175186dfb18a53` /
`d55bc2f370709deb135fa443e6017302567cae40f6f8cc08780cca030badf32c`;
the prerequisite artifact file hash is
`644fbc3af0cb63e907013b686a5ee239266fe47a1e7184911f25a3e99e008d79`.

The forced-due run completed in 7.2 seconds with `0 new / 1 updated / 2
skipped`. It re-scraped GUID `c3c39254-53cc-4461-9b85-041288171803`, found 16
source agenda items, downloaded and extracted all `4 / 4` declared
attachments, and ran the current authoritative loader plus persisted-inventory
assertion. The selected-field capture changed `15 -> 16`: one new current raw
document, one predecessor retirement, and one meeting document-pointer change;
there were no agenda-item or attachment changes.

- New current raw document: `e8319563-1ef5-4085-a87a-913d8d5af8a1`, content
  hash `1094af541913c2e3a9cf1db587cb741f33a60a435dc4885562056d6ad9d1d5a4`,
  applied revision
  `31cf57057fdccf3ff2455cec8c24c716d1b0abe3c9e096ca75f4b510b9cbbacd`.
- Its metadata records 4 declared / 4 downloaded attachments and inventory hash
  `785cb507d084452c193a8b3f4132d0f9920600619dec29bd03905e5a37ee0b2d`,
  exactly matching the predecessor inventory hash.
- Predecessor `5a52c653-51c5-4b21-bc04-ff7fb4b2acce` changed only from active to
  retired at `2026-08-09T01:01:00.169047+00:00`; meeting
  `4f115627-cc88-4c76-a599-bd2c0decc239` changed only its document pointer to
  the new current raw row.
- Both persisted agenda items remained active, ID-stable, revision-stable, and
  `agenda_source_authority='agenda'`.

All four attachment identities remained active and exact before/after:

| Attachment ID | Source document | Content SHA-256 |
|---|---:|---|
| `2b061f3e-7ff0-41d5-853a-80b611741bfb` | `62881` | `87a6f3da657f937213dfa7cf345356c6c6bd87ba6641753da1919ce2123c18a3` |
| `43d653ed-8acd-42f9-a34f-8fb5c9b2a3fa` | `62884` | `9eb4592245af1e43aaed7e7cae19d0c15eefe60bbd279c810ec4f3093763c34f` |
| `6bd73a73-ef85-40b9-83fc-dd31157d9b46` | `62883` | `2a53e860baba7b8d4cab2149c833dc84e1988b14c312bb41ee247bd76d19117c` |
| `85c583d2-a245-4637-9a4b-fb79de065ce0` | `62882` | `87609e0afed92bd73978e010c62afd9a578d884eb1e1ef6066cd8df1ca092cf7` |

Each belongs to agenda-owned item `b31e0afa-1b57-4f57-9934-de8f749a54e5`
and retained revision
`31cf57057fdccf3ff2455cec8c24c716d1b0abe3c9e096ca75f4b510b9cbbacd`
with `source_retired_at=NULL`. The exact live cohort contains **zero
minutes-owned items and zero minutes-owned attachments**, both before and
after. This is an exact `0 -> 0` ownership check, not a non-vacuous live proof;
the non-zero minutes-preservation cases remain covered by the focused loader
tests.

The immediate replay completed in 3.3 seconds with `0 new / 0 updated / 3
skipped`. Its capture was `16 -> 16`, with zero created, missing, changed, or
unsafe-after-only IDs in every selected table. Snapshot hashes were:

- forced-due before/after:
  `e3df7bc9721c7db7fca479bea2cd27a5bc62165be3bfad489b8006146d7a79f7` /
  `8c3e4d3d3587dc7bd74d727c501b060cf3d76ab3d25252715b659efd610d6a28`;
- immediate replay before/after:
  `460a6da876a0d4b477ef3c52d5f09ee20b0d000018e69d6ae3d2f96192d71c75` /
  `19b8fad0e6072b125192cd62a386a296e2789cb3e163ebf1dbc0c4f7f238fb6b`.

Both review manifests are non-executable and state
`mutation_surface_complete=false` and `restoration_supported=false`. No
production sync, migration, or restoration action was part of this exercise.

Scope warning: these snapshot counts prove the exact GUID-owned rows and
selected fields captured in `documents`, `meetings`, `agenda_items`, and
`agenda_item_attachments`. The loader can also change uncaptured content fields,
delete or invalidate derivative relations, and write audit/sync-log rows outside
that cohort. The evidence utility therefore now emits only integrity-hashed JSON
delta artifacts with `mutation_surface_complete=false`,
`restoration_supported=false`, an explicit omitted-surface list, and exact
per-table IDs/counts. Its executable SQL option and restoration-safety claim
have been removed; the older SQL files in the local evidence directory are
superseded historical artifacts and were never applied. Full production
restoration remains unproven and is a hard no-go. This clone proof is not
production approval; no production sync, enforcement migration, or migration
134 action is authorized.

### Migration 134 rollback-only clone preflight — blocked/no-op

The unchanged draft at
`docs/plans/134_source_reconciliation_enforcement.sql` had SHA-256
`4fac27264b5b0fe63f03d92e52462db33590457c11de64e795f4daeb4072e7a6`.
For the clone-only check, the in-memory payload mechanically replaced only its
single EOF-anchored `COMMIT;` with `ROLLBACK;`. The qualifying
`recent_complete_full_sync` preflight was **0**, so the first `DO` block raised
`source reconciliation cutover blocked: no recent complete full sync`. The
attempt aborted before quarantine DML or policy DDL; the terminal `ROLLBACK`
was therefore unreachable and operationally a no-op. No qualifying sync row or
other preflight shim was injected.

There was no independently sampled mutated inside state. “Not reached” below
means exactly that the preflight aborted before a mutation could create one; it
must not be read as a separately observed inside value.

| Metric | Before | Inside | After |
|---|---:|---|---:|
| `active_agenda_items` | 190 | Not reached | 190 |
| `active_attachment_quarantine_candidates` | 7,945 | Not reached | 7,945 |
| `active_legacy_agenda_items` | 2,281 | Not reached | 2,281 |
| `active_legacy_parent_attachments` | 4,176 | Not reached | 4,176 |
| `active_minutes_items` | 9,514 | Not reached | 9,514 |
| `active_null_revision_attachments` | 7,945 | Not reached | 7,945 |
| `active_unsanitized_documents` | 258 | Not reached | 258 |
| `before_public_agenda_items` | 11,985 | Not reached | 11,985 |
| `before_public_attachments` | 8,576 | Not reached | 8,576 |
| `before_public_documents` | 8,017 | Not reached | 8,017 |
| `expected_public_agenda_item_loss` | 2,281 | Not reached | 2,281 |
| `expected_public_attachment_loss` | 7,945 | Not reached | 7,945 |
| `incomplete_current_attachments` | 0 | Not reached | 0 |
| `meetings_with_guid` | 210 | Not reached | 210 |
| `missing_current_raw` | 203 | Not reached | 203 |
| `recent_complete_full_sync` | 0 | Not reached | 0 |
| `unproven_active_agenda` | 0 | Not reached | 0 |
| `unsanitized_without_replacement` | 258 | Not reached | 258 |

Post-check: `metrics=18`, `changed=0`, `differences=[]`. This proves only that
the current draft fails closed at its first gate and leaves the clone unchanged
when that gate is unsatisfied. It does **not** exercise the draft's destructive
body, prove source ownership, or make migration 134 safe. Migration 134 remains
unchanged, unapplied, and a HARD NO-GO.

### Production incident

During the parallel clone work, `data_sync` unexpectedly force-loaded the production `.env`. The bounded three-GUID attempt therefore wrote to production before it was stopped:

- 3 new raw `documents` rows;
- 2 older raw `documents` rows soft-retired;
- 1 `meetings.document_id` repointed;
- agenda-item rows, attachment rows, and their counts were unchanged.

No broader run followed. The fail-closed clone guard is now enforced and tested. A SELECT-only comparison from the baseline at `00:15:00.878681Z` to `00:16:33.107593Z` found exact zero deltas in database bytes, public relation bytes, public estimated live/dead rows, aggregate insert/update/delete counters, and the corresponding `documents`, `meetings`, `agenda_items`, and `agenda_item_attachments` metrics. This confirms no continuing mutation after the baseline; it does not erase the bounded writes already included in that baseline.

Any rollback, production replay, enforcement migration, or production correction still requires a separate exact GUID-scoped approval packet.

## 7. Duplicate-contribution adjudication — destructive action held

The July warning `cc106e5c-8198-403d-95ad-f6bdba638181` said 10 possible
duplicate contributions because `check_duplicate_contributions()` applied
`LIMIT 10` before calculating the total. That 10 was only a sampled prefix of
the same cohort, not the population. Its pending-decision payload retained five
examples: Cecilia Lucas `$100` on 2024-02-03, `$100` on 2024-03-18, and `$250`
on 2023-04-30; Ellen Pechman `$100` on 2017-09-10 and `$200` on 2018-10-27.

The uncapped production query found **42 groups / 42 extra rows / $14,900**.
Every group has exactly two rows. Within each pair, donor display name, amount,
date, committee, filing ID, and `city_clerk` source are identical; the rows
differ by donor profile and load timestamp. Donor profiles were not merged
because employer/occupation provenance can materially differ. The proposed
survivor is the earlier contribution row; any richer entity/election/schedule/
document fields from the later row are copied onto it before the later
contribution row is removed.

The exact 42 keeper/drop pairs and their name/amount/date/filing/source fields
are versioned in
`docs/audits/2026-08-08-duplicate-contribution-cohort.csv`. The rollback capture
contained 84 rows totaling `$29,800` and had MD5
`394c4bd5e706f0360174657f38785667`.

A guarded production transaction then proved the proposal without persisting
it:

- before: `42 groups / 42 extras`, with all 84 planned rows present and no
  flagged row outside the plan;
- inside the transaction after survivor enrichment and 42 exact-ID deletes:
  `0 groups / 0 extras`, all 42 keepers present, all 42 drops absent;
- after explicit `ROLLBACK`: `42 groups / 42 extras`, and all 42 drop IDs
  restored.

The patched check computes the full population with a window aggregate before
returning five bounded examples; a read-only production run now reports
`count=42`. Decision `cc106e5c-8198-403d-95ad-f6bdba638181` remains **pending**
and unchanged. No contribution deletion, donor merge, or decision resolution
was persisted. The destructive production cleanup is held for explicit
operator approval.
