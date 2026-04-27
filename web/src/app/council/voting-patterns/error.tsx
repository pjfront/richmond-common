'use client'

export default function VotingPatternsError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">
        How the Council Votes
      </h1>
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 mt-4">
        <h2 className="text-lg font-semibold text-red-800 mb-2">
          Couldn&apos;t load voting records
        </h2>
        <p className="text-sm text-red-700 mb-4">
          This page processes a large volume of voting records and may have
          timed out. Try again — it usually loads on the next attempt.
        </p>
        {error.message && (
          <p className="text-xs text-red-500 mb-4 font-mono">{error.message}</p>
        )}
        <button
          onClick={reset}
          className="px-4 py-2 bg-civic-navy text-white text-sm font-medium rounded hover:bg-civic-navy-light transition-colors"
        >
          Try again
        </button>
        {error.digest && (
          <p className="text-xs text-red-400 mt-3">Error ID: {error.digest}</p>
        )}
      </div>
    </div>
  )
}
