# Plain Language Standards for City Council Agenda Summaries

**Research date:** 2026-03-16
**Sources:** California Elections Code, Federal Plain Language Guidelines, GOV.UK Content Design, Center for Civic Design, Readability Measurement Science
**Purpose:** Ground the plain_language_system.txt prompt rewrite (S12.3) in authoritative standards

---

## California Voter Guides — Structural Model

- **Elections Code §9085:** LAO must prepare "concise summary of the general meaning and effect of 'yes' and 'no' votes on each state measure." Center for Civic Design field research confirms voters rank "What Your Vote Means" as the most valuable section.
- **§9087(b):** "Clear and concise terms, so as to be easily understood by the average voter." No specific FK grade level — uses 5-person review committee instead.
- **§9051(b)(1):** Condensed ballot label ≤ 75 words. **§9051(a)(1):** AG title/summary ≤ 100 words.
- **§9051(e):** "True and impartial... shall neither be an argument, nor be likely to create prejudice, for or against the proposed measure."
- **Gap:** Actual ballot measure language often scores grade 12-16 FK despite statutory intent. Higher reading difficulty → increased voter roll-off (Reilly & Richey, 2011).

## Federal Plain Language Guidelines (2011)

- Active voice over passive ("Passive voice obscures who is responsible")
- "Must" replaces "shall" (officious, imprecise)
- Present tense default; other tenses only for accuracy
- Average sentence length 15-20 words
- "You" for reader, "we" for agency (but "the City Council" is clearer than "we")
- Minimize abbreviations (≤2-3 per document)
- Avoid nominalizations ("make an application" → "apply")

## GOV.UK — Research-Backed Sentence Limits

- Reading age 9 target (most aggressive among major government publishers)
- Ann Wylie's research: 14 words → 90% comprehension; 43 words → <10% comprehension
- **25-word sentence ceiling** (stricter than federal 15-20 average)
- Words to avoid: "facilitate" (→ "help"), "stakeholder" (→ name the group), "robust," "streamline," "leverage"
- Use numerals, % symbol, $ symbol — never spell out
- Sentence case for headings, no semicolons

## Center for Civic Design — Practical Outcomes

- **Describe practical outcomes, not legal mechanisms.** Most common failure in ballot language.
- **"Yes" = change, "No" = status quo.** Violating this → voters vote against their intent.
- **Never use double negatives.** Highest rates of misunderstanding.
- **Word limits matter.** Ballot questions exceeding 1,000 words → 7.7 min read time. SF Ballot Simplification: 300-word limit, 8th-grade target.
- Readability formulas are "rather simplistic" — use as drafting flags, not quality measures.

## Readability Measurement

- **SMOG:** Gold standard for civic text. FK underestimates difficulty by ~2.52 grades. But requires 30 sentences (unreliable for 2-4 sentence summaries).
- **Flesch-Kincaid:** Most widely used, de facto government standard. Works on shorter text. WCAG 2.0 SC 3.1.5 references it.
- **Coleman-Liau & ARI:** Character-based, more stable on short text than syllable-counting formulas.
- **Target:** FK grade 6-8, hard ceiling grade 8.
- **Python library:** `textstat` (MIT, actively maintained). Key: `flesch_kincaid_grade()`, `coleman_liau_index()`, `text_standard()`.

## Synthesized 14-Rule Framework

1. **Yes/no vote structure** — every summary includes "A 'yes' vote will..." and "A 'no' vote will..."
2. **75-word maximum, 2-4 sentences**
3. **FK grade 6-8, hard ceiling grade 8**
4. **25-word sentence ceiling, 15-20 word average**
5. **Active voice exclusively** (exception: law as actor)
6. **"Will" for proposed, "would" for conditional, past tense for completed; never "shall"**
7. **Dollar amounts whenever fiscal impact exists** (rounded, with funding source)
8. **Resident-facing outcomes over administrative mechanisms**
9. **Strict factual neutrality** — no value-judgment adjectives
10. **Common words; define unavoidable technical terms inline**
11. **No double negatives; frame "no" votes in the positive**
12. **"You" for resident impact, name the acting body**
13. **Numerals, $ symbol, % symbol always**
14. **Automated readability validation** (textstat)
