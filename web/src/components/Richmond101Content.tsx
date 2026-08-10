import Link from 'next/link'
import SourceBadge from './SourceBadge'

const CHECKED_AT = '2026-08-10T12:00:00-07:00'

interface SourceReference {
  name: string
  href: string
  tier: 1 | 2
}

function SourceReferences({ sources }: { sources: SourceReference[] }) {
  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sources</p>
      <ul className="mt-2 space-y-2">
        {sources.map((source) => (
          <li key={source.href}>
            <a
              href={source.href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 flex-col justify-center gap-1 rounded text-sm font-medium text-civic-navy hover:text-civic-navy-light focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
            >
              <span>
                {source.name} <span aria-hidden="true">&nearr;</span>
                <span className="sr-only"> (opens in a new tab)</span>
              </span>
              <SourceBadge
                tier={source.tier}
                source={source.name}
                extractedAt={CHECKED_AT}
              />
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Richmond101Content() {
  return (
    <article className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-12">
      <header className="border-b border-slate-200 pb-7">
        <p className="inline-flex rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800">
          Operator-only · AI-generated draft · voice review required
        </p>
        <h1 className="mt-4 text-3xl font-bold text-civic-navy sm:text-4xl">Richmond 101</h1>
        <p className="mt-3 text-base leading-relaxed text-slate-600">
          A practical guide to finding a meeting, reading an agenda, following a vote,
          and taking part in Richmond city government.
        </p>
      </header>

      <div className="mt-8 space-y-10">
        <section aria-labelledby="council-heading">
          <h2 id="council-heading" className="text-2xl font-semibold text-slate-900">
            Who makes city decisions
          </h2>
          <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-700">
            <p>
              Richmond&apos;s City Council has seven voting members: the mayor and six
              council members who represent districts. The council sets policy, adopts
              the city budget, and appoints a city manager to carry out its decisions and
              oversee city departments.
            </p>
            <p>
              Start with the person who represents your address, then use their profile
              to see recorded votes and meeting activity.
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              href="/elections/find-my-district"
              className="inline-flex min-h-11 items-center rounded-md bg-civic-navy px-4 py-2 text-sm font-semibold text-white hover:bg-civic-navy-light focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
            >
              Find My District
            </Link>
            <Link
              href="/council"
              className="inline-flex min-h-11 items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-civic-navy hover:border-civic-navy-light focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
            >
              Council Members
            </Link>
          </div>
          <SourceReferences
            sources={[
              {
                name: 'City of Richmond: City Council',
                href: 'https://www.ci.richmond.ca.us/29/City-Council',
                tier: 1,
              },
              {
                name: 'City of Richmond: Election 2026',
                href: 'https://www.ci.richmond.ca.us/4771/ELECTION-2026',
                tier: 1,
              },
            ]}
          />
        </section>

        <section aria-labelledby="meetings-heading">
          <h2 id="meetings-heading" className="text-2xl font-semibold text-slate-900">
            Find the meeting that matters to you
          </h2>
          <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-700">
            <p>
              Meeting dates, start times, and participation details can change. The latest
              official agenda is the final word on when and where a meeting happens.
            </p>
            <p>
              Richmond Commons brings agendas, plain-language summaries, votes, and links
              to the underlying city records into one meeting page.
            </p>
          </div>
          <Link
            href="/meetings"
            className="mt-4 inline-flex min-h-11 items-center rounded-md bg-civic-navy px-4 py-2 text-sm font-semibold text-white hover:bg-civic-navy-light focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
          >
            All Meetings
          </Link>
          <SourceReferences
            sources={[
              {
                name: 'City of Richmond: Council meeting information',
                href: 'https://www.ci.richmond.ca.us/3181/Richmond-City-Council',
                tier: 1,
              },
              {
                name: 'City of Richmond: Council agenda documents',
                href: 'https://www.ci.richmond.ca.us/151/Council-Agenda-Documents',
                tier: 1,
              },
            ]}
          />
        </section>

        <section aria-labelledby="agenda-heading">
          <h2 id="agenda-heading" className="text-2xl font-semibold text-slate-900">
            Read an agenda in a few steps
          </h2>
          <ol className="mt-3 list-decimal space-y-3 pl-5 text-base leading-relaxed text-slate-700 marker:font-semibold marker:text-civic-navy">
            <li>Find the item number and the city department bringing it forward.</li>
            <li>Read the recommended action to see what the council is being asked to do.</li>
            <li>Open the staff report and attachments for background, costs, and options.</li>
            <li>After the meeting, check the minutes and recorded votes for the final action.</li>
          </ol>
          <p className="mt-3 text-base leading-relaxed text-slate-700">
            Some routine items are grouped for one vote. An item can be removed from that
            group so the council can discuss it separately.
          </p>
          <SourceReferences
            sources={[
              {
                name: 'City of Richmond: Current council meetings and documents',
                href: 'https://www.ci.richmond.ca.us/4157/City-of-Richmond-Council-Meetings',
                tier: 1,
              },
              {
                name: 'City of Richmond: Guidelines for being heard',
                href: 'https://www.ci.richmond.ca.us/264/Guidelines-for-Being-Heard',
                tier: 1,
              },
            ]}
          />
        </section>

        <section aria-labelledby="comment-heading">
          <h2 id="comment-heading" className="text-2xl font-semibold text-slate-900">
            Speak during public comment
          </h2>
          <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-700">
            <p>
              If your comment is about an agenda item, use that item number. For a city
              issue that is not on the agenda, use the meeting&apos;s open public-comment period.
              The process and speaking time can vary, so check the current agenda before
              the meeting.
            </p>
            <p>
              Decide on one clear request, put the most important point first, and bring
              the source or document you want the council to consider.
            </p>
          </div>
          <SourceReferences
            sources={[
              {
                name: 'City of Richmond: Guidelines for being heard',
                href: 'https://www.ci.richmond.ca.us/264/Guidelines-for-Being-Heard',
                tier: 1,
              },
              {
                name: 'City of Richmond: Latest council agenda',
                href: 'https://www.ci.richmond.ca.us/citycouncilagenda',
                tier: 1,
              },
            ]}
          />
        </section>

        <section aria-labelledby="commissions-heading">
          <h2 id="commissions-heading" className="text-2xl font-semibold text-slate-900">
            Follow boards and commissions
          </h2>
          <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-700">
            <p>
              Richmond&apos;s boards, commissions, and committees advise the council and, in
              some cases, make decisions about specific projects or programs. Their meetings
              can be a useful place to understand an issue before it reaches the full council.
            </p>
            <p>
              The city publishes meeting information, openings, qualifications, and application
              instructions for residents who want to serve.
            </p>
          </div>
          <SourceReferences
            sources={[
              {
                name: 'City of Richmond: Boards, commissions, and committees',
                href: 'https://www.ci.richmond.ca.us/3696/Boards-Commissions-and-Committees',
                tier: 1,
              },
              {
                name: 'City of Richmond: Boards and commission meetings',
                href: 'https://www.ci.richmond.ca.us/4191/Richmond-Boards-and-Commissions',
                tier: 1,
              },
            ]}
          />
        </section>

        <aside className="rounded-lg border border-teal-200 bg-teal-50/60 p-5" aria-labelledby="reporting-heading">
          <h2 id="reporting-heading" className="text-xl font-semibold text-slate-900">
            For reporting and deeper context
          </h2>
          <p className="mt-2 text-base leading-relaxed text-slate-700">
            Richmond Commons is a reference desk for public records. Richmondside&apos;s guide
            adds reporting and broader context about city departments, county government,
            schools, and community life.
          </p>
          <SourceReferences
            sources={[
              {
                name: 'Richmondside: How Richmond works',
                href: 'https://richmondside.org/richmond-government-guide/',
                tier: 2,
              },
            ]}
          />
        </aside>
      </div>
    </article>
  )
}
