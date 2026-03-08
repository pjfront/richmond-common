# Code Conventions & Standards

## FIPS Enforcement

- **Every database table** has a `city_fips` column
- **Every query** filters by `city_fips`
- **Every web search** includes "Richmond, California" — never just "Richmond"
- **Every API response** includes city context
- Richmond CA = `0660620`. There are 27 Richmonds in the US.

## Python (Backend/Pipeline)

- Type hints on all functions
- Extraction prompts in dedicated files, not inline strings
- `python-dotenv` required — `.env` is in repo root, not `src/`
- Load with `load_dotenv(Path(__file__).parent.parent / ".env", override=True)`
- Run pipeline scripts from `src/` directory
- NULL-safe field access: `(row.get("FIELD") or "").strip()` pattern

## TypeScript (Frontend)

- Strict TypeScript, no `any` types
- Next.js 16 app router with ISR (1hr revalidation)
- Supabase queries in `web/lib/queries.ts`, types in `web/lib/types.ts`

## Commit Messages

- Imperative mood, reference the phase: "Phase 2: add coalition tracking"
- Feature branches and PRs for all work (initial scaffolding was direct to main)
- AI drafts all messages; most are AI-delegable. See `team-operations.md` for when commit message framing is a judgment call requiring human review.

## Progress Tracking Sync

- **Every commit that completes or substantially advances a PARKING-LOT.md item must update the parking lot in the same commit.** Mark items ✅, add status lines, update descriptions. This is AI-delegable.
- Same applies to `CLAUDE.md` "What's Built" section when sprint status changes (e.g., an entire sprint completing).
- If a commit touches multiple tracked items, update all of them.
- This is not optional. The parking lot is the project's source of truth for progress. If it's stale, the operator wastes time re-discovering what's done.

## Testing

- pytest for Python, 400+ tests in `tests/`
- Dict-dispatched functions: use `patch.dict(SYNC_SOURCES, ...)` not `@patch("data_sync.sync_netfile")`
- Lazy imports in sync functions: patch at source module level

## Database Migrations

- Files in `src/migrations/` named `00N_description.sql`
- All migrations are idempotent (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`)
- Run manually in Supabase SQL Editor — no automated migration runner for production
- Health check: `/api/health` probes tables across all migration groups

## Documentation

- Log decisions in `docs/DECISIONS.md` with date and rationale
- Research output goes to `docs/research/{topic}.md`
- Plans go to `docs/plans/{date}-{topic}.md`
- Specs go to `docs/specs/{feature}-spec.md`

## Environment

- Use Claude Code through the Claude desktop app, NOT VS Code extension
- Parallel sessions: use built-in worktree checkbox or sibling directories (NOT `.worktrees/`)
- No `sudo npm install` — ever
- Secrets in `.env` only, `.env.example` gets placeholder values like `sk-ant-...`
