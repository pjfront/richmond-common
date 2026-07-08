# Start PostgreSQL (embedded, bundled with Paperclip) then launch Paperclip
param(
    [int]$Port = 54329
)

$ErrorActionPreference = "Stop"
$PG_HOME = "$env:LOCALAPPDATA\nvm\v22.16.0\node_modules\paperclipai\node_modules\@embedded-postgres\windows-x64\native"
$PG_DATA = "$env:USERPROFILE\.paperclip\instances\default\db"
$PG_LOG = "$PG_DATA\pg.log"

# Check if already running
$existing = Get-Process -Name "postgres" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "PostgreSQL already running." -ForegroundColor Green
} else {
    Write-Host "Starting PostgreSQL on port $Port..." -ForegroundColor Cyan
    & "$PG_HOME\bin\pg_ctl.exe" start -D $PG_DATA -l $PG_LOG -o "-p $Port"
    Write-Host "PostgreSQL started." -ForegroundColor Green
}

Write-Host "Starting Paperclip..." -ForegroundColor Cyan
paperclipai run
