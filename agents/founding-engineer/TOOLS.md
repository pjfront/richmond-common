# Founding Engineer Tools

## Paperclip API

Same API as CEO. Key endpoints:

| Action | Endpoint |
|--------|----------|
| My identity | `GET /api/agents/me` |
| My inbox | `GET /api/agents/me/inbox-lite` |
| Checkout task | `POST /api/issues/{issueId}/checkout` |
| Get task context | `GET /api/issues/{issueId}/heartbeat-context` |
| Update task | `PATCH /api/issues/{issueId}` |
| Add comment | `POST /api/issues/{issueId}/comments` |
| Create subtask | `POST /api/companies/{companyId}/issues` |
| Release task | `POST /api/issues/{issueId}/release` |

## Development Tools

- **Git:** Full access. Feature branches, PRs, auto-merge.
- **Supabase:** `supabase db push`, `supabase db push --dry-run`. Token in `.env`.
- **Python:** `pytest` for tests, `python src/pipeline_map.py` for pipeline ops.
- **Node:** `npm run dev`, `npm run build`, `npm run gen:types` from `web/`.
- **Vercel:** `bash web/scripts/deploy-prod.sh` (after CEO OKs deployment batch).

## Skills

- `paperclip` — Paperclip coordination
- Codebase tools — Read, Write, Edit, Grep, Glob, Bash, PowerShell

## Project Conventions

Always read `.claude/rules/` files before touching related code:
- `judgment-boundaries.md` — what you can decide vs. must escalate
- `architecture.md` — three-layer DB, tech stack
- `conventions.md` — code style, testing, branching, migrations
- `richmond.md` — city context, source tiers
