import Link from 'next/link'
import { CivicDate, Localized } from '@/components/civic/CivicLanguage'
import { formatReportedMoney as money, reportedCents } from '@/lib/reported-money'
import type { CandidateFilingCoverage } from '@/data/anderson-paper-filings'
import { JIMENEZ_FINANCE as report, JIMENEZ_MONEY_PATH, jimenezDonationPeriods, jimenezPeriodTotal, hasNewJimenezReports } from '@/lib/jimenez-finance'

export function JimenezReportFreshness({ coverage }: { coverage: CandidateFilingCoverage }) {
  const reviewedIds = new Set(report.sources.map(source => source.filing_id))
  const newReport = coverage.latestPeriodic.id !== report.periodic.filing_id ? coverage.latestPeriodic
    : coverage.recentRapid.find(source => !reviewedIds.has(source.id))
  if (hasNewJimenezReports(coverage)) return <p role="status" className="mt-3 text-sm text-slate-700">
    <Localized en="A newer report is available. These figures keep their original dates while we check it."
      es="Hay un informe más reciente. Estas cifras conservan sus fechas originales mientras lo revisamos." />{' '}
    <a href={newReport!.sourceUrl} className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">
      <Localized en="See the official report" es="Ver el informe oficial" />
    </a>{' '}<Localized en="Report list checked " es="Lista de informes consultada el " /><CivicDate date={coverage.checkedAt.slice(0, 10)} />.
  </p>
  if (coverage.status !== 'available') return <p role="status" className="mt-3 text-sm text-slate-700">
    <Localized en="We couldn’t check for newer reports just now. These figures were checked against the originals on "
      es="No pudimos consultar informes más recientes. Estas cifras se cotejaron con los originales el " />
    <CivicDate date={report.reviewed_at.slice(0, 10)} />.
  </p>
  return <p className="mt-2 text-sm text-slate-600"><Localized en="Official report list checked " es="Lista de informes oficiales consultada el " />
    <CivicDate date={coverage.checkedAt.slice(0, 10)} />.
  </p>
}

export default function JimenezFinanceSummary({ coverage }: { coverage?: CandidateFilingCoverage } = {}) {
  const later = jimenezDonationPeriods().later
  const laterTotal = later.reduce((sum, receipt) => sum + reportedCents(receipt.amount), 0)
  return <div aria-label="Jimenez campaign finances" className="mt-5">
    <p className="text-sm font-medium text-slate-600"><Localized
      en="Cash donations reported · Jan 1–Jun 30, 2026"
      es="Donaciones monetarias declaradas · 1 de enero–30 de junio de 2026" /></p>
    <p className="mt-1 text-3xl font-semibold text-civic-navy">{money(jimenezPeriodTotal())}</p>
    <p className="mt-3 leading-relaxed text-slate-700"><Localized
      en={`Her campaign reported ${money(report.periodic.reported.ending_cash)} in cash left on June 30. It also reported ${money(report.periodic.reported.cumulative_noncash)} in noncash support through that date, separate from the cash donations.`}
      es={`Su campaña declaró ${money(report.periodic.reported.ending_cash)} de efectivo disponible al 30 de junio. También declaró ${money(report.periodic.reported.cumulative_noncash)} de apoyo no monetario hasta esa fecha, separado de las donaciones en efectivo.`} /></p>
    <p className="mt-3 leading-relaxed text-slate-700"><Localized
      en={`Five later donations totaling ${money(laterTotal)} were reported as received July 23–31. They do not provide a complete fundraising total since June.`}
      es={`Se declararon cinco donaciones posteriores por un total de ${money(laterTotal)}, recibidas del 23 al 31 de julio. No representan todo lo recaudado desde junio.`} /></p>
    <p className="mt-3 text-sm text-slate-600"><Localized
      en="Official campaign reports · AI source check " es="Informes oficiales de campaña · cotejo con IA " />
      <CivicDate date={report.reviewed_at.slice(0, 10)} />
    </p>
    {coverage && <JimenezReportFreshness coverage={coverage} />}
    <Link href={JIMENEZ_MONEY_PATH} className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">
      <Localized en="See the donations, calculation and original reports →" es="Ver las donaciones, el cálculo y los informes originales →" />
    </Link>
  </div>
}
