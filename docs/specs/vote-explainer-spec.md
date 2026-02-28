# S3.2 — "Explain This Vote" Lite

**Sprint:** 3 (Citizen Clarity)
**Paths:** A, B
**Publication tier:** Graduated (operator-only until framing validated)
**Depends on:** S2.1 (categories, complete), S3.1 (summaries, complete)

## Problem

Citizens can see how council members voted, but not *why it mattered*. Vote tallies like "5-2, Passed" don't communicate what was at stake, whether the outcome was routine or contentious, or what it means for residents. The existing plain language summary (S3.1) explains the agenda item, but not the vote itself.

## Solution

Generate a per-motion explainer that answers:
1. **What was decided?** (synthesis of motion + context)
2. **Why does it matter?** (financial impact, policy significance, who's affected)
3. **Was it contentious?** (unanimous vs. split, with the actual breakdown)

Explicitly out of scope (parked as Option C): historical voting patterns per member, cross-referencing contributions, speculation about motives.

## Architecture

Follows the S3.1 pattern exactly:

| Layer | S3.1 (Summaries) | S3.2 (Vote Explainers) |
|-------|-------------------|------------------------|
| **Target table** | `agenda_items` | `motions` |
| **Fields** | `plain_language_summary`, `_generated_at`, `_model` | `vote_explainer`, `_generated_at`, `_model` |
| **Module** | `plain_language_summarizer.py` | `vote_explainer.py` |
| **Generator** | `generate_summaries.py` | `generate_vote_explainers.py` |
| **Prompts** | `prompts/plain_language_*.txt` | `prompts/vote_explainer_*.txt` |
| **Frontend** | `AgendaItemCard` (expandable) | `VoteBreakdown` (below vote display) |
| **Skip logic** | Procedural items | Procedural items + consent calendar unanimity |

## Prompt Design

### Inputs to the prompt
- Agenda item: title, category, department, financial_amount, plain_language_summary
- Motion: motion_text, motion_type, moved_by, seconded_by, result, vote_tally
- Votes: list of (official_name, vote_choice)

### Prompt guidelines
- 3-5 sentences maximum
- Factual framing. No opinion, no advocacy, no motive inference.
- State the decision outcome and what it means for residents
- Note financial amounts when relevant
- Characterize the vote margin: "unanimously," "with one dissent," "in a close 4-3 vote"
- Name who voted against or abstained (dissent is newsworthy; unanimity is not)
- Use the plain language summary for context rather than re-explaining the item

### Skip logic
- Skip procedural items (same as S3.1)
- Skip consent calendar items that passed unanimously (no meaningful vote context to explain)
- Generate for: all non-procedural items with votes, especially split votes

## Database

Migration `008_vote_explainers.sql` adds to `motions`:
- `vote_explainer TEXT` (nullable)
- `vote_explainer_generated_at TIMESTAMPTZ` (nullable)
- `vote_explainer_model VARCHAR(50)` (nullable)

## Frontend

- Display in `VoteBreakdown.tsx` below the existing vote badges
- Gated by `OperatorGate` (graduated tier)
- Subtle styling, distinct from the motion text. Similar treatment to plain language summaries.

## CLI

```
python generate_vote_explainers.py                     # All motions missing explainers
python generate_vote_explainers.py --meeting-id UUID   # Single meeting
python generate_vote_explainers.py --limit 10          # Process N motions
python generate_vote_explainers.py --dry-run            # Preview without generating
python generate_vote_explainers.py --force              # Regenerate existing
```

## Tests

- Unit tests for `vote_explainer.py` (prompt assembly, skip logic)
- Integration-style tests for `generate_vote_explainers.py` (query building, save logic)
- Follow existing test patterns from `test_plain_language_summarizer.py`

## Future (Parked)

**Option C: Historical Context** — Add a query that pulls past votes by the same council members on items in the same category. Feed to the explainer prompt as additional context ("Councilmember X has voted against housing projects 4 of the last 5 times"). Trigger: after 2-3 prompt iterations on the base explainer. No schema changes needed, just a richer query + prompt input.
