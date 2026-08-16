import type { Metadata } from 'next'
import { OperatorMethodology } from './OperatorMethodology'

export const metadata: Metadata = {
  title: 'About',
  description:
    'How Richmond Commons collects, organizes, and publishes local government data. Data sources, methodology, and project information.',
}

export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <h1 className="text-4xl font-bold text-civic-navy mb-3">About</h1>
      <p className="text-lg text-slate-600 mb-8">
        How we collect, organize, and publish Richmond City Council data.
      </p>

      {/* What is this */}
      <Section title="What Is Richmond Commons?">
        <p>
          Richmond Commons pulls Richmond&apos;s city government data into one place
          and makes it understandable. Meeting agendas, votes, and official actions
          are translated into plain language so any resident can follow what&apos;s
          happening at City Hall without reading hundreds of pages of government documents.
        </p>
        <p>
          Local journalism covering Richmond has declined significantly. Over 2,500
          newspapers have closed nationwide since 2005. Richmond Commons helps fill the gap
          by making the information that&apos;s already public genuinely accessible.
        </p>
      </Section>

      <Section id="privacy" title="Privacy">
        <p>
          Richmond Commons uses Vercel Web Analytics to understand aggregate
          demand for public pages. It measures page views, daily anonymous
          visitors, referring pages, browser and device types, and approximate
          city or country. Modern browsers usually reduce cross-site referrers
          to the source site, but a source can choose to send its full page URL
          to Vercel. Richmond Commons reports referrers only as aggregate source
          domains. We do not use analytics cookies or an identifier that follows
          someone across days.
        </p>
        <p>
          Query strings and page fragments are removed before a page view is
          sent. Analytics is disabled for unresolved and operator sessions and
          for subscription management pages. Search terms, addresses, email
          addresses, and subscription tokens are not written to browsing
          analytics. Email subscription information is used to deliver and
          manage briefings; it is not joined to browsing activity.
        </p>
        <p>
          Operational safety logs omit raw request addresses and user-agent
          strings. Where short-term correlation is needed, address and email
          values are replaced with secret-keyed pseudonyms that rotate each UTC
          day. Private per-cycle subscription activation history is deleted
          after 90 days. Richmond Commons does not currently retain longer-term
          activation aggregates.
        </p>
        <p>
          Learn more about{' '}
          <a
            href="https://vercel.com/docs/analytics/using-web-analytics"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-civic-navy-light hover:text-civic-navy hover:underline"
          >
            Vercel Web Analytics privacy
          </a>
          .
        </p>
      </Section>

      {/* What this is NOT */}
      <Section title="What This Is NOT">
        <ul className="list-disc list-inside space-y-2 text-slate-700">
          <li>
            <strong>Not adversarial.</strong> This is a governance assistant, not a &ldquo;gotcha&rdquo; tool.
            Accountability is a byproduct of transparency, not the goal.
          </li>
          <li>
            <strong>Not advocacy.</strong> We present factual, citation-backed information.
            No opinion, no editorial, no recommendations on how to vote.
          </li>
          <li>
            <strong>Not social media.</strong> Data comes from official government sources and
            regulated campaign finance filings, not social media or rumors.
          </li>
        </ul>
      </Section>

      {/* How It Works */}
      <Section title="How It Works">
        <ol className="list-decimal list-inside space-y-3 text-slate-700">
          <li>
            <strong>Collect official documents:</strong> We download agendas, minutes, staff reports,
            and attachments from Richmond&apos;s official meeting portals.
          </li>
          <li>
            <strong>Extract structured data:</strong> Documents are parsed to pull out
            agenda items, motions, votes, and key details.
          </li>
          <li>
            <strong>Generate plain-language summaries:</strong> Each agenda item gets a short
            description of what happened and why it matters, written at a level anyone can understand.
          </li>
          <li>
            <strong>Show council context:</strong> Council member profiles include voting records
            and campaign finance data from public filings, so you can see the full picture.
          </li>
        </ol>
      </Section>

      {/* Operator-only methodology sections */}
      <OperatorMethodology />

      {/* Data Sources */}
      <Section title="Data Sources">
        <p className="mb-3 text-slate-600">
          All data comes from official government sources and regulated public filings.
        </p>
        <div className="space-y-3">
          <DataSource
            name="eSCRIBE Meeting Portal"
            description="Full agenda packets including staff reports, contracts, resolutions, and attachments."
            url="https://pub-richmond.escribemeetings.com/"
          />
          <DataSource
            name="Richmond Archive Center"
            description="Official council meeting minutes (certified PDF documents)."
            url="https://www.ci.richmond.ca.us/ArchiveCenter/?AMID=31"
          />
          <DataSource
            name="NetFile Connect2"
            description="Local campaign finance: individual council candidate contributions filed with the City Clerk."
            url="https://public.netfile.com/pub2/?AID=RICH"
          />
          <DataSource
            name="CAL-ACCESS"
            description="California campaign finance: PAC contributions, independent expenditures, statewide filings."
            url="https://cal-access.sos.ca.gov/"
          />
          <DataSource
            name="Transparent Richmond"
            description="City open data portal: expenditures, vendors, payroll, permits, and more."
            url="https://www.transparentrichmond.org/"
          />
        </div>
      </Section>

      {/* Limitations */}
      <Section title="Limitations & Disclaimers">
        <ul className="list-disc list-inside space-y-2 text-slate-700">
          <li>
            Auto-generated summaries are not 100% accurate. We validate against known patterns
            and improve continuously, but errors are possible. Official documents are always
            linked as the primary source.
          </li>
          <li>
            Campaign finance data has a lag. State filings may be weeks or months behind.
            Local filings are more current but only cover filings since 2018.
          </li>
          <li>
            Meeting data depends on what the city publishes. If a document isn&apos;t posted
            to the official portal, it won&apos;t appear here.
          </li>
          <li>
            This project is not affiliated with the City of Richmond. It is an independent
            civic technology initiative.
          </li>
        </ul>
      </Section>

      {/* Contact & Support */}
      <Section title="Contact & Support">
        <p>
          This project is in active development. If you spot an error, have a correction,
          or want to share feedback, there are two ways to reach us:
        </p>
        <div className="space-y-3 mt-3">
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <h4 className="font-medium text-slate-900 text-sm mb-1">Feedback Button</h4>
            <p className="text-sm text-slate-600">
              Use the feedback button in the bottom-right corner of any page to send
              questions, corrections, or ideas directly. No account needed.
            </p>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <h4 className="font-medium text-slate-900 text-sm mb-1">Email</h4>
            <p className="text-sm text-slate-600">
              For longer questions or partnership inquiries:{' '}
              <a
                href="mailto:hello@richmondcommons.org"
                className="text-civic-navy-light hover:text-civic-navy font-medium"
              >
                hello@richmondcommons.org
              </a>
            </p>
          </div>
        </div>
      </Section>

      {/* Support This Project */}
      <Section title="Support This Project">
        <p>
          Richmond Commons is free and will always be free. If you find it useful and
          want to help keep it running, you can support the project on Ko-fi.
        </p>
        <a
          href="https://ko-fi.com/richmondcommon"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 mt-3 px-4 py-2 bg-civic-amber text-white font-medium text-sm rounded-lg hover:bg-amber-600 transition-colors"
        >
          Support on Ko-fi &rarr;
        </a>
        <p className="text-xs text-slate-500 mt-2">
          100% of contributions go toward hosting, data infrastructure, and API costs.
        </p>
      </Section>
    </div>
  )
}

function Section({
  id,
  title,
  children,
}: {
  id?: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="mb-10 scroll-mt-6">
      <h2 className="text-xl font-semibold text-civic-navy mb-3">{title}</h2>
      <div className="space-y-3 text-slate-700 leading-relaxed">{children}</div>
    </section>
  )
}

function DataSource({
  name,
  description,
  url,
}: {
  name: string
  description: string
  url: string
}) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-3">
      <h4 className="font-medium text-slate-900 text-sm">{name}</h4>
      <p className="text-sm text-slate-600 mt-0.5">{description}</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-civic-navy-light hover:text-civic-navy mt-1 inline-block"
      >
        {url.replace(/^https?:\/\//, '')} &rarr;
      </a>
    </div>
  )
}
