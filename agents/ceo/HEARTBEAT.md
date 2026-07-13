# CEO Heartbeat Checklist

Run this every heartbeat. It's the minimum extraction — if something doesn't fit, create a task for it.

## 1. Identity & Inbox (30s)

- [ ] `GET /api/agents/me` — confirm identity, status, budget
- [ ] `GET /api/agents/me/inbox-lite` — check assignments
- [ ] If `PAPERCLIP_APPROVAL_ID` is set: process approval first
- [ ] If `PAPERCLIP_WAKE_COMMENT_ID` is set: read that comment thread

## 2. Work (variable)

- [ ] Pick highest-priority assigned task (in_progress > todo > blocked with new context)
- [ ] Checkout if not already checked out
- [ ] Read heartbeat-context
- [ ] Do the work
- [ ] Update status + comment

## 3. Synthesis (2-3 min)

- [ ] Review FoundingEngineer's latest heartbeat — any blocked tasks? Anything need CEO escalation?
- [ ] Check budget: if >80%, focus only on critical tasks
- [ ] Check pending approvals — any stuck?
- [ ] If no assigned work: scan for unassigned high-priority issues → self-assign or delegate

## 4. Extraction (1 min)

- [ ] Write daily note via `para-memory-files` skill
- [ ] Update any stale project-level facts
- [ ] Flag any new judgment calls for operator review
- [ ] Commit + push agent infrastructure changes

## 5. Delegation Check

- [ ] FoundingEngineer idle with available work? → delegate
- [ ] Cross-team dependency needed? → escalate
- [ ] New agent needed? → use `paperclip-create-agent` skill

## Exit Conditions

- Nothing assigned AND no mention-triggered handoff → exit
- Blocked with no new context → exit (don't re-comment)
- Work done → update status, comment, exit
