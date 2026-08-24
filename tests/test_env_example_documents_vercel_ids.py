"""Guards for documented and target-bound Vercel project identifiers.

`.env.example` documents the Vercel CLI variable names for contributors, but
production deployment no longer trusts a mutable local `.env`. The wrapper
pins the established non-secret Richmond org/project IDs and refuses
conflicting ambient values.

Same enforcement pattern as tests/test_deploy_gate.py: a non-negotiable
piece of project state is locked in by a test so a future cleanup can't
silently regress it.

Background: production deploys became AI-delegable on 2026-05-18; the
exact-SHA gate now owns non-secret target binding while authentication remains
outside Git. See web/CLAUDE.md "Deployment Gating".
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"


def test_env_example_documents_vercel_org_id():
    assert _ENV_EXAMPLE.exists(), f".env.example missing at {_ENV_EXAMPLE}"
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "VERCEL_ORG_ID" in text, (
        ".env.example must document the VERCEL_ORG_ID integration name for "
        "contributors and ambient-conflict diagnosis. Production pins its "
        "target in web/scripts/deploy-prod.sh; no .env setup is required."
    )


def test_env_example_documents_vercel_project_id():
    assert _ENV_EXAMPLE.exists(), f".env.example missing at {_ENV_EXAMPLE}"
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "VERCEL_PROJECT_ID" in text, (
        ".env.example must document the VERCEL_PROJECT_ID integration name "
        "for contributors and ambient-conflict diagnosis. Production pins "
        "its target in web/scripts/deploy-prod.sh; no .env setup is required."
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
    # Sanity: the tracked gate pins the exact Richmond target and CLI version.
    text = script.read_text(encoding="utf-8")
    assert 'EXPECTED_VERCEL_ORG_ID="team_EZvKrao9Jh9nwoKNX648v4qy"' in text
    assert 'EXPECTED_VERCEL_PROJECT_ID="prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4"' in text
    assert 'VERCEL_CLI_VERSION="59.1.4"' in text
    assert 'ENV_FILE=' not in text
