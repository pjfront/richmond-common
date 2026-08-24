"""Keep retired n8n orchestration out of current operational guidance."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_current_operational_surfaces_do_not_claim_n8n_is_active():
    current_surfaces = [
        "agents/founding-engineer/AGENTS.md",
        "docs/PROJECT-SPEC.md",
        "src/cloud_pipeline.py",
        "src/data_sync.py",
        "src/staleness_monitor.py",
    ]
    for relative in current_surfaces:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8").lower()
        assert "n8n" not in text, f"retired n8n claim remains in {relative}"


def test_historical_architecture_docs_warn_before_n8n_content():
    for relative in (
        "docs/ARCHITECTURE.md",
        "docs/specs/cloud-pipeline-spec.md",
    ):
        opening = "\n".join(
            (REPO_ROOT / relative)
            .read_text(encoding="utf-8")
            .splitlines()[:15]
        ).lower()
        assert "historical" in opening
        assert "n8n" in opening
        assert "github actions" in opening
        assert "current" in opening
