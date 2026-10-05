# Richmond Commons on this computer

This runner uses the preserved local PostgreSQL 17 cluster, official portable Windows PostgREST, a small `/rest/v1` compatibility proxy, and an isolated Next.js source copy. All listeners bind to `127.0.0.1`; it creates no Windows service and must never be exposed through a public tunnel or port forwarding.

The encrypted original backup is unchanged. The restored test cluster receives fresh local passwords, a local API login, and a read-only API guard; no civic record rows are modified. Supabase cloud keys, model keys, email keys and webhook secrets are never loaded. The local service-role key belongs only to this isolated database, stays server-side, and cannot authorize cloud access.

From the reviewed repository root:

```powershell
python scripts/local-runtime/run_local.py prepare
# Copy web only after the local feature profile is ready.
python scripts/local-runtime/run_local.py prepare --source-web ./web
python scripts/local-runtime/run_local.py start
python scripts/local-runtime/run_local.py status
python scripts/local-runtime/run_local.py stop
```

Read-flow and isolation checks (no record payloads or credentials are printed):

```powershell
python scripts/local-runtime/verify_local.py
python -m unittest discover -s scripts/local-runtime -p test_run_local.py
node --test scripts/local-runtime/proxy.test.cjs
```

The verified local edition serves the home/search/library, campaign records with their partial coverage, an ordinary item with motions and roll calls, the known J-2 source-review hold, and operator cookie login with settings/sync/recap GET views. The legacy search endpoint falls back to keyword results. Writes and email requests are blocked. These checks verify representative flows; they do not establish that every archived dashboard or managed Supabase function works. Startup readiness requires a rendered home HTTP 200 and a surviving Next process, beyond an open TCP port. Full stop/start has also been exercised.

`start --infrastructure-only` launches the database, REST service and proxy without Next. `stop-web` stops only Next when updating the source copy, leaving the database available for separate approved local work. Prepare is repeatable: existing local secrets are retained, and the old database password is reset only on the first preparation while the cluster is stopped. The source copy excludes `.env*`, `.vercel`, `.next` and dependencies; its `node_modules` is a junction to the reviewed checkout's existing dependencies. Next uses `dev --webpack` because Turbopack rejects this external junction. Stop before recopying source. Do not run prepare against the original live database or alter the canonical backup.

Default paths and ports:

| Component | Address / location |
|---|---|
| Local page | `http://127.0.0.1:3100` |
| PostgreSQL | `127.0.0.1:59876`, database `richmond_restore` |
| PostgREST | `127.0.0.1:59877` |
| Supabase REST compatibility proxy | `127.0.0.1:59878/rest/v1/` |
| Runtime source/config/logs | `E:/Projectz/RichmondTransparencyProject/local-runtime/` |
| Local secrets | `local-runtime/config/secrets.json` — restricted to this Windows user and SYSTEM; never commit/share |
| Preserved cluster | `local-backups/2026-10-04/restore-test/cluster/` |

The local page has no public site password prompt because it is available only on loopback. Operator cookie login uses a separate freshly generated local operator password in the restricted secrets file. Operator access cannot enable database writes. Database/API mutations, unknown RPCs, unrelated proxy paths and cross-origin requests outside the two configured localhost origins are rejected. The read-only database RPC list is explicit in the runner; the API guard additionally requires each allowed function to be STABLE or IMMUTABLE. Existing RLS is retained; the original cloud role capabilities have not been reproduced.

The local environment defaults to `RICHMOND_LOCAL_ARCHIVE=true`, `RICHMOND_FEATURE_PROFILE=local_archive`, `RICHMOND_READ_ONLY_STAGE=false`, `RICHMOND_API_BUDGET_LOCK=true` and a zero API budget. No paid inference or email delivery is supported by this runner. Do not place production `.env` files inside the isolated source copy. Logs may contain database/application records and stay in the restricted runtime directory.

Native pgvector, Vault and the full managed Supabase service stack are unavailable. The verified restoration preserves 125 non-vector/application/managed table loads; full API/RLS service behavior still requires verification. Keyword search and the bounded natural-language grammar do not need a model. The optional similar-discussion panel must stay disabled until a compatible pgvector runtime and its archived data are restored. A later local embedding model cannot be compared directly with the existing `text-embedding-3-small` 1,536-dimensional vectors; changing models needs a separate versioned index and validation.

For the separately approved compact measurement database, `verify_core_http.py` temporarily launches loopback REST ports 59879/59880, then stops them. Run it only after `scripts/basic-core` has created `basic_core_measure_20261004`; it adds local read-guard metadata to that disposable database, never source rows. The compact PostgREST config uses `db-extra-search-path=public` because this database has no Supabase `extensions` schema. `verify_basic_app.py` then runs a separate Next instance on 3101 with profile `basic_public`, stage reads only, an anon key and no service-role/operator/model/email credentials. It checks home/search, actual housing/vote results, finance page/complete snapshot CSV, meeting/detail links, J-2 suppression and disabled APIs, then stops all temporary processes. The user edition on 3100 stays available. These are local HTTP checks; browser verification is recorded separately by the parent task. Safe aggregate reports are saved under `local-runtime/config/`; application logs stay private. No cloud deployment or claim about a future hosted database is implied.

PostgREST v16.4 is downloaded only from its [official release](https://github.com/PostgREST/postgrest/releases/tag/v16.4); SHA-256 is pinned and verified before extraction/launch: `29a5b56e5a09b7168bb552ef14aa7ade40bf0a81dd0687cffa86610187b89d78`. The runner uses only portable executables and existing Python/Node; no Docker, Linux distro, compiler or model is installed. The existing snapshot's date limits, finance coverage limitations and known source-review holds remain product requirements, independent of hosting.
