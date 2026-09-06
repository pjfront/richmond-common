"""Run the production locator parser on real stdout bytes; no network or CLI deployment."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest


PARSER = Path(__file__).resolve().parents[1] / "web/scripts/parse-deploy-output.mjs"
URL = "https://rtp-exact-sha-test.vercel.app"
DEPLOYMENT = {"id": "dpl_NewProduction456", "url": URL, "inspectorUrl": "https://vercel.com/project/deploy",
              "readyState": "READY", "target": "production",
              "deploymentApiUrl": "https://api.vercel.com/v13/deployments/dpl_NewProduction456"}


def parse(value: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["node", str(PARSER)], input=value, text=True, capture_output=True, check=False)


@pytest.mark.parametrize("value", [
    URL, URL + "/", URL + "\r\n", f"Production {URL}",
    f"\x1b[2K\x1b[1G  \x1b[1mProduction      \x1b[22m \x1b[36m{URL}\x1b[39m\r\n",
    f"\x1b[?25l\x1b[2K\r  Production      {URL}\x1b[?25h",
    json.dumps(DEPLOYMENT, indent=2),
    json.dumps({"status": "ok", "deployment": DEPLOYMENT, "message": "Deployment ready.",
                "next": [{"command": f"vercel curl {URL}", "when": "Verify deployment"}]}),
])
def test_accepts_only_explicit_machine_or_single_line_legacy_forms(value):
    result = parse(value)
    assert result.returncode == 0, result.stderr
    assert result.stdout == URL
    assert result.stderr == ""


@pytest.mark.parametrize("value", [
    "", "\n", "not a URL", "Preview " + URL, "Aliased " + URL,
    URL + "\n" + URL, "Production " + URL + "\n" + URL,
    "Production " + URL + " https://other.vercel.app",
    "notice: deployment is " + URL,
    "https://rtp.vercel.app.evil.example", "https://one.two.vercel.app",
    "http://rtp.vercel.app", "https://rtp.vercel.app:443", "https://user@rtp.vercel.app",
    "https://rtp.vercel.app/path", "https://rtp.vercel.app?token=private", "https://rtp.vercel.app#fragment",
    "https://-rtp.vercel.app", "https://rtp-.vercel.app", "https://" + "x" * 64 + ".vercel.app",
    "https://rtp\x1b[0m-exact-sha-test.vercel.app",
    "\x1b]8;;https://evil.example\x07" + URL + "\x1b]8;;\x07",
    URL + "\x08", URL + "\x1b[1A", "Production " + URL + "\rhttps://other.vercel.app",
    "x" * 16385,
    json.dumps([DEPLOYMENT]), json.dumps({"url": URL}),
    json.dumps({"status": "error", "deployment": DEPLOYMENT}),
    json.dumps({"status": "ok", "deployment": DEPLOYMENT, "url": "https://other.vercel.app"}),
    json.dumps({**DEPLOYMENT, "target": "preview"}), json.dumps({**DEPLOYMENT, "readyState": "BUILDING"}),
    json.dumps({**DEPLOYMENT, "id": "../../unexpected"}),
    json.dumps({**DEPLOYMENT, "deploymentApiUrl": "https://evil.example/deployments"}),
    json.dumps({**DEPLOYMENT, "error": "Build failed"}),
    json.dumps(DEPLOYMENT)[:-1] + ', "url": "https://other.vercel.app"}',
    json.dumps(DEPLOYMENT)[:-1] + ', "\\u0075rl": "https://other.vercel.app"}',
    json.dumps(DEPLOYMENT) + "\n" + json.dumps(DEPLOYMENT),
])
def test_rejects_ambiguous_injected_untrusted_or_nonready_output(value):
    result = parse(value)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Deployment output diagnostic:" in result.stderr
    assert URL not in result.stderr and "evil.example" not in result.stderr


@pytest.mark.parametrize("value", [
    "npm warning https://secret-user:SECRET_TOKEN@registry.example/private-path",
    '{"private":"SECRET_TOKEN", broken',
    "\x1b[2KProduction https://rtp.vercel.app?token=SECRET_TOKEN",
])
def test_failure_diagnostic_preserves_structure_without_raw_values(value):
    result = parse(value)
    diagnostic = json.loads(result.stderr.removeprefix("Deployment output diagnostic: "))
    assert diagnostic["bytes"] == len(value.encode())
    assert diagnostic["lines"] == 1
    assert diagnostic["ansi"] == ("\x1b" in value)
    assert "SECRET_TOKEN" not in result.stderr
    assert "secret-user" not in result.stderr and "private-path" not in result.stderr
