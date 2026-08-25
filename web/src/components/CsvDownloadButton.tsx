'use client'

import Link from 'next/link'

type CsvValue = string | number | null

interface CsvDownloadButtonProps {
  filename: string
  columns: readonly string[]
  rows: ReadonlyArray<Record<string, CsvValue>>
}

export function escapeCsv(value: CsvValue): string {
  let text = value === null ? '' : String(value)
  // Spreadsheet engines can treat both ASCII and normalized full-width
  // operators as formulas. Leading control whitespace can expose the same
  // interpretation, so neutralize it before RFC 4180 quoting.
  if (typeof value === 'string' && /^[=+\-@\t\r\n\uFF0B\uFF0D\uFF1D\uFF20]/u.test(text)) {
    text = `'${text}`
  }
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/** Download caller-provided filing rows with stable technical column names. */
export default function CsvDownloadButton({
  filename,
  columns,
  rows,
}: CsvDownloadButtonProps) {
  function download() {
    const lines = [
      columns.join(','),
      ...rows.map((row) => columns.map((column) => escapeCsv(row[column] ?? null)).join(',')),
    ]
    const blob = new Blob([`${lines.join('\r\n')}\r\n`], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={download}
        className="inline-flex min-h-11 items-center rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-civic-navy hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
      >
        Download CSV
      </button>
      <Link
        href="/elections/methodology#campaign-record-csv-field-guide"
        className="inline-flex min-h-11 items-center rounded-sm px-2 text-sm font-medium text-civic-navy-light hover:text-civic-navy hover:underline focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
      >
        CSV field guide
      </Link>
    </div>
  )
}
