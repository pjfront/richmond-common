import type { Metadata } from 'next'
import { CIVIC_STORIES } from '@/data/civic-stories'
import { CivicLanguageScope, Localized } from '@/components/civic/CivicLanguage'
import { SourceNote, StoryCard } from '@/components/civic/CivicStory'

export const metadata: Metadata = {
  title: 'The stories shaping Richmond',
  description: 'Follow Richmond’s Chevron settlement, fire-station bond and Flock camera decisions through dated official sources, open questions and recent agendas.',
  alternates: { canonical: '/stories' },
}

export default function StoriesPage() {
  return <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10 lg:px-8"><CivicLanguageScope>
    <header className="mb-10 max-w-3xl">
      <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-civic-navy"><Localized en="Follow the thread" es="Seguir el hilo" /></p>
      <h1 className="text-4xl font-semibold leading-tight tracking-tight sm:text-5xl"><Localized en="The stories shaping Richmond" es="Los temas que dan forma a Richmond" /></h1>
      <p className="mt-5 text-lg leading-8 text-slate-700"><Localized en="Local decisions unfold over months and years. Start with what’s established, see what’s still unresolved, and follow the next public decision." es="Las decisiones locales se desarrollan durante meses y años. Empiece por lo que está establecido, vea qué sigue pendiente y siga la próxima decisión pública." /></p>
    </header>
    <div className="grid gap-6 lg:grid-cols-3">{CIVIC_STORIES.map(story => <StoryCard story={story} key={story.slug} headingLevel="h2" />)}</div>
    <div className="mt-10 max-w-3xl border-t border-slate-200 pt-6"><SourceNote /></div>
  </CivicLanguageScope></div>
}
