import Link from 'next/link'
import type { Metadata } from 'next'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import { CivicLanguageScope, Localized } from '@/components/civic/CivicLanguage'
import { AndersonReportFreshness } from '@/components/AndersonFinanceSummary'
import { ANDERSON_FILER } from '@/data/anderson-paper-filings'
import { ANDERSON_FINANCE as data, ANDERSON_MONEY_PATH, andersonSource, andersonSourcePage,
  andersonPeriodTotal, andersonDonationPeriods, andersonPaymentGroups, formatReportedMoney as money, reportedCents } from '@/lib/anderson-finance'
import { formatCivicDate } from '@/lib/november-election'
import { getAndersonFilingCoverage } from '@/lib/queries/candidate-filing-coverage'

export const metadata: Metadata = {
  title: 'Ahmad Anderson: campaign donations, cash and original reports',
  description: 'Read Anderson’s campaign-reported fundraising by period, named recent donations, and the original Richmond campaign reports.',
  alternates: { canonical: `https://richmondcommons.org${ANDERSON_MONEY_PATH}` },
}

const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'
const sectionClass = 'mt-10 border-t border-slate-200 pt-7'

function Donations({ receipts }: { receipts: typeof data.rapid_receipts }) {
  return <ol className="mt-4 divide-y divide-slate-200">{receipts.map(receipt => <li key={receipt.filing_id} className="py-5">
    <p className="text-lg font-semibold text-civic-navy">{money(receipt.amount)} · {receipt.donor_name}</p>
    <p className="mt-1 text-slate-700"><Localized en="Donation received " es="Donación recibida el " /><time dateTime={receipt.received_date}>{formatCivicDate(receipt.received_date)}</time></p>
    {receipt.reported_context && <p className="mt-1 text-slate-600"><Localized en="Work listed in the report: " es="Ocupación declarada en el informe: " />{receipt.reported_context}</p>}
    <p className="mt-1 text-sm text-slate-600"><Localized en="Report listed by the city " es="Informe registrado por la ciudad el " />{formatCivicDate(andersonSource(receipt.filing_id).filed_at)} · <a className={linkClass} href={andersonSourcePage(receipt.filing_id, receipt.page)}><Localized en="Read the original donation report" es="Leer el informe original de la donación" /></a></p>
  </li>)}</ol>
}

export default async function AndersonMoneyPage() {
  const coverage = await getAndersonFilingCoverage()
  const { later, earlier } = andersonDonationPeriods()
  const latest = andersonSource(data.periodic.filing_id)
  const periodTotal = andersonPeriodTotal()
  const laterTotal = later.reduce((total, receipt) => total + reportedCents(receipt.amount), 0)
  const payees = andersonPaymentGroups()
  return <article className="mx-auto max-w-3xl px-4 py-10 sm:px-6"><CivicLanguageScope>
    <Link href="/elections/2026-general#money" className={linkClass}><Localized en="← November guide" es="← Guía de noviembre" /></Link>
    <h1 className="mt-4 text-3xl font-bold tracking-tight text-civic-navy sm:text-4xl"><Localized en="Ahmad Anderson’s campaign money" es="El dinero de la campaña de Ahmad Anderson" /></h1>
    <p className="mt-4 text-lg leading-relaxed text-slate-700"><Localized
      en={`His campaign reports ${money(periodTotal)} in cash donations for January 1–June 30, 2026. We added the amounts for four separate reporting periods, so money raised in 2025 is kept out of this year’s figure.`}
      es={`Su campaña declara ${money(periodTotal)} en donaciones monetarias del 1 de enero al 30 de junio de 2026. Sumamos cuatro períodos distintos para separar el dinero recaudado en 2025.`} /></p>
    <p className="mt-3 leading-relaxed text-slate-700"><Localized
      en={`Two newer reports list another ${money(laterTotal)} received on August 30 and September 2. They describe two donations and do not provide a complete fundraising total since June.`}
      es={`Dos informes más recientes declaran ${money(laterTotal)} recibidos el 30 de agosto y el 2 de septiembre. Describen dos donaciones, no el total recaudado desde junio.`} /></p>
    <p className="mt-3 text-sm text-slate-600"><Localized en="Official campaign reports · AI-written explanation, checked against the original PDFs on " es="Informes oficiales de campaña · explicación redactada con IA y cotejada con los PDF originales el " /><time dateTime={data.reviewed_at}>{formatCivicDate(data.reviewed_at)}</time>.</p>
    <p className="mt-2 text-sm text-slate-600">{ANDERSON_FILER.committeeName} · FPPC {ANDERSON_FILER.committeeId}</p>
    <AndersonReportFreshness coverage={coverage} />
    <div className="mt-4 flex flex-wrap gap-x-6"><a className={linkClass} href="#donations"><Localized en="Recent donors" es="Donantes recientes" /></a><a className={linkClass} href="#calculation"><Localized en="How we counted" es="Cómo calculamos" /></a><a className={linkClass} href={`${ANDERSON_MONEY_PATH}/reports.csv`}><Localized en="Download these figures (CSV)" es="Descargar estas cifras (CSV)" /></a></div>

    <section className={sectionClass} aria-labelledby="latest-report"><h2 id="latest-report" className="text-2xl font-semibold text-civic-navy"><Localized en="Cash and spending in the latest full report" es="Efectivo y gastos en el último informe completo" /></h2>
      <p className="mt-3 text-slate-700"><Localized en="May 29–June 30, 2026" es="29 de mayo–30 de junio de 2026" /></p>
      <dl className="mt-5 grid gap-5 sm:grid-cols-3">
        <div><dt className="text-slate-600"><Localized en="Donations received" es="Donaciones recibidas" /></dt><dd className="mt-1 text-2xl font-semibold text-civic-navy">{money(data.periodic.reported.monetary_received)}</dd></div>
        <div><dt className="text-slate-600"><Localized en="Money spent" es="Dinero gastado" /></dt><dd className="mt-1 text-2xl font-semibold text-civic-navy">{money(data.periodic.reported.payments)}</dd></div>
        <div><dt className="text-slate-600"><Localized en="Cash left on June 30" es="Efectivo al 30 de junio" /></dt><dd className="mt-1 text-2xl font-semibold text-civic-navy">{money(data.periodic.reported.ending_cash)}</dd></div>
      </dl>
      <p className="mt-4 leading-relaxed text-slate-700"><Localized en="The campaign started this period with $16,895. Adding $9,140 received and subtracting $12,612 spent gives the reported $13,423 ending balance. This is its June 30 balance, not its balance today."
        es="La campaña comenzó este período con $16,895. Al sumar $9,140 recibidos y restar $12,612 gastados, el saldo declarado es de $13,423. Es el saldo al 30 de junio, no el saldo actual." /></p>
      <a className={`${linkClass} mt-2`} href={andersonSourcePage(latest.filing_id, data.periodic.summary_page)}><Localized en="Read the cash summary · page 3 of the report" es="Leer el resumen de efectivo · página 3 del informe" /></a>
    </section>

    <section className={sectionClass}><h2 className="text-2xl font-semibold text-civic-navy"><Localized en="Where most of that spending went" es="Adónde fue la mayor parte de ese dinero" /></h2>
      <p className="mt-3 text-slate-700"><Localized en={`The two largest totals among ${payees.length} payees listed for May 29–June 30:`} es={`Los dos mayores totales entre ${payees.length} destinatarios de pagos del 29 de mayo al 30 de junio:`} /></p>
      <ul className="mt-4 space-y-4">{payees.slice(0, 2).map(payee => <li key={payee.name}><p className="font-semibold text-civic-navy">{money(payee.cents)} · {payee.name}</p><p className="mt-1 text-slate-600"><Localized en="For: " es="Por: " />{payee.descriptions.join('; ')}</p></li>)}</ul>
      <p className="mt-4 text-sm leading-relaxed text-slate-600"><Localized en="The report lists 14 payments totaling $12,611.90, which rounds to the $12,612 on its summary page. These payments are already included in the spending figure above."
        es="El informe enumera 14 pagos que suman $12,611.90, redondeados a $12,612 en su resumen. Ya están incluidos en la cifra de gastos anterior." /></p>
      <a href={andersonSourcePage(data.periodic.filing_id, 7)} className={linkClass}><Localized en="Read all 14 payments · page 7" es="Leer los 14 pagos · página 7" /></a>
    </section>

    <section id="donations" className={`${sectionClass} scroll-mt-24`}><h2 className="text-2xl font-semibold text-civic-navy"><Localized en={`Donations received after June 30 (${later.length})`} es={`Donaciones recibidas después del 30 de junio (${later.length})`} /></h2>
      <Donations receipts={later} />
      <p className="mt-2 text-sm leading-relaxed text-slate-600"><Localized en="The Davillier Sloan report has two filing dates: the city’s stamp says August 31, while the form is dated September 1. Both are separate from the August 30 donation date."
        es="El informe de Davillier Sloan tiene dos fechas: el sello de la ciudad dice 31 de agosto y el formulario dice 1 de septiembre. La donación se recibió el 30 de agosto." /></p>
    </section>
    <section className={sectionClass}><h2 className="text-2xl font-semibold text-civic-navy"><Localized en={`May donations reported in August (${earlier.length})`} es={`Donaciones de mayo declaradas en agosto (${earlier.length})`} /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized en="These reports arrived later, but both give May 16 as the donation date. They are not money received after June. We keep them separate from the period totals because we have not established how they fit into those totals."
        es="Estos informes llegaron después, pero ambos indican que la donación se recibió el 16 de mayo. No son ingresos posteriores a junio. Los mantenemos separados de los totales por período porque todavía no se ha establecido cómo encajan en ellos." /></p>
      <Donations receipts={earlier} />
      <p className="mt-2 text-sm text-slate-600"><Localized en="An individual’s listed employer is context from the filing; it does not make the employer the donor." es="El empleador declarado aporta contexto; no significa que el empleador hizo la donación." /></p>
    </section>

    <section id="calculation" className={`${sectionClass} scroll-mt-24`}><h2 className="text-2xl font-semibold text-civic-navy"><Localized en="How the 2026 total adds up" es="Cómo se calcula el total de 2026" /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized en="We use the amount received during each period on the campaign’s summary page. These are the campaign’s declared totals; they have not been fully matched to every individual donation."
        es="Usamos el dinero recibido durante cada período que figura en la página de resumen. Son los totales declarados por la campaña; todavía no se han cotejado con cada donación individual." /></p>
      <ol className="mt-4 divide-y divide-slate-200">{data.periodic_history.map(period => {
        const source = andersonSource(period.filing_id)
        return <li key={period.filing_id} className="flex flex-wrap items-center justify-between gap-x-5 py-3"><a className={linkClass} href={andersonSourcePage(period.filing_id, period.summary_page)}>{formatCivicDate(source.period_start!)}–{formatCivicDate(source.period_end!)}</a><span className="text-lg font-semibold text-civic-navy">{money(period.monetary_received)}</span></li>
      })}</ol>
      <p className="mt-4 font-semibold text-civic-navy"><Localized en="Total for these four periods: " es="Total de estos cuatro períodos: " />{money(periodTotal)}</p>
      <p className="mt-4 leading-relaxed text-slate-700"><Localized en="Why not $73,300? That running figure includes the $18,997 reported for 2025. The four 2026 periods add up to $54,303; together they explain the $73,300 printed on the June report."
        es="¿Por qué no $73,300? Esa cifra acumulada incluye los $18,997 declarados para 2025. Los cuatro períodos de 2026 suman $54,303; juntos explican los $73,300 del informe de junio." /></p>
      <a className={linkClass} href={andersonSourcePage(data.prior_year.filing_id, data.prior_year.summary_page)}><Localized en="Read the 2025 report · page 3" es="Leer el informe de 2025 · página 3" /></a>
      <p className="mt-3 text-sm leading-relaxed text-slate-600"><Localized en="The city lists two versions of the January–April report. Both show $21,605 for the same period, which we count once. Neither is marked as an amendment."
        es="La ciudad incluye dos versiones del informe de enero a abril. Ambas declaran $21,605 para el mismo período, que contamos una sola vez. Ninguna está marcada como enmienda." />{' '}<a className={linkClass} href={andersonSourcePage('217027183', 3)}><Localized en="See the second version" es="Ver la segunda versión" /></a></p>
    </section>

    <section className={sectionClass}><h2 className="text-2xl font-semibold text-civic-navy"><Localized en="What still needs checking" es="Qué falta por verificar" /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized en="Some donation attachments contain dates outside their reporting periods, one report refers to an attachment that is missing, and some spending and donation subtotals disagree. We keep the source figures visible rather than silently changing them. We do not use these reports to claim a complete donor list, a small-donor percentage, or a reliable year-to-date spending total."
        es="Algunos anexos incluyen fechas fuera del período, falta un anexo mencionado y ciertos subtotales no coinciden. Mostramos las cifras originales sin cambiarlas en silencio. Estos informes no permiten afirmar que tenemos la lista completa de donantes, el porcentaje de pequeñas donaciones ni un total confiable de gastos del año." /></p>
      <div className="mt-2 flex flex-wrap gap-x-5"><a href={andersonSourcePage('217094857', 4)} className={linkClass}><Localized en="June donation schedule" es="Desglose de donaciones de junio" /></a><a href={andersonSourcePage('216695016', 3)} className={linkClass}><Localized en="January–April spending summary" es="Resumen de gastos de enero a abril" /></a></div>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized en="These figures belong to Anderson’s own campaign. Money raised or spent by Safe Richmond Neighborhoods is separate and is not included here."
        es="Estas cifras corresponden a la campaña de Anderson. El dinero de Safe Richmond Neighborhoods se registra por separado y no está incluido aquí." /></p>
      <Link href="/elections/2026-general/money?committee=1490887" className={linkClass}><Localized en="See the separate Safe Richmond committee’s records →" es="Ver los registros del comité independiente Safe Richmond →" /></Link>
    </section>
    <footer className="mt-10 border-t border-slate-200 pt-6 text-sm text-slate-600"><a href={ANDERSON_FILER.sourceUrl} className={linkClass}><Localized en="All official reports for Anderson’s campaign" es="Todos los informes oficiales de la campaña de Anderson" /></a><p className="mt-3"><Localized en="Richmond Commons. “Ahmad Anderson’s campaign money.” Source review: September 6, 2026. Amounts are dollars as reported, including any rounding in the originals."
      es="Richmond Commons. «El dinero de la campaña de Ahmad Anderson». Fuentes revisadas el 6 de septiembre de 2026. Las cantidades conservan el redondeo de los originales." /></p><div className="mt-3"><SuggestCorrectionLink /></div></footer>
  </CivicLanguageScope></article>
}
