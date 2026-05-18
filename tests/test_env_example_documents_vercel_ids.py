"""Guard test: .env.example must document VERCEL_ORG_ID and VERCEL_PROJECT_ID.

These vars are required for web/scripts/deploy-prod.sh to work. Without
them in .env.example, new contributors (or future-AI sessions starting
fresh) won't know they need to set them, and AI-delegated production
deploys will fail with cryptic errors.

Same enforcement pattern as tests/test_deploy_gate.py: a non-negotiable
piece of project state is locked in by a test so a future cleanup can't
silently regress it.

Background: production deploys became AI-delegable on 2026-05-18 (see
.claude/rules/judgment-boundaries.md "Production deploy command execution"
and web/CLAUDE.md "Deployment Gating"). The mechanism is env-var-based
Vercel linkage — keeping the variable names documented in .env.example
keeps the boundary expansion reversible: if someone removes the vars
from .env to revoke AI deploys, .env.example still tells them how to
restore the capability.
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"


def test_env_example_documents_vercel_org_id():
    assert _ENV_EXAMPLE.exists(), f".env.example missing at {_ENV_EXAMPLE}"
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "VERCEL_ORG_ID" in text, (
        ".env.example must document VERCEL_ORG_ID. Required by "
        "web/scripts/deploy-prod.sh. See web/CLAUDE.md 'Deployment Gating' "
        "for setup instructions."
    )


def test_env_example_documents_vercel_project_id():
    assert _ENV_EXAMPLE.exists(), f".env.example missing at {_ENV_EXAMPLE}"
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "VERCEL_PROJECT_ID" in text, (
        ".env.example must document VERCEL_PROJECT_ID. Required by "
        "web/scripts/deploy-prod.sh. See web/CLAUDE.md 'Deployment Gating' "
        "for setup instructions."
    )


def test_deploy_script_exists_and_is_executable():
    """The deploy script must exist; permissions check skipped on Windows
    where bash scripts are invoked via `bash <script>` rather than
    relying on +x.
    """
    script = _REPO_ROOT / "web" / "scripts" / "deploy-prod.sh"
    assert script.exists(), (
        f"Deploy script missing at {script}. AI-delegated deploys depend "
        f"on this wrapper. See web/CLAUDE.md 'Deployment Gating' for "
        f"what it should do."
    )
    # Sanity: the script references the env vars it depends on.
    text = script.read_text(encoding="utf-8")
    assert "VERCEL_ORG_ID" in text and "VERCEL_PROJECT_ID" in text, (
        "deploy-prod.sh must reference VERCEL_ORG_ID + VERCEL_PROJECT_ID "
        "(it reads them from .env). If renamed, update this test."
    )
