import Link from 'next/link'
import type { Metadata } from 'next'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import { CivicDate, CivicLanguageScope, Localized } from '@/components/civic/CivicLanguage'
import { formatReportedMoney as money, reportedCents } from '@/lib/reported-money'
import { JIMENEZ_FINANCE as data, JIMENEZ_MONEY_PATH, jimenezSource, jimenezSourcePage,
  jimenezPeriodTotal, jimenezDonationPeriods } from '@/lib/jimenez-finance'

export const metadata: Metadata = {
  title: 'Claudia Jimenez: campaign donations, cash and original reports',
  description: 'Jimenez’s campaign-reported cash donations, noncash support, June 30 balance and later donation reports, with the original Richmond filings.',
  alternates: { canonical: `https://richmondcommons.org${JIMENEZ_MONEY_PATH}` },
}

const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'
const sectionClass = 'mt-10 border-t border-slate-200 pt-7'

function Donations({ receipts }: { receipts: typeof data.rapid_receipts }) {
  return <ol className="mt-4 divide-y divide-slate-200">{receipts.map(receipt => (
    <li key={`${receipt.filing_id}:${receipt.source_row}`} className="py-5">
      <p className="text-lg font-semibold text-civic-navy">{money(receipt.amount)} · {receipt.donor_name}</p>
      {receipt.donor_fppc_id && <p className="mt-1 text-sm text-slate-600">FPPC {receipt.donor_fppc_id}</p>}
      <p className="mt-1 text-slate-700"><Localized en="Donation received " es="Donación recibida el " />
        <CivicDate date={receipt.received_date} /></p>
      <p className="mt-1 text-sm text-slate-600"><Localized en="Report filed " es="Informe presentado el " />
        <CivicDate date={jimenezSource(receipt.filing_id).filed_at} />{' · '}
        <a className={linkClass} href={jimenezSourcePage(receipt.filing_id, receipt.page)}>
          <Localized en="Read the original donation report" es="Leer el informe original de la donación" />
        </a>
      </p>
    </li>
  ))}</ol>
}

export default function JimenezMoneyPage() {
  const { later, earlier } = jimenezDonationPeriods()
  const latest = data.periodic.reported
  const periodTotal = jimenezPeriodTotal()
  const laterTotal = later.reduce((sum, receipt) => sum + reportedCents(receipt.amount), 0)
  return <article className="mx-auto max-w-3xl px-4 py-10 sm:px-6"><CivicLanguageScope>
    <Link href="/elections/2026-general#money" className={linkClass}><Localized en="← November guide" es="← Guía de noviembre" /></Link>
    <h1 className="mt-4 text-3xl font-bold tracking-tight text-civic-navy sm:text-4xl"><Localized
      en="Claudia Jimenez’s campaign money" es="El dinero de la campaña de Claudia Jimenez" /></h1>
    <p className="mt-4 text-lg leading-relaxed text-slate-700"><Localized
      en={`Her campaign reports ${money(periodTotal)} in cash donations for January 1–June 30, 2026. Three reporting periods add up to the same amount printed on its latest summary.`}
      es={`Su campaña declara ${money(periodTotal)} en donaciones monetarias del 1 de enero al 30 de junio de 2026. Tres períodos suman la misma cantidad que aparece en su último resumen.`} /></p>
    <p className="mt-3 leading-relaxed text-slate-700"><Localized
      en={`The campaign separately reports ${money(latest.cumulative_noncash)} in noncash support through June 30. Five later donation entries total ${money(laterTotal)} received in July; they are not a complete fundraising total since June.`}
      es={`La campaña declara por separado ${money(latest.cumulative_noncash)} en apoyo no monetario hasta el 30 de junio. Cinco donaciones posteriores suman ${money(laterTotal)} recibidos en julio; no son el total recaudado desde junio.`} /></p>
    <p className="mt-3 text-sm text-slate-600"><Localized
      en="Official campaign reports · AI-written explanation, checked against the original PDFs on "
      es="Informes oficiales de campaña · explicación redactada con IA y cotejada con los PDF originales el " />
      <CivicDate date={data.reviewed_at.slice(0, 10)} />.
    </p>
    <p className="mt-2 text-sm text-slate-600">{data.committee.name} · FPPC {data.committee.fppc_id}</p>
    <nav aria-label="On this page" className="mt-4 flex flex-wrap gap-x-6">
      <a className={linkClass} href="#donations"><Localized en="July donations" es="Donaciones de julio" /></a>
      <a className={linkClass} href="#calculation"><Localized en="How we counted" es="Cómo calculamos" /></a>
      <a className={linkClass} href="#noncash"><Localized en="Noncash support" es="Apoyo no monetario" /></a>
    </nav>

    <section className={sectionClass} aria-labelledby="latest-report">
      <h2 id="latest-report" className="text-2xl font-semibold text-civic-navy"><Localized
        en="Cash and spending in the latest reviewed report" es="Efectivo y gastos en el último informe revisado" /></h2>
      <p className="mt-3 text-slate-700"><Localized en="May 17–June 30, 2026 · filed July 31" es="17 de mayo–30 de junio de 2026 · presentado el 31 de julio" /></p>
      <dl className="mt-5 grid gap-5 sm:grid-cols-3">
        <div><dt className="text-slate-600"><Localized en="Cash donations received" es="Donaciones monetarias recibidas" /></dt><dd className="mt-1 text-2xl font-semibold text-civic-navy">{money(latest.monetary_received)}</dd></div>
        <div><dt className="text-slate-600"><Localized en="Cash payments" es="Pagos en efectivo" /></dt><dd className="mt-1 text-2xl font-semibold text-civic-navy">{money(latest.payments)}</dd></div>
        <div><dt className="text-slate-600"><Localized en="Cash left on June 30" es="Efectivo al 30 de junio" /></dt><dd className="mt-1 text-2xl font-semibold text-civic-navy">{money(latest.ending_cash)}</dd></div>
      </dl>
      <p className="mt-4 leading-relaxed text-slate-700"><Localized
        en={`The period began with ${money(latest.beginning_cash)}. Adding ${money(latest.monetary_received)} received and subtracting ${money(latest.payments)} paid gives the reported ${money(latest.ending_cash)} ending balance. This is its June 30 balance, not its balance today.`}
        es={`El período comenzó con ${money(latest.beginning_cash)}. Al sumar ${money(latest.monetary_received)} recibidos y restar ${money(latest.payments)} pagados, el saldo declarado es ${money(latest.ending_cash)}. Es el saldo al 30 de junio, no el saldo actual.`} /></p>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en={`Across January–June, the campaign reports ${money(latest.cumulative_payments)} in cash payments. The ${money(latest.cumulative_noncash)} in noncash support is separate from these cash payments.`}
        es={`De enero a junio, la campaña declara ${money(latest.cumulative_payments)} en pagos en efectivo. Los ${money(latest.cumulative_noncash)} de apoyo no monetario se registran por separado.`} /></p>
      <a className={`${linkClass} mt-2`} href={jimenezSourcePage(data.periodic.filing_id, data.periodic.summary_page)}>
        <Localized en="Read the cash summary · page 3" es="Leer el resumen de efectivo · página 3" />
      </a>
    </section>

    <section id="donations" className={`${sectionClass} scroll-mt-24`}>
      <h2 className="text-2xl font-semibold text-civic-navy"><Localized
        en={`Donations received after June 30 (${later.length})`} es={`Donaciones recibidas después del 30 de junio (${later.length})`} /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en="Three reports filed July 31 describe these five receipts. The dates below are when the donations were received, not when the reports were filed."
        es="Tres informes presentados el 31 de julio describen estas cinco donaciones. Las fechas indican cuándo se recibieron, no cuándo se presentaron los informes." /></p>
      <Donations receipts={later} />
    </section>

    <section className={sectionClass}>
      <h2 className="text-2xl font-semibold text-civic-navy"><Localized
        en="A February donation reported in August" es="Una donación de febrero declarada en agosto" /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en="The newest filing in our September 6 source review describes an earlier donation. We have not matched it to the period reports, so we keep it separate from their totals and from July's receipts."
        es="El informe más reciente de nuestra revisión del 6 de septiembre describe una donación anterior. No se ha cotejado con los informes por período; la mantenemos separada de sus totales y de las donaciones de julio." /></p>
      <Donations receipts={earlier} />
    </section>

    <section id="calculation" className={`${sectionClass} scroll-mt-24`}>
      <h2 className="text-2xl font-semibold text-civic-navy"><Localized en="How the 2026 cash total adds up" es="Cómo se calcula el total monetario de 2026" /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en="We use the campaign's declared amounts for three nonoverlapping periods, including its amended reports. Their sum matches the calendar-year cash total on the June 30 statement. This checks the summaries, not every individual donation."
        es="Usamos las cantidades declaradas para tres períodos que no se superponen, incluidas las enmiendas. La suma coincide con el total monetario del año en el informe al 30 de junio. Este cotejo verifica los resúmenes, no cada donación individual." /></p>
      <ol className="mt-4 divide-y divide-slate-200">{data.periodic_history.map(period => {
        const source = jimenezSource(period.filing_id)
        return <li key={period.filing_id} className="flex flex-wrap items-center justify-between gap-x-5 py-3">
          <a className={linkClass} href={jimenezSourcePage(period.filing_id, period.summary_page)}>
            <CivicDate date={source.period_start!} />–<CivicDate date={source.period_end!} />
          </a><span className="text-lg font-semibold text-civic-navy">{money(period.monetary_received)}</span>
        </li>
      })}</ol>
      <p className="mt-4 font-semibold text-civic-navy"><Localized en="Total for these three periods: " es="Total de estos tres períodos: " />{money(periodTotal)}</p>
      <p className="mt-4 leading-relaxed text-slate-700"><Localized
        en="An earlier paper report covers May 17–28, inside the latest report's May 17–June 30 period. Adding it again would overlap the dates. We retain the original report without adding it to this total."
        es="Un informe anterior en papel abarca del 17 al 28 de mayo, dentro del período del 17 de mayo al 30 de junio del último informe. Sumarlos superpondría las fechas. Conservamos el informe original sin añadirlo al total." /></p>
      <a className={linkClass} href={jimenezSourcePage(data.overlapping_report.filing_id, data.overlapping_report.summary_page)}>
        <Localized en="Read the overlapping May report" es="Leer el informe de mayo con fechas superpuestas" />
      </a>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en="The three reports include $1,447 in unitemized cash donations, reported as combined amounts rather than individual donor rows. Those amounts are included in the $60,365 above."
        es="Los tres informes incluyen $1,447 en donaciones monetarias no desglosadas, declaradas como cantidades agrupadas. Ya están incluidas en los $60,365 anteriores." /></p>
    </section>

    <section id="noncash" className={`${sectionClass} scroll-mt-24`}>
      <h2 className="text-2xl font-semibold text-civic-navy"><Localized en="Support that did not arrive as cash" es="Apoyo que no llegó en efectivo" /></h2>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en="The campaign lists $2,000 from Diana Wear on April 8 as noncash support: payment for speech coaching. A separate rapid contribution report lists the same name, date and amount. It does not establish an additional cash donation, so we do not add it to the cash total."
        es="La campaña declara $2,000 de Diana Wear el 8 de abril como apoyo no monetario: pago por entrenamiento para discursos. Otro informe de contribución enumera el mismo nombre, fecha y cantidad. No acredita una donación adicional en efectivo, por lo que no lo añadimos al total monetario." /></p>
      <div className="mt-2 flex flex-wrap gap-x-5">
        <a className={linkClass} href={jimenezSourcePage(data.noncash_contribution.filing_id, data.noncash_contribution.page)}><Localized en="Read Schedule C · noncash contribution" es="Leer el anexo C · contribución no monetaria" /></a>
        <a className={linkClass} href={jimenezSourcePage(data.noncash_contribution.matching_rapid_filing_id, data.noncash_contribution.matching_rapid_page)}><Localized en="Read the separate contribution report" es="Leer el informe de contribución separado" /></a>
      </div>
      <p className="mt-3 leading-relaxed text-slate-700"><Localized
        en="These are Jimenez's own campaign records. Outside committees' fundraising and spending are separate and are not included here."
        es="Estos registros pertenecen a la campaña de Jimenez. La recaudación y los gastos de comités externos son independientes y no están incluidos aquí." /></p>
    </section>

    <footer className="mt-10 border-t border-slate-200 pt-6 text-sm text-slate-600">
      <a href={data.committee.source_url} className={linkClass}><Localized en="All official reports for Jimenez’s campaign" es="Todos los informes oficiales de la campaña de Jimenez" /></a>
      <p className="mt-3"><Localized en="Richmond Commons. “Claudia Jimenez’s campaign money.” Figures are dollars as reported, with their original reporting dates."
        es="Richmond Commons. «El dinero de la campaña de Claudia Jimenez». Las cifras están en dólares según lo declarado, con las fechas de los informes originales." /></p>
      <div className="mt-3"><SuggestCorrectionLink /></div>
    </footer>
  </CivicLanguageScope></article>
}
