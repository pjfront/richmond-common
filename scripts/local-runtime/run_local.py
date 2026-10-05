"""Portable, loopback-only Richmond archive runner. Never reads production .env."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = Path(__file__).resolve().parents[2]
WORKSPACE = REPOSITORY.parent
DEFAULT_RUNTIME = WORKSPACE / "local-runtime"
BACKUP = WORKSPACE / "local-backups" / "2026-10-04"
PG_BIN = BACKUP / "tooling" / "pgsql" / "bin"
CLUSTER = BACKUP / "restore-test" / "cluster"
DATABASE = "richmond_restore"
PORTS = {"postgres": 59876, "postgrest": 59877, "proxy": 59878, "web": 3100}
POSTGREST_URL = "https://github.com/PostgREST/postgrest/releases/download/v16.4/postgrest-v16.4-windows-x86-64.zip"
POSTGREST_SHA256 = "29a5b56e5a09b7168bb552ef14aa7ade40bf0a81dd0687cffa86610187b89d78"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SAFE_ENV_NAMES = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERNAME", "USERDOMAIN", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "SYSTEMDRIVE"}
READ_RPCS = {"search_site", "get_category_stats", "get_controversial_items", "get_meeting_flag_counts", "get_official_voting_record", "list_public_tables", "get_meeting_coverage_stats"}


def safe_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV_NAMES}


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def token(secret: str, role: str, issued: int) -> str:
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64(json.dumps({"iss": "richmond-local-archive", "role": role, "iat": issued, "exp": issued + 365 * 86400}, separators=(",", ":")).encode())
    message = f"{header}.{payload}"
    return message + "." + b64(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest())


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def private_dirs(runtime: Path) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        user = f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"
        result = subprocess.run(["icacls", str(runtime), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True, creationflags=NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Could not restrict the runtime directory permissions")
    else:
        runtime.chmod(0o700)
    for name in ("config", "logs", "tooling"):
        (runtime / name).mkdir(exist_ok=True)


def load_secrets(runtime: Path) -> dict:
    path = runtime / "config" / "secrets.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    issued = int(time.time())
    secret = secrets.token_urlsafe(48)
    data = {"version": 1, "issued_at": issued, "postgres_password": secrets.token_urlsafe(36), "authenticator_password": secrets.token_urlsafe(36), "jwt_secret": secret, "anon_key": token(secret, "anon", issued), "service_role_key": token(secret, "service_role", issued), "operator_password": secrets.token_urlsafe(30), "operator_session_password": secrets.token_urlsafe(48)}
    write_json(path, data)
    return data


def private_run(args: list[str], runtime: Path, log_name: str, *, env: dict | None = None, stdin: bytes | None = None) -> None:
    with (runtime / "logs" / log_name).open("ab") as log:
        result = subprocess.run(args, input=stdin, stdout=log, stderr=log, env=env or safe_env(), creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f"Local command failed; inspect restricted logs/{log_name}")


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def wait_port(port: int, process: subprocess.Popen | None = None, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("Local process stopped before its listener became ready; inspect private logs")
        if port_open(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Local port {port} did not become ready")


def prepare_binary(runtime: Path) -> Path:
    archive = runtime / "tooling" / "postgrest-v16.4-windows-x86-64.zip"
    if not archive.exists():
        request = urllib.request.Request(POSTGREST_URL, headers={"User-Agent": "Richmond-local-archive"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    with archive.open("rb") as archive_input:
        actual = hashlib.file_digest(archive_input, "sha256").hexdigest()
    if actual != POSTGREST_SHA256:
        raise RuntimeError("Official PostgREST ZIP hash did not match; executable was not launched")
    target = runtime / "tooling" / "postgrest"
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            resolved = (target / member.filename).resolve()
            if not resolved.is_relative_to(target.resolve()):
                raise RuntimeError("Unexpected archive member path")
            if member.is_dir():
                resolved.mkdir(parents=True, exist_ok=True)
                continue
            if resolved.is_file():
                with resolved.open("rb") as existing, package.open(member) as original:
                    if hashlib.file_digest(existing, "sha256").digest() == hashlib.file_digest(original, "sha256").digest():
                        continue
            package.extract(member, target)
    candidates = list(target.rglob("postgrest.exe"))
    if len(candidates) != 1:
        raise RuntimeError("Official package did not contain exactly one PostgREST executable")
    write_json(runtime / "config" / "tooling-verification.json", {"url": POSTGREST_URL, "sha256": actual, "verified": True, "executable": str(candidates[0])})
    return candidates[0]


def pg_env(runtime: Path) -> dict[str, str]:
    data = load_secrets(runtime)
    # Credentials go to a restricted file, never process arguments or stdout.
    pgpass = runtime / "config" / "pgpass.private"
    pgpass.write_text(f"127.0.0.1:{PORTS['postgres']}:*:postgres:{data['postgres_password']}\n", encoding="utf-8")
    result = safe_env()
    result["PGPASSFILE"] = str(pgpass)
    return result


def pg_start(runtime: Path) -> None:
    if port_open(PORTS["postgres"]):
        private_run([str(PG_BIN / "pg_ctl.exe"), "status", "-D", str(CLUSTER)], runtime, "pg-status.private.log")
        return
    private_run([str(PG_BIN / "pg_ctl.exe"), "start", "-D", str(CLUSTER), "-l", str(runtime / "logs" / "postgres.private.log"), "-w", "-t", "30"], runtime, "pg-start.private.log")
    wait_port(PORTS["postgres"])


def bootstrap_database(runtime: Path) -> None:
    marker = runtime / "config" / "database-initialized.json"
    if marker.exists():
        return
    if port_open(PORTS["postgres"]) or (CLUSTER / "postmaster.pid").exists():
        raise RuntimeError("Initial local credential reset requires the restored cluster to be stopped")
    data = load_secrets(runtime)
    sql = f"ALTER ROLE postgres PASSWORD '{data['postgres_password']}';\n".encode()
    # Single-user mode has no TCP listener and does not require an old password.
    private_run([str(PG_BIN / "postgres.exe"), "--single", "-D", str(CLUSTER), "postgres"], runtime, "credential-reset.private.log", stdin=sql)
    pg_start(runtime)
    allowed = ", ".join("'" + name + "'" for name in sorted(READ_RPCS))
    bootstrap = f"""\
DO $roles$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='richmond_local_authenticator') THEN
    CREATE ROLE richmond_local_authenticator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $roles$;
ALTER ROLE richmond_local_authenticator PASSWORD '{data['authenticator_password']}';
ALTER ROLE richmond_local_authenticator SET default_transaction_read_only=on;
ALTER ROLE anon NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE service_role NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE anon SET default_transaction_read_only=on;
ALTER ROLE service_role SET default_transaction_read_only=on;
GRANT anon, service_role TO richmond_local_authenticator;
GRANT CONNECT ON DATABASE {DATABASE} TO richmond_local_authenticator;
CREATE SCHEMA IF NOT EXISTS local_runtime AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA local_runtime FROM PUBLIC;
GRANT USAGE ON SCHEMA local_runtime TO anon, service_role, richmond_local_authenticator;
CREATE OR REPLACE FUNCTION local_runtime.guard_read_request() RETURNS void
LANGUAGE plpgsql AS $guard$
DECLARE method text := current_setting('request.method', true);
        path text := current_setting('request.path', true);
        name text;
BEGIN
  IF path LIKE '/rpc/%' THEN
    name := substring(path from 6);
    IF method NOT IN ('GET','HEAD','POST') OR name NOT IN ({allowed}) THEN
      RAISE insufficient_privilege USING MESSAGE='This RPC is unavailable in the local read-only archive';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='public' AND p.proname=name AND p.provolatile IN ('s','i')) THEN
      RAISE insufficient_privilege USING MESSAGE='Local RPC is not a verified read operation';
    END IF;
  ELSIF method NOT IN ('GET','HEAD') THEN
    RAISE insufficient_privilege USING MESSAGE='Database mutations are disabled in the local archive';
  END IF;
END $guard$;
REVOKE ALL ON FUNCTION local_runtime.guard_read_request() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION local_runtime.guard_read_request() TO anon, service_role;
"""
    sql_file = runtime / "config" / "bootstrap.private.sql"
    sql_file.write_text(bootstrap, encoding="utf-8")
    private_run([str(PG_BIN / "psql.exe"), "-X", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", str(PORTS["postgres"]), "-U", "postgres", "-d", DATABASE, "-f", str(sql_file)], runtime, "database-bootstrap.private.log", env=pg_env(runtime))
    write_json(marker, {"database": DATABASE, "host": "127.0.0.1", "port": PORTS["postgres"], "local_roles_only": True, "snapshot_rows_modified": False, "vector_available": False})


def write_configs(runtime: Path) -> None:
    data = load_secrets(runtime)
    pgrst = runtime / "config" / "postgrest.private.conf"
    pgrst.write_text(f'''db-uri = "postgresql://richmond_local_authenticator:{data['authenticator_password']}@127.0.0.1:{PORTS['postgres']}/{DATABASE}"
db-schemas = "public"
db-extra-search-path = "public,extensions"
db-anon-role = "anon"
db-pre-request = "local_runtime.guard_read_request"
db-config = false
db-max-rows = 1000
jwt-secret = "{data['jwt_secret']}"
server-host = "127.0.0.1"
server-port = {PORTS['postgrest']}
server-cors-allowed-origins = "http://127.0.0.1:{PORTS['web']},http://localhost:{PORTS['web']}"
openapi-mode = "disabled"
log-level = "error"
''', encoding="utf-8")
    write_json(runtime / "config" / "proxy.json", {"host": "127.0.0.1", "port": PORTS["proxy"], "upstreamHost": "127.0.0.1", "upstreamPort": PORTS["postgrest"], "webPort": PORTS["web"], "readRpcs": sorted(READ_RPCS)})


def copy_web(runtime: Path, source: Path, web_port: int = PORTS["web"]) -> None:
    source = source.resolve()
    if not (source / "package.json").is_file() or not (source / "src").is_dir():
        raise RuntimeError("Source must be the reviewed checkout's web directory")
    destination = runtime / "web"
    if destination.resolve().parent != runtime.resolve() or destination.resolve() == source:
        raise RuntimeError("Unsafe local web copy target")
    if port_open(web_port):
        raise RuntimeError("Stop the local web process before updating its isolated source copy")
    if (destination / "node_modules").exists():
        os.rmdir(destination / "node_modules")  # Remove only the directory junction, never its target.
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("node_modules", ".next", ".vercel", ".git", ".env*", "coverage", "out", "*.log"))
    modules = source / "node_modules"
    if not modules.is_dir():
        raise RuntimeError("Reviewed source node_modules are required; runner does not install packages")
    target = destination / "node_modules"
    # The fixed, validated target is inside the restricted runtime directory.
    command = f"New-Item -ItemType Junction -Path '{str(target).replace(chr(39), chr(39)*2)}' -Target '{str(modules).replace(chr(39), chr(39)*2)}' | Out-Null"
    private_run(["powershell", "-NoProfile", "-Command", command], runtime, "node-modules-junction.private.log")
    write_json(runtime / "config" / "source-copy.json", {"source_web": str(source), "copied_at": int(time.time()), "excluded": [".env*", ".vercel", ".next", "node_modules"], "node_modules_junction": str(modules)})


def web_env(runtime: Path) -> dict[str, str]:
    data = load_secrets(runtime)
    env = safe_env()
    env.update({"NODE_ENV": "development", "NEXT_TELEMETRY_DISABLED": "1", "NEXT_PUBLIC_SITE_URL": f"http://127.0.0.1:{PORTS['web']}", "NEXT_PUBLIC_SUPABASE_URL": f"http://127.0.0.1:{PORTS['proxy']}", "NEXT_PUBLIC_SUPABASE_ANON_KEY": data["anon_key"], "SUPABASE_SERVICE_ROLE_KEY": data["service_role_key"], "OPERATOR_PASSWORD": data["operator_password"], "IRON_SESSION_PASSWORD": data["operator_session_password"], "SITE_ACCESS_REQUIRED": "false", "RICHMOND_API_BUDGET_LOCK": "true", "RICHMOND_API_MONTHLY_CAP_USD": "0", "RICHMOND_READ_ONLY_STAGE": "false", "RICHMOND_LOCAL_ARCHIVE": "true", "RICHMOND_FEATURE_PROFILE": "local_archive", "RICHMOND_BUILD_USES_PRODUCTION_DATA": "false"})
    return env


def launch(args: list[str], runtime: Path, log_name: str, *, env: dict | None = None, cwd: Path | None = None) -> subprocess.Popen:
    with (runtime / "logs" / log_name).open("ab") as log:
        return subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env or safe_env(), cwd=cwd, creationflags=NO_WINDOW)


def start(runtime: Path, include_web: bool) -> dict:
    pg_start(runtime)
    state_path = runtime / "config" / "processes.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    executable = Path(json.loads((runtime / "config" / "tooling-verification.json").read_text())["executable"])
    if not port_open(PORTS["postgrest"]):
        env = safe_env()
        env["PATH"] = str(PG_BIN) + os.pathsep + env.get("PATH", "")
        process = launch([str(executable), str(runtime / "config" / "postgrest.private.conf")], runtime, "postgrest.private.log", env=env)
        state["postgrest"] = {"pid": process.pid, "command_contains": str(executable)}
        write_json(state_path, state)
        wait_port(PORTS["postgrest"], process)
    node = shutil.which("node")
    if not node:
        raise RuntimeError("An existing Node installation is required")
    if not port_open(PORTS["proxy"]):
        proxy = Path(__file__).with_name("proxy.cjs")
        process = launch([node, str(proxy), str(runtime / "config" / "proxy.json")], runtime, "proxy.private.log")
        state["proxy"] = {"pid": process.pid, "command_contains": str(proxy)}
        write_json(state_path, state)
        wait_port(PORTS["proxy"], process)
    if include_web:
        web = runtime / "web"
        next_bin = web / "node_modules" / "next" / "dist" / "bin" / "next"
        if not next_bin.is_file():
            raise RuntimeError("Prepare the isolated web source after the feature profile is ready")
        if not port_open(PORTS["web"]):
            # Webpack supports the intentionally external node_modules junction.
            process = launch([node, str(next_bin), "dev", "--webpack", "--hostname", "127.0.0.1", "--port", str(PORTS["web"])], runtime, "web.private.log", env=web_env(runtime), cwd=web)
            state["web"] = {"pid": process.pid, "command_contains": str(next_bin)}
            write_json(state_path, state)
            wait_port(PORTS["web"], process, timeout=60)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTS['web']}/", timeout=120) as response:
                    response.read()
                    if response.status != 200:
                        raise RuntimeError("Local home page did not render successfully")
                if process.poll() is not None:
                    raise RuntimeError("Local web process stopped after its initial listener appeared")
            except urllib.error.URLError as error:
                raise RuntimeError("Local home page did not become healthy; inspect private web log") from error
    write_json(state_path, state)
    return status(runtime)


def stop(runtime: Path, infrastructure: bool = True) -> dict:
    path = runtime / "config" / "processes.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for name in (("web", "proxy", "postgrest") if infrastructure else ("web",)):
        entry = state.get(name)
        if not entry:
            continue
        pid = int(entry["pid"])
        # Verify the saved PID still belongs to the exact runner command before killing it.
        check = subprocess.run(["powershell", "-NoProfile", "-Command", f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if($p){{$p.CommandLine}}"], capture_output=True, text=True, creationflags=NO_WINDOW)
        command = check.stdout.strip()
        if command and entry["command_contains"].lower() not in command.lower():
            raise RuntimeError("Saved PID belongs to a different process; refusing to stop it")
        if command:
            private_run(["taskkill", "/PID", str(pid), "/T", "/F"], runtime, "stop-process.private.log")
        state.pop(name, None)
    if infrastructure and port_open(PORTS["postgres"]):
        private_run([str(PG_BIN / "pg_ctl.exe"), "stop", "-D", str(CLUSTER), "-m", "fast", "-w", "-t", "30"], runtime, "pg-stop.private.log")
    write_json(path, state)
    return status(runtime)


def status(runtime: Path) -> dict:
    state_path = runtime / "config" / "processes.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    return {"runtime": str(runtime), "host": "127.0.0.1", "ports": PORTS, "listening": {name: port_open(port) for name, port in PORTS.items()}, "process_ids": {name: entry["pid"] for name, entry in state.items()}, "cloud_keys_loaded": False, "model_calls_allowed": False, "email_calls_allowed": False, "vector_available": False, "web_url": f"http://127.0.0.1:{PORTS['web']}"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "start", "stop", "stop-web", "status"))
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--source-web", type=Path)
    parser.add_argument("--infrastructure-only", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if runtime == WORKSPACE.resolve() or not runtime.is_relative_to(WORKSPACE.resolve()):
        raise RuntimeError("Runtime must be a dedicated directory inside the intended workspace")
    if args.action == "prepare":
        private_dirs(runtime)
        load_secrets(runtime)
        prepare_binary(runtime)
        bootstrap_database(runtime)
        write_configs(runtime)
        if args.source_web:
            copy_web(runtime, args.source_web)
        result = {"prepared": True, "runtime": str(runtime), "official_binary_sha256_verified": True, "cloud_keys_loaded": False}
    elif args.action == "start":
        result = start(runtime, not args.infrastructure_only)
    elif args.action == "stop":
        result = stop(runtime)
    elif args.action == "stop-web":
        result = stop(runtime, infrastructure=False)
    else:
        result = status(runtime)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print subprocess output, passwords, URLs containing passwords, or private records.
        log_directory = DEFAULT_RUNTIME / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        with (log_directory / "runner-errors.private.log").open("a", encoding="utf-8") as error_log:
            traceback.print_exc(file=error_log)
        print(f"Local runner failed: {type(error).__name__}. Inspect restricted runtime logs.", file=sys.stderr)
        sys.exit(1)
