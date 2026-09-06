import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { CIVIC_STORIES, getCivicStory } from '@/data/civic-stories'
import { getResidentSnapshot } from '@/lib/queries/civic-stories'
import { CivicLanguageScope, Localized } from '@/components/civic/CivicLanguage'
import { civicLink, SourceNote, StoryAgenda, StorySources, StoryTimeline } from '@/components/civic/CivicStory'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import PublishedCivicBriefs from '@/components/PublishedCivicBriefs'

export const revalidate = 3600
export const dynamicParams = false
export function generateStaticParams() { return CIVIC_STORIES.map(story => ({ slug: story.slug })) }

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const story = getCivicStory((await params).slug)
  return story ? { title: story.title.en, description: story.summary.en, alternates: { canonical: `/stories/${story.slug}` } } : { title: 'Story not found' }
}

export default async function StoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const story = getCivicStory((await params).slug)
  if (!story) notFound()
  const snapshot = await getResidentSnapshot()
  return <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10 lg:px-8"><CivicLanguageScope>
    <Link href="/stories" className={`${civicLink} mb-6`}><span aria-hidden="true">←</span><Localized en="All stories" es="Todos los temas" /></Link>
    <header className="mb-10 max-w-3xl">
      <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-civic-navy"><Localized {...story.category} /></p>
      <h1 className="text-4xl font-semibold leading-tight tracking-tight sm:text-5xl"><Localized {...story.title} /></h1>
      <p className="mt-5 text-xl leading-8 text-slate-700"><Localized {...story.summary} /></p>
      <p className="mt-5 inline-block border-l-4 border-civic-navy bg-slate-100 px-4 py-2 font-medium leading-7"><Localized {...story.status} /></p>
      <div className="mt-5"><SourceNote /></div>
    </header>
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:gap-14">
      <div className="min-w-0 space-y-10">
        <section aria-labelledby="story-question-heading"><h2 id="story-question-heading" className="text-2xl font-semibold"><Localized {...story.question} /></h2><p className="mt-3 leading-7 text-slate-700"><Localized {...story.why} /></p></section>
        <StoryTimeline story={story} />
        <PublishedCivicBriefs subjectKey={story.slug} />
        <StoryAgenda story={story} snapshot={snapshot} />
        <StorySources story={story} />
        <div className="flex min-h-11 items-center"><SuggestCorrectionLink /></div>
      </div>
      <aside className="space-y-7 border-t-4 border-civic-navy bg-slate-100 p-6 sm:p-7">
        <section><h2 className="text-xl font-semibold"><Localized en="What remains open" es="Qué sigue pendiente" /></h2><p className="mt-3 leading-7 text-slate-700"><Localized {...story.disputed} /></p></section>
        <section className="border-t border-slate-300 pt-6"><h2 className="text-xl font-semibold"><Localized en="What to watch next" es="Qué observar ahora" /></h2><p className="mt-3 leading-7 text-slate-700"><Localized {...story.next} /></p>{story.nextDate && <Link className={`${civicLink} mt-2`} href="/elections/2026-general"><Localized en="See the November choices" es="Ver las opciones de noviembre" /><span aria-hidden="true">→</span></Link>}</section>
        <section className="border-t border-slate-300 pt-6"><h2 className="text-base font-semibold"><Localized en="What this page cannot yet tell you" es="Lo que esta página aún no puede confirmar" /></h2><p className="mt-3 text-sm leading-6 text-slate-700"><Localized {...story.coverage} /></p></section>
      </aside>
    </div>
  </CivicLanguageScope></div>
}
