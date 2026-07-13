# Founding Engineer Heartbeat Checklist

Run every heartbeat.

## 1. Identity & Inbox (30s)

- [ ] `GET /api/agents/me` — confirm identity, status
- [ ] `GET /api/agents/me/inbox-lite` — check assignments
- [ ] If `PAPERCLIP_WAKE_COMMENT_ID` is set: read that comment thread first

## 2. Work (variable)

- [ ] Pick highest-priority assigned task
- [ ] Checkout if not already checked out
- [ ] Read heartbeat-context + issue details
- [ ] Read relevant codebase files (CLAUDE.md, project rules, files the task touches)
- [ ] Do the work — build, test, commit
- [ ] Update status + comment with what changed

## 3. Extraction (1 min)

- [ ] Commit message format: imperative, sprint prefix
- [ ] `Co-Authored-By: Paperclip <noreply@paperclip.ing>` on every commit
- [ ] Update PARKING-LOT.md if feature completed/advanced
- [ ] Update pipeline-manifest.yaml if pipeline changed
- [ ] Push to feature branch, create PR, queue auto-merge

## 4. Escalation

- [ ] Blocked? → PATCH status to `blocked`, comment with blocker, mention CEO
- [ ] Need architecture decision? → comment + mention CEO
- [ ] Cross-team dependency? → escalate to CEO
- [ ] Budget concern? → flag in comment

## Exit Conditions

- Nothing assigned AND no mention → exit
- Blocked with no new context → exit (don't re-comment)
- Work done → update status, comment, exit
