param(
    [string]$ProjectRef = "ahrwvmizzykyyfavdvfv",
    [string]$SqlPath = "docs/audits/2026-08-08-supabase-24h-readonly.sql"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedSql = Join-Path $repoRoot $SqlPath
$envFile = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $resolvedSql -PathType Leaf)) {
    throw "Snapshot SQL not found: $resolvedSql"
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Repository .env not found. SUPABASE_ACCESS_TOKEN is required."
}

$tokenLine = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^SUPABASE_ACCESS_TOKEN=' } |
    Select-Object -First 1
if (-not $tokenLine) {
    throw "SUPABASE_ACCESS_TOKEN is not configured in the repository .env."
}

$token = (($tokenLine -split '=', 2)[1]).Trim().Trim('"').Trim("'")
if (-not $token) {
    throw "SUPABASE_ACCESS_TOKEN is empty."
}

$sql = Get-Content -LiteralPath $resolvedSql -Raw
$body = @{ query = [string]$sql; parameters = @() } | ConvertTo-Json -Compress
$uri = "https://api.supabase.com/v1/projects/$ProjectRef/database/query/read-only"

$response = Invoke-RestMethod -Method Post -Uri $uri -Headers @{
    Authorization = "Bearer $token"
} -ContentType "application/json" -Body $body

# The token is never emitted. The single returned JSON object is suitable for
# durable capture by Codex or CI artifacts without any production mutation.
$response | ConvertTo-Json -Depth 20
