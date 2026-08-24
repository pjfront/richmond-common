# Windows launcher for the exact-SHA production deploy gate.
#
# Windows' bare `bash` command may resolve to WSL instead of Git for Windows.
# Pin the reviewed shell already installed on the operator machine, then let
# deploy-prod.sh perform every source, CI, target, and approval-bound check.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string] $ApprovedSha
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$gitBashPath = 'C:\Program Files\Git\bin\bash.exe'
$deployScriptPath = Join-Path -Path $PSScriptRoot -ChildPath 'deploy-prod.sh'

if (-not (Test-Path -LiteralPath $gitBashPath -PathType Leaf)) {
    Write-Error "ACTION: Install Git for Windows at the standard path, then rerun this same command. Required shell not found."
    exit 1
}
if (-not (Test-Path -LiteralPath $deployScriptPath -PathType Leaf)) {
    Write-Error "ACTION: Restore web/scripts/deploy-prod.sh from the approved clean checkout, then rerun."
    exit 1
}

& $gitBashPath $deployScriptPath $ApprovedSha
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
