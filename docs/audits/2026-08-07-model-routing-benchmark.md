# Model routing benchmark — vote explainers

**Date:** 2026-08-07
**Publication impact:** Graduated vote-explainer generation
**Models:** `deepseek-v4-flash`, `deepseek-v4-pro`, `gpt-5.6-luna`
**Spend boundary:** $0.01 per call; $0.00302716 actual for all 12 calls across both passes

## Question

Can a cheaper frontier model produce accurate Richmond vote explainers, and is there a narrow case where OpenAI earns a production route on quality per dollar?

## Source-closest inputs

The benchmark used the exact structured motion, agenda-item, and individual-vote fields consumed by `src/vote_explainer.py`, read from production without writes:

1. **Liftech contract, 2026-04-28:** passed 6-1; $299,797 in the plain-language source summary; Sue Wilson voted no.
2. **Craneway denial motion, 2026-04-21:** a motion to deny the donation failed 3-3 with one abstention. The supplied record did not include a separate final action on the underlying donation agreement.

The second case tests a credibility boundary: a failed motion to deny is not proof that the underlying item was approved.

## Results

### Initial prompt

| Model | Liftech | Craneway | Finding |
|---|---:|---:|---|
| V4 Flash | factual | unsafe | Claimed the donation was set to move forward and the city would accept it. |
| V4 Pro | factual | unsafe | Claimed the city remained on track to take ownership and the item would likely proceed. |
| Luna | factual | safe | Explicitly said the records did not show a final approval or denial. |

This identified a prompt-level accuracy gap. The prompt now requires the generator to keep the motion outcome separate from the underlying item's disposition and to preserve uncertainty when no separate final action is provided.

### Fixed prompt

| Model | Liftech checks | Craneway assessment | Actual mean cost/call |
|---|---:|---|---:|
| V4 Flash | 7/7 | Safe after the guard, but more verbose and hypothetical | $0.0001403 |
| V4 Pro | 7/7 | Safe; omitted the abstaining member's first name | $0.0003872 |
| Luna | 7/7 | Safest and most direct; preserved the unresolved disposition | $0.0002434 |

All 12 budget reservations settled against provider-reported usage. No fallback occurred; returned model IDs matched requested model IDs.

## Decision

- Keep V4 Flash as the default routine vote-explainer route.
- Use Luna only when the motion text begins with a negated action (`deny`, `reject`, `block`, or `postpone`) and that motion failed.
- Keep V4 Pro for its existing complex/source-grounded tiers; it did not earn this routine call site on either cost or safety.
- Do not activate Kimi K3. No Moonshot credential is configured, and the current evidence does not identify a quality gap that justifies adding its higher-cost route.

The expected marginal cost of the Luna exception is roughly $0.00010 per affected explainer versus Flash. The rule is structural and covered by routing-policy tests; Luna is not a fallback and cannot be selected for other call sites without another benchmark.
