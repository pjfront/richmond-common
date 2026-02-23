# Parking Lot — Process Issues & Improvement Ideas

*Things we noticed that need fixing but aren't the current task. Review periodically.*

---

## 2026-02-22: Research sessions must auto-persist findings

**Problem:** The Form 700 research session (pure research, no code) almost completed without documenting its findings. A durable research artifact was only created because the human noticed and intervened. This violates the AI-native architecture principle — documenting research output is not a human-unique decision.

**Root cause:** There's no skill, hook, or convention that ensures research sessions produce a durable artifact in `docs/research/`. The session treated "research" as a conversation activity rather than a pipeline that produces an output file.

**Proposed fix:** Create a skill or hook that:
1. Detects when a session is doing research (no code changes, lots of web fetches/reads)
2. Automatically writes findings to `docs/research/{topic}.md` before the session ends
3. Includes the research doc in the commit

**Scope:** This is a Claude Code workflow improvement — a skill in `.claude/skills/` or a hook in `.claude/hooks/`.
