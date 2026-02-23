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

---

## 2026-02-22: Vercel auto-deploy from GitHub (HIGH PRIORITY)

**Problem:** Vercel deployments are manual (`npx vercel --prod` from CLI). After merging PR #4 (city-leadership), the `/api/health` endpoint was 404ing because Vercel was still serving a 2-day-old build. Every PR merge requires someone to remember to deploy. This is fragile and will get worse as parallel development increases.

**Root cause:** Vercel project isn't connected to the GitHub repo for auto-deploy. Likely set up via CLI initially and never linked.

**Proposed fix:**
1. Connect the Vercel project to `pjfront/richmond-transparency-project` GitHub repo via Vercel Dashboard → Project Settings → Git
2. Configure: auto-deploy on push to `main`, preview deployments for PRs
3. Set root directory to `web/` (since the Next.js app is in a subdirectory)
4. Verify environment variables (SUPABASE_URL, SUPABASE_SERVICE_KEY, etc.) are set in Vercel project settings

**Bonus:** PR preview deployments let you see frontend changes before merging — would have been useful for the city-leadership PR.

**Scope:** ~10 minutes in Vercel dashboard. No code changes needed.

---

## 2026-02-22: GitHub Actions CI for tests

**Problem:** PRs merge without running the 317+ test suite. Breakage is only caught after merge, when it's harder to fix. The city-leadership and commissions branches had no CI checks at all (`gh pr checks 4` returned nothing).

**Root cause:** No GitHub Actions workflow for running tests on PR.

**Proposed fix:** Add `.github/workflows/test.yml`:
1. Trigger on `pull_request` to `main`
2. Set up Python 3.x, install requirements
3. Run `python3 -m pytest tests/ -v`
4. Optionally add branch protection rule requiring tests to pass before merge

**Scope:** Small — one workflow file + optional repo settings. High value: catches regressions before merge.

---

## 2026-02-22: Clean up deprecated sync-pipeline.yml

**Problem:** `.github/workflows/sync-pipeline.yml` is deprecated (prints a warning and exits) but still in the repo. Could confuse future sessions or contributors.

**Proposed fix:** Either delete the file entirely or rename to `sync-pipeline.yml.deprecated` with a header comment explaining it was replaced by `cloud-pipeline.yml`.

**Scope:** 1 minute. Housekeeping.
