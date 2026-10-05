"""Pass only the local runner credential to the isolated refresh subprocess.

Never reads production dotenv, prints a URI/password, or exports credentials.
Default --plan does not open the private runtime credential file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

REPOSITORY = Path(__file__).resolve().parents[2]
RUNTIME = REPOSITORY.parent / "local-runtime"
SAFE_ENV = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "SYSTEMDRIVE"}


def main(args: list[str] | None = None) -> int:
    args = args if args is not None else sys.argv[1:]
    # The child CLI performs all profile/feature/date/step validation.
    env = {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV}
    env.update({"RICHMOND_FEATURE_PROFILE": "local_archive", "RICHMOND_LOCAL_ARCHIVE": "true",
                "RICHMOND_API_BUDGET_LOCK": "true", "RICHMOND_API_MONTHLY_CAP_USD": "0", "PYTHONIOENCODING": "utf-8"})
    if "--apply" in args:
        try:
            private = json.loads((RUNTIME / "config/secrets.json").read_text(encoding="utf-8"))
            password = private["postgres_password"]
            if not isinstance(password, str) or not password:
                raise ValueError
        except (OSError, ValueError, KeyError):
            print(json.dumps({"status": "blocked", "reason": "Start/bootstrap the local archive runtime before refreshing"}))
            return 2
        env["RICHMOND_LOCAL_DATABASE_URL"] = "postgresql://postgres:" + quote(password, safe="") + "@127.0.0.1:59876/richmond_restore"
    result = subprocess.run([sys.executable, str(REPOSITORY / "src/basic_refresh.py"), "--target", "local", "--profile", "local_archive", *args],
                            cwd=REPOSITORY, env=env, capture_output=True, text=True, encoding="utf-8")
    try:
        aggregate = json.loads(result.stdout)
    except ValueError:
        aggregate = {"status": "failed", "reason": "Local refresh did not return a safe aggregate report"}
    print(json.dumps(aggregate, indent=2))
    if "--apply" in args and (RUNTIME / "logs").is_dir():
        (RUNTIME / "logs/basic-refresh-aggregate.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
