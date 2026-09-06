import Link from 'next/link'
import { CivicDate, Localized } from '@/components/civic/CivicLanguage'
import { formatReportedMoney as money, reportedCents } from '@/lib/reported-money'
import { JIMENEZ_FINANCE as report, JIMENEZ_MONEY_PATH, jimenezDonationPeriods, jimenezPeriodTotal } from '@/lib/jimenez-finance'

export default function JimenezFinanceSummary() {
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
    <Link href={JIMENEZ_MONEY_PATH} className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">
      <Localized en="See the donations, calculation and original reports →" es="Ver las donaciones, el cálculo y los informes originales →" />
    </Link>
  </div>
}
