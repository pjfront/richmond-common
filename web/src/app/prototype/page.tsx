import Link from 'next/link'

export const metadata = { title: 'Design Prototypes — Richmond Commons' }

const prototypes = [
  {
    href: '/prototype/know',
    name: 'Know Your City',
    desc: 'Institutional memory, not a news feed. Search-forward hero, meeting heartbeat, knowledge threads for newcomers ("what\'s the deal with the refinery?"), civic regulars, platform scope. The city\'s brain, not its bulletin board.',
    color: 'bg-[#2d5f4f]',
    textColor: 'text-white',
    badge: 'NEW',
  },
  {
    href: '/prototype/record',
    name: 'The Front Page',
    desc: 'Newspaper editorial meets civic data. Warm earth tones, dark masthead, two-column layout. One lead story told big, then community voice, split votes, issue tags, and council. Opinionated about hierarchy.',
    color: 'bg-[#1a2332]',
    textColor: 'text-white',
  },
  {
    href: '/prototype/threads',
    name: 'Threads',
    desc: 'Dark, immersive, issue-first. Richmond politics as ongoing storylines. Four active local issues with color-coded timeline cards. You follow a thread, not an entity. Council and meetings are secondary.',
    color: 'bg-[#0f1419]',
    textColor: 'text-white',
  },
  {
    href: '/prototype/civic',
    name: 'Civic',
    desc: 'Bold teal identity, countdown strips, big numbers for community engagement. "What\'s happening in Richmond government" as the question. Clean, warm, modern. Treats every section as a self-contained story.',
    color: 'bg-[#1b4965]',
    textColor: 'text-white',
  },
]

export default function PrototypeIndex() {
  return (
    <div className="min-h-screen bg-[#faf9f7]">
      <div className="max-w-2xl mx-auto px-6 pt-16 pb-20">
        <h1 className="text-3xl font-bold text-[#1a2332] tracking-tight">Design Prototypes</h1>
        <p className="text-[#8a7e72] text-lg mt-2 mb-12 max-w-md">
          Three radically different approaches to presenting civic information. Same data, different editorial choices.
        </p>

        <div className="space-y-4">
          {prototypes.map((p) => (
            <Link
              key={p.href}
              href={p.href}
              className="block group rounded-xl overflow-hidden transition-transform hover:scale-[1.01]"
            >
              <div className={`${p.color} ${p.textColor} p-6 sm:p-8`}>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold">{p.name}</h2>
                  {'badge' in p && p.badge && (
                    <span className="text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-white/20">
                      {p.badge}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm opacity-70 leading-relaxed max-w-lg">{p.desc}</p>
                <p className="mt-4 text-sm font-medium opacity-50 group-hover:opacity-80 transition-opacity">
                  View prototype &rarr;
                </p>
              </div>
            </Link>
          ))}
        </div>

        <div className="mt-12 pt-8 border-t border-[#e4dfd8]">
          <p className="text-sm text-[#8a7e72]">All prototypes use real data from the database. Nothing is mocked.</p>
          <Link href="/" className="text-sm text-[#8a7e72] hover:text-[#1a2332] transition-colors mt-2 inline-block">
            &larr; Back to current site
          </Link>
        </div>
      </div>
    </div>
  )
}
