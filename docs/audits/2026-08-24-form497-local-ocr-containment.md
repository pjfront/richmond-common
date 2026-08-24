# Form 497 local-OCR containment evidence - 2026-08-24

## Incident

Three consecutive automatic NetFile runs completed the structured API sync but
ended retryable because two eligible Anderson for Mayor 2026 paper filings had
no PyMuPDF text and `MOONSHOT_API_KEY` was not configured. No run was retried,
cancelled, or manually dispatched during this diagnosis. No production row was
corrected or replayed.

The pending official source PDFs were:

- [NetFile filing 217243030](https://netfile.com/Connect2/api/public/image/217243030)
- [NetFile filing 217243444](https://netfile.com/Connect2/api/public/image/217243444)

Both are one-page Form 497 Part 1 contribution-received reports, not Part 2
payments and not Form 460 summaries. Therefore the benchmarked Luna Form 460
summary exception does not apply.

## Bounded alternative tested

The official scans were rendered locally at 1.5x using PyMuPDF and read with
the pinned, offline `rapidocr==3.9.2` and `onnxruntime==1.29.0` packages. During
this local benchmark no source image was sent to an external OCR or LLM
provider. For both filings the accepted OCR transcript contained:

- the Form 497 title and Part 1 contributions-received heading;
- the filing and contribution dates;
- the contributor name; and
- the exact `$2,500` contribution amount.

The deterministic post-extraction check passed the expected public name, date,
and amount for both filings. Street addresses are not recorded in this packet.

## Enforced production boundary

- Form 497 only; the source must prove Part 1.
- At most four pages and 50,000 accepted OCR characters.
- OCR lines below 0.80 confidence are excluded.
- At least two valid source dates and one comma-formatted monetary token.
- Structured extraction stays on DeepSeek V4 Pro.
- Every returned name, date, and amount must occur in the OCR transcript.
- A zero-row result, missing dependency, oversize filing, malformed OCR output,
  or ungrounded field fails closed and leaves the filing retryable.
- The local-OCR stage keeps source images on the runner and sends only its
  validated transcript to DeepSeek.
- Separately, if `MOONSHOT_API_KEY` is configured and local OCR or DeepSeek
  fails, the pre-existing optional Kimi fallback may render and send the
  filing's page images to Kimi. This change does not configure that credential
  or add a new provider route.
- No production data correction or replay is included in this change. The next
  ordinary bounded NetFile observation is the first permitted live proof after
  deployment.
