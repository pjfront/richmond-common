/**
 * Skip Vercel Preview builds until the exact Git branch has an approved,
 * branch-scoped Supabase Preview environment.
 *
 * Vercel's Ignored Build Step uses exit code 0 to skip and any non-zero exit
 * code to continue. Production remains an explicit deployment path and is
 * never blocked here; `assert-preview-env.mjs` remains the fail-closed
 * credential guard once an approved Preview build starts.
 */

const environment = (process.env.VERCEL_ENV ?? '').trim()
const actualGitBranch = (process.env.VERCEL_GIT_COMMIT_REF ?? '').trim()
const approvedGitBranch = (
  process.env.RICHMOND_PREVIEW_GIT_BRANCH ?? ''
).trim()

if (environment === 'production') {
  console.log('Vercel build gate: production deployment may continue.')
  process.exit(1)
}

if (environment !== 'preview') {
  console.log(
    'Vercel build gate: skipped because this is not a recognized Preview deployment.',
  )
  process.exit(0)
}

if (isAutomationBranch(actualGitBranch)) {
  console.log(
    `Vercel build gate: skipped automation branch ${actualGitBranch || '(missing)'}.`,
  )
  process.exit(0)
}

if (!actualGitBranch || approvedGitBranch !== actualGitBranch) {
  console.log(
    'Vercel build gate: skipped unapproved Preview branch. Bootstrap a bounded Supabase Preview before requesting a live deployment.',
  )
  process.exit(0)
}

console.log(
  `Vercel build gate: approved Preview branch ${actualGitBranch} may continue.`,
)
process.exit(1)

function isAutomationBranch(branch) {
  return (
    branch === 'heartbeat' ||
    branch.startsWith('automation/') ||
    branch.startsWith('automation-')
  )
}
