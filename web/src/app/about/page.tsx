import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'About & Methodology',
  description:
    'How the Richmond Transparency Project collects, analyzes, and publishes local government data. Source credibility tiers, conflict scanner methodology, and data sources.',
}

export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">About & Methodology</h1>
      <p className="text-slate-600 mb-8">
        How we collect, analyze, and publish Richmond City Council data.
      </p>

      {/* What is this */}
      <Section title="What Is the Richmond Transparency Project?">
        <p>
          The Richmond Transparency Project is an AI-powered local government accountability
          platform. It automatically analyzes government documents, detects potential conflicts
          of interest, and generates public comment before Richmond City Council meetings.
        </p>
        <p>
          This project replaces the investigative function of disappeared local journalism.
          Richmond, California (population ~116,000) lost dedicated beat reporters years ago.
          Without someone watching, transparency gaps grow silently.
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
            <strong>Not advocacy.</strong> We generate factual, citation-heavy analysis.
            No opinion, no editorial, no recommendations on how to vote.
          </li>
          <li>
            <strong>Not social media.</strong> Data comes from official government sources and
            regulated campaign finance filings, not social media or rumors.
          </li>
        </ul>
      </Section>

      {/* Source Credibility Tiers */}
      <Section title="Source Credibility Tiers">
        <p className="mb-4">
          All data is tagged with a credibility tier. Higher tiers carry more weight in analysis.
        </p>
        <div className="space-y-3">
          <TierCard
            tier={1}
            label="Official Records"
            color="bg-green-50 border-green-200"
            description="Certified minutes, adopted resolutions, CAL-ACCESS filings, budget documents. Highest reliability."
          />
          <TierCard
            tier={2}
            label="Independent Journalism"
            color="bg-blue-50 border-blue-200"
            description="Richmond Confidential (UC Berkeley), East Bay Times, KQED. Editorially independent reporting."
          />
          <TierCard
            tier={3}
            label="Stakeholder Communications"
            color="bg-amber-50 border-amber-200"
            description="Council member newsletters, Tom Butt E-Forum, Richmond Standard (Chevron-funded). Bias is always disclosed."
          />
          <TierCard
            tier={4}
            label="Community / Social"
            color="bg-slate-50 border-slate-200"
            description="Nextdoor, public comments, social media. Used for context only, never as a sole source for factual claims."
          />
        </div>
      </Section>

      {/* Conflict Scanner */}
      <Section title="How the Conflict Scanner Works">
        <ol className="list-decimal list-inside space-y-3 text-slate-700">
          <li>
            <strong>Document ingestion:</strong> We download agendas, minutes, and staff reports
            from Richmond&apos;s eSCRIBE portal and Archive Center.
          </li>
          <li>
            <strong>AI extraction:</strong> Claude Sonnet extracts structured data from documents:
            agenda items, motions, votes, financial amounts, departments.
          </li>
          <li>
            <strong>Cross-referencing:</strong> Each agenda item is compared against 27,000+
            campaign contributions from CAL-ACCESS (state PAC/IE filings) and NetFile (local
            council candidate filings).
          </li>
          <li>
            <strong>Entity matching:</strong> Donor names, employers, and entities mentioned in
            agenda items are normalized and compared. Employer cross-referencing catches indirect
            connections.
          </li>
          <li>
            <strong>Confidence scoring:</strong> Matches are scored by confidence across three
            tiers: Strong (&ge;85%), Moderate (&ge;70%), and Low (&ge;50%). Flags below 50%
            are tracked internally only.
          </li>
          <li>
            <strong>False positive reduction:</strong> Government entity donors, sitting council
            member names, generic employers, and duplicate filings are automatically filtered.
          </li>
        </ol>
      </Section>

      {/* Data Sources */}
      <Section title="Data Sources">
        <div className="space-y-3">
          <DataSource
            name="Richmond Archive Center"
            description="Official council meeting minutes (certified PDF documents)."
            url="https://www.ci.richmond.ca.us/ArchiveCenter/?AMID=31"
          />
          <DataSource
            name="eSCRIBE Meeting Portal"
            description="Full agenda packets including staff reports, contracts, resolutions, and attachments."
            url="https://pub-richmond.escribemeetings.com/"
          />
          <DataSource
            name="CAL-ACCESS"
            description="California campaign finance: PAC contributions, independent expenditures, statewide filings."
            url="https://cal-access.sos.ca.gov/"
          />
          <DataSource
            name="NetFile Connect2"
            description="Local campaign finance: individual council candidate contributions filed with the City Clerk."
            url="https://public.netfile.com/pub2/?AID=RICH"
          />
          <DataSource
            name="Transparent Richmond"
            description="City open data portal with 300+ datasets: expenditures, vendors, payroll, permits."
            url="https://www.transparentrichmond.org/"
          />
        </div>
      </Section>

      {/* Limitations */}
      <Section title="Limitations & Disclaimers">
        <ul className="list-disc list-inside space-y-2 text-slate-700">
          <li>
            This system identifies <em>financial connections</em>, not corruption. A contribution
            to a council member from a vendor does not imply wrongdoing.
          </li>
          <li>
            Entity matching is imperfect. Name normalization may miss matches or create false
            positives, particularly for common surnames.
          </li>
          <li>
            Campaign finance data has a lag. CAL-ACCESS filings may be weeks or months behind.
            NetFile data is more current but only covers filings since 2018.
          </li>
          <li>
            AI extraction is not 100% accurate. We validate against known patterns and re-extract
            when prompts improve, but errors are possible.
          </li>
          <li>
            This project is not affiliated with the City of Richmond. It is an independent
            civic technology initiative.
          </li>
        </ul>
      </Section>

      {/* About the creator */}
      <Section title="About the Creator">
        <p>
          This project was created by Phillip Front, a Richmond resident in the North &amp; East
          neighborhood. The project exists because local journalism covering Richmond has
          largely disappeared, and the investigative function it served can be partially
          automated with modern AI tools.
        </p>
        <p>
          Phillip maintains a collaborative relationship with city government. This tool is
          designed to help cities stay transparent by default, not to be adversarial.
        </p>
      </Section>

      {/* Contact */}
      <Section title="Contact & Feedback">
        <p>
          This project is in active development. If you have questions, corrections, or
          feedback, please reach out.
        </p>
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2 className="text-xl font-semibold text-civic-navy mb-3">{title}</h2>
      <div className="space-y-3 text-slate-700 leading-relaxed">{children}</div>
    </section>
  )
}

function TierCard({
  tier,
  label,
  color,
  description,
}: {
  tier: number
  label: string
  color: string
  description: string
}) {
  return (
    <div className={`rounded-lg border p-3 ${color}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-bold text-slate-500">TIER {tier}</span>
        <span className="font-semibold text-slate-800 text-sm">{label}</span>
      </div>
      <p className="text-sm text-slate-600">{description}</p>
    </div>
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
