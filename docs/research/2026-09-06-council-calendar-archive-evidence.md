# Council calendar and archive follow-up — September 6, 2026

Read-only source/production audit; implementation based on `f47aeb63eccb17280b7bbcc17044443eda6e8a63`. No live imports, dispatches, model calls, or data corrections were performed.

## Council schedule and source coverage

The [September 4 City Manager report, page 3](https://www.ci.richmond.ca.us/Archive.aspx?ADID=17876#page=3) says the council is in recess and regular sessions resume September 15. The [August 28 report, page 3](https://www.ci.richmond.ca.us/Archive.aspx?ADID=17867#page=3) gives the same date. September 4 PDF SHA-256: `879f6cfbe911b4e35dd4efad1698e69ee34f84e91c861740c3f441d6dc77c7a1`.

The official eSCRIBE calendar API, queried for July 1–October 31 with cancellations included, returned only the five meetings below. The [City agenda archive](https://www.ci.richmond.ca.us/Archive.aspx?AMID=30) also stops at August 26. No September agenda or meeting time was found. This is a published-agenda absence, not proof that no meeting is scheduled.

| Date | eSCRIBE GUID | Source leaf items / live active items |
|---|---|---:|
| July 7 | `e420dbcd-8417-474e-9167-d2a28d3c5b6d` | 29 / 29 |
| July 21 | `2de7b493-e2eb-4f46-af1c-244f4c7eafec` | 25 / 25 |
| July 28 | `ab7e536d-f895-404f-845f-b7fc17ad77d0` | 56 / 56 |
| August 11, special | `c3c39254-53cc-4461-9b85-041288171803` | 2 / 2 |
| August 26, closed session | `109ce607-21c0-4495-9bfc-e2024d85afac` | 3 / 3 |

All 115 leaf item-number sets match exactly, with no missing or extra active items. Department wrapper headings are excluded by the existing converter. The [September 6 scheduled Data Sync](https://github.com/pjfront/richmond-common/actions/runs/34030977958) reconciled all four meetings inside its 60-day lookback at 11:45–11:48 UTC, with zero eSCRIBE errors. July 7 was checked the previous day and fell outside that window on September 6.

The homepage now shows the dated, source-linked recess notice only when the database calendar is available and has no upcoming meeting. It supplies no invented time or meeting row. English and Spanish copy use the existing `Localized` component. The notice expires at the start of September 15 in Richmond; a client expiry check also hides it from an open tab or stale ISR response after hydration. A failed database query keeps its existing unavailable-calendar message.

## Formal minutes

The [City minutes archive](https://www.ci.richmond.ca.us/Archive.aspx?AMID=31) currently labels June 23 and July 7/21/28 as “public comments received”; these are not a newly published set of formal minutes. No August council minutes appear in that listing. Production contains these comment-only document revisions without formal-minutes extraction. Its latest meeting with motions explicitly sourced to minutes is June 16, backed by [ADID 17676](https://www.ci.richmond.ca.us/Archive.aspx?ADID=17676). That meeting has a null `minutes_url`, despite its formal extraction; repairing that pointer is separate from inventing July/August outcomes.

The same daily run scanned eSCRIBE IDs 62378–65378 and found three already-linked Post-Meeting Minutes PDFs: [June 9, 62425](https://pub-richmond.escribemeetings.com/filestream.ashx?DocumentId=62425), [May 19, 62426](https://pub-richmond.escribemeetings.com/filestream.ashx?DocumentId=62426), and [May 26, 62878](https://pub-richmond.escribemeetings.com/filestream.ashx?DocumentId=62878). Their filenames were verified by HEAD requests. This bounded filename scan is not a proof that no undiscovered standalone minutes exist anywhere. No broad document scan was repeated in this audit. No agenda refresh dispatch is indicated by the source comparison.

## Archive persistence defect and bounded repair

The September 5 and 6 logs contain the exact same 1,647 failed ADIDs, all reporting `object supporting the buffer API required`. Breakdown: resolutions 1,382; ordinances 185; Personnel Board minutes 49; Personnel Board agendas 21; Design Review agendas 8; Planning minutes 2. Council minutes account for zero of these failures.

`save_to_documents()` supplied `None` to `ingest_document_with_status()` when deterministic PDF extraction returned no text; the latter immediately calls SHA-256. These are local extraction/persistence errors, not paid-model failures. The archive sync also re-enumerates its full 12-module inventory despite the `incremental` name. That network/CPU inefficiency is not expanded into a broad replay here.

Two bounded official-source checks confirmed image-only PDFs, HTTP 200, and zero extractable text:

- [Resolution 143-26, ADID 17838](https://www.ci.richmond.ca.us/Archive.aspx?ADID=17838): 4 image pages, 673,151 bytes; SHA-256 `342ef7949272679545e3ef0baed038e55046639f133af9c04924ae972a4c7b7b`.
- [Ordinance 11-26, ADID 17810](https://www.ci.richmond.ca.us/Archive.aspx?ADID=17810): 12 image pages, 6,070,562 bytes; SHA-256 `199c9e7a20667b984949c8eaf27c3812053f9d70dba5db3f9c95ccf308e39c0d`.

The fix carries the downloaded PDF path into persistence and retains original PDF bytes for scan-only documents, with `raw_text=NULL` and explicit metadata showing unavailable text. Missing bytes or an HTML error page fails visibly; empty content is never fabricated. Existing text-bearing documents retain their historical text hash and UUID. This deliberately does not migrate all legacy text records to PDF-byte identity.

Normal catch-up is capped at **20 new scan documents and 32 MiB per run**, newest ADIDs first. Already-retained hashes spend neither budget. Deferred scans are counted separately; later runs advance through the remaining backlog. An individual scan over 32 MiB requires an explicitly larger bounded persistence call, rather than bypassing the byte ceiling. Text imports remain independent. Genuine persistence failures return `required_source_incomplete` instead of a silently complete source result. No model/OCR stage is enabled by retaining the source.

Persistence validates the PDF signature and streams its hash in 1 MiB chunks before checking the count/byte limits. Only an admitted new scan receives a final bounded read; its size and hash must still match before insertion. This avoids materializing oversized or already-retained scans and rejects a file changed between hashing and persistence. It does not impose new limits on PyMuPDF extraction or the earlier HTTP download.

**Remaining efficiency limitation:** both sync modes still enumerate all 12 modules and attempt all 5,215 current records, including the repeated 1,647-scan cohort. The downloader reuses a PDF only if its local path exists. Scheduled Actions cache Python dependencies, not the raw PDF directory, so fresh runners download and deterministically extract these records again. The new persistence cap controls database growth, not network work. A separate change-aware archive cache/cursor should persist source identity and verification metadata, prioritize newly listed ADIDs, and periodically recheck older documents for replacements; no such cache or broad archive replay is included here.

Validation: 67 targeted Python tests, 14 frontend tests, TypeScript checking and targeted ESLint pass. Regression tests exercise generated image-only PDFs through the actual hashing/writer code, stable-ID replay, distinct-scan identity, historical text hashes, absent/invalid evidence, count and byte budgets, progress across repeats, chunked oversized-file reads, and rejection of source bytes changed before insertion. Browser checks at desktop and 390px width show English/Spanish notice copy, its official source link, no horizontal overflow, and no framework error overlay. Production execution remains with the release coordinator after review.
