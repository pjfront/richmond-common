import { ANDERSON_FILER, type CandidateFilingCoverage } from '@/data/anderson-paper-filings'
import { formatCivicDate } from '@/lib/november-election'
import { Localized } from '@/components/civic/CivicLanguage'

const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'

export default function CandidatePaperCoverage({ coverage }: { coverage: CandidateFilingCoverage }) {
  const latest = coverage.latestPeriodic
  const checked = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Los_Angeles' }).format(new Date(coverage.checkedAt))
  return <aside aria-label="Anderson paper filing coverage" className="mt-5 border-t border-slate-200 pt-4">
    <h4 className="font-semibold text-civic-navy"><Localized en="Paper filings are outside this receipt index" es="Los informes en papel no están incluidos en este índice" /></h4>
    <p className="mt-2 text-sm leading-relaxed text-slate-700"><Localized
      en="Anderson’s committee (FPPC 1481105) has filed paper reports with the city. Their receipts are not included in this electronic transaction index. A missing subtotal here does not mean no money was raised."
      es="El comité de Anderson (FPPC 1481105) ha presentado informes en papel a la ciudad. Sus aportaciones no están incluidas en este índice de transacciones electrónicas. La falta de un subtotal aquí no significa que no haya recaudado dinero." /></p>
    {coverage.status !== 'available' && <p role="status" className="mt-2 text-sm text-slate-700"><Localized
      en={coverage.status === 'unavailable' ? 'The current filing check is unavailable. The dated, previously verified records remain below.' : 'A fresh filing check is pending. The last verified records remain below.'}
      es="La consulta actual no está disponible. A continuación se muestran los registros verificados anteriormente, con sus fechas." /></p>}
    <p className="mt-3 text-sm text-slate-600"><Localized en="Latest periodic report in the checked list" es="Último informe periódico en la lista verificada" />:</p>
    <a href={latest.sourceUrl} className={linkClass}>Form 460 · <Localized en="through" es="hasta el" /> {formatCivicDate(latest.periodEnd!)}</a>
    <p className="text-sm text-slate-600"><Localized en="Filed" es="Presentado el" /> {formatCivicDate(latest.filedAt)} · <Localized en="covers" es="cubre del" /> {formatCivicDate(latest.periodStart!)}–{formatCivicDate(latest.periodEnd!)}</p>
    {coverage.recentRapid.length > 0 && <>
      <p className="mt-3 text-sm text-slate-600"><Localized en="24-hour reports filed after that period (up to four)" es="Informes de 24 horas presentados después de ese período (hasta cuatro)" />:</p>
      <ul className="mt-1 text-sm">{coverage.recentRapid.map(filing => <li key={filing.id}>
        <a href={filing.sourceUrl} className={linkClass}>Form 497 · {formatCivicDate(filing.filedAt)} · #{filing.id}</a>
      </li>)}</ul>
    </>}
    <p className="mt-3 text-sm text-slate-600"><Localized en="Official filing metadata · last checked" es="Datos oficiales de los informes · última verificación" /> <time dateTime={coverage.checkedAt}>{checked} <Localized en="Richmond time" es="hora de Richmond" /></time>. <Localized en="Filing dates are not contribution dates." es="Las fechas de presentación no son las fechas de las aportaciones." /></p>
    <a href={ANDERSON_FILER.sourceUrl} className={`${linkClass} text-sm`}><Localized en="See the committee’s official filing list →" es="Ver la lista oficial de informes del comité →" /></a>
  </aside>
}
