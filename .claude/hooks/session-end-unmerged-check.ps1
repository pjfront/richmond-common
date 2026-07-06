# SessionEnd hook: surface unmerged commits so work doesn't pile up on
# feature branches. The foundational tenet is that discipline-based rules
# decay silently — this is the tooling enforcement.
#
# Prints a status block: clean, or UNMERGED with commit list + whether a
# PR already exists for this branch. The AI reads this at session end and
# acts — either creates a PR or explains why work is staying on the branch.

$ErrorActionPreference = 'Stop'

$repoRoot = $env:CLAUDE_PROJECT_DIR
if (-not $repoRoot) {
  $repoRoot = git rev-parse --show-toplevel 2>$null
}
if (-not $repoRoot) { exit 0 }

Push-Location $repoRoot
try {
  $branch = git branch --show-current 2>$null
  if (-not $branch -or $branch -eq 'main') { exit 0 }

  $count = git rev-list --count "main..HEAD" 2>$null
  if (-not $count -or $count -eq '0') { exit 0 }

  $commits = git log --oneline "main..HEAD" 2>$null
  $prUrl = gh pr list --head $branch --json url --jq '.[0].url' 2>$null

  Write-Host ""
  Write-Host "╔══════════════════════════════════════════════════════════╗"
  Write-Host "║  UNMERGED COMMITS ON BRANCH: $branch".PadRight(56) + "║"
  Write-Host "╠══════════════════════════════════════════════════════════╣"
  foreach ($line in ($commits -split "`n")) {
    $trimmed = $line.Trim()
    if ($trimmed) {
      Write-Host ("║  " + $trimmed).PadRight(56) + "║"
    }
  }
  Write-Host "╠══════════════════════════════════════════════════════════╣"
  if ($prUrl) {
    Write-Host ("║  PR: $prUrl").PadRight(56) + "║"
  } else {
    Write-Host "║  NO OPEN PR — create one before ending session".PadRight(56) + "║"
  }
  Write-Host "╚══════════════════════════════════════════════════════════╝"
  Write-Host ""
} finally {
  Pop-Location
}