# CEO Tools

## Paperclip API

Full Paperclip API via `http://127.0.0.1:3100/api`. Key endpoints:

| Action | Endpoint |
|--------|----------|
| My identity | `GET /api/agents/me` |
| My inbox | `GET /api/agents/me/inbox-lite` |
| Company agents | `GET /api/companies/{companyId}/agents` |
| Create issue | `POST /api/companies/{companyId}/issues` |
| List issues | `GET /api/companies/{companyId}/issues` |
| Get issue | `GET /api/issues/{issueId}` |
| Update issue | `PATCH /api/issues/{issueId}` |
| Checkout | `POST /api/issues/{issueId}/checkout` |
| Release | `POST /api/issues/{issueId}/release` |
| Add comment | `POST /api/issues/{issueId}/comments` |
| Heartbeat context | `GET /api/issues/{issueId}/heartbeat-context` |
| Dashboard | `GET /api/companies/{companyId}/dashboard` |
| Create project | `POST /api/companies/{companyId}/projects` |
| Create workspace | `POST /api/projects/{projectId}/workspaces` |
| Update agent | `PATCH /api/agents/{agentId}` |
| Set instructions path | `PATCH /api/agents/{agentId}/instructions-path` |
| OpenClaw invite | `POST /api/companies/{companyId}/openclaw/invite-prompt` |

## Paperclip CLI

`paperclipai` — setup, diagnostics, configuration:
- `paperclipai heartbeat run --agent-id <id>` — trigger a manual heartbeat
- `paperclipai agent local-cli <name> --company-id <id>` — get local env vars
- `paperclipai doctor` — diagnostic checks

## Skills

- `paperclip` — Paperclip control plane coordination
- `paperclip-create-agent` — Create new agents with governance
- `para-memory-files` — Memory and knowledge management (REQUIRED for all memory ops)

## Git & Repo

- Repo: `https://github.com/pjfront/richmond-common`
- Local: `e:\Projectz\RichmondTransparencyProject\richmond-transparency-project`
- Commit messages MUST include: `Co-Authored-By: Paperclip <noreply@paperclip.ing>`
