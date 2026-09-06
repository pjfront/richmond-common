import Link from 'next/link'
import type { CandidateFilingCoverage } from '@/data/anderson-paper-filings'
import { Localized } from '@/components/civic/CivicLanguage'
import { formatCivicDate } from '@/lib/november-election'
import { ANDERSON_FINANCE as report, ANDERSON_MONEY_PATH, andersonPeriodTotal, andersonSourcePage,
  andersonDonationPeriods, formatReportedMoney as money, hasNewAndersonReports } from '@/lib/anderson-finance'

const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'

export function AndersonReportFreshness({ coverage }: { coverage: CandidateFilingCoverage }) {
  const reviewedIds = new Set(report.sources.map(source => source.filing_id))
  const newReport = coverage.latestPeriodic.id !== report.periodic.filing_id ? coverage.latestPeriodic
    : coverage.recentRapid.find(source => !reviewedIds.has(source.id))
  if (hasNewAndersonReports(coverage)) return <p role="status" className="mt-3 text-sm text-slate-700"><Localized
    en="A newer report is available. These figures keep their original dates while we check the new report."
    es="Hay un informe más reciente. Estas cifras conservan sus fechas originales mientras revisamos el nuevo informe." />{' '}
    <a href={newReport!.sourceUrl} className={linkClass}><Localized en="See the official report" es="Ver el informe oficial" /></a></p>
  if (coverage.status !== 'available') return <p role="status" className="mt-3 text-sm text-slate-700"><Localized
    en="We couldn’t check for newer reports just now. These figures were checked against the original reports on September 6."
    es="No pudimos consultar informes más recientes. Estas cifras se cotejaron con los informes originales el 6 de septiembre." /></p>
  return null
}

export default function AndersonFinanceSummary({ coverage }: { coverage: CandidateFilingCoverage }) {
  const later = andersonDonationPeriods().later
  return <div aria-label="Anderson campaign finances" className="mt-5">
    <p className="text-sm font-medium text-slate-600"><Localized en="Cash donations reported · Jan 1–Jun 30, 2026" es="Donaciones monetarias declaradas · 1 de enero–30 de junio de 2026" /></p>
    <p className="mt-1 text-3xl font-semibold text-civic-navy">{money(andersonPeriodTotal())}</p>
    <p className="mt-3 leading-relaxed text-slate-700"><Localized
      en={`His campaign reported ${money(report.periodic.reported.ending_cash)} in cash left on June 30. Its latest report lists ${money(report.periodic.reported.payments)} spent from May 29 through June 30.`}
      es={`Su campaña declaró ${money(report.periodic.reported.ending_cash)} de efectivo disponible al 30 de junio. Su último informe declara ${money(report.periodic.reported.payments)} gastados del 29 de mayo al 30 de junio.`} /></p>
    <p className="mt-3 leading-relaxed text-slate-700"><Localized
      en="More recent donations: " es="Donaciones más recientes: " />{later.map((receipt, index) => <span key={receipt.filing_id}>
        {index > 0 && <Localized en=" and " es=" y " />}<a href={andersonSourcePage(receipt.filing_id, receipt.page)} className="underline underline-offset-4">{money(receipt.amount)} · {receipt.donor_name}</a>{' '}(<time dateTime={receipt.received_date}>{formatCivicDate(receipt.received_date)}</time>)
      </span>)}. <Localized en="These do not include every donation since June."
        es="No incluyen todas las donaciones desde junio." /></p>
    <p className="mt-3 text-sm text-slate-600"><Localized en="Official campaign reports · AI source check " es="Informes oficiales de campaña · cotejo con IA " /><time dateTime={report.reviewed_at}>{formatCivicDate(report.reviewed_at)}</time></p>
    <AndersonReportFreshness coverage={coverage} />
    <Link href={ANDERSON_MONEY_PATH} className={`${linkClass} mt-2`}><Localized en="See the donations, calculation and original reports →" es="Ver las donaciones, el cálculo y los informes originales →" /></Link>
  </div>
}
