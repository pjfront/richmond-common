'use client'

type CsvValue = string | number | null

interface CsvDownloadButtonProps {
  filename: string
  columns: readonly string[]
  rows: ReadonlyArray<Record<string, CsvValue>>
}

export function escapeCsv(value: CsvValue): string {
  let text = value === null ? '' : String(value)
  if (typeof value === 'string' && /^[=+\-@]/.test(text)) {
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
    <button
      type="button"
      onClick={download}
      className="inline-flex min-h-11 items-center rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-civic-navy hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
    >
      Download CSV
    </button>
  )
}
