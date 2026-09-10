import Link from 'next/link'
import { CIVIC_SOURCES, CITY_AGENDAS_URL, STORY_CONTEXT_CHECKED_AT, type CivicStory } from '@/data/civic-stories'
import type { ResidentSnapshot, StoryAgendaEntry } from '@/lib/queries/civic-stories'
import { CivicDate, Localized } from './CivicLanguage'

export const civicLink = 'inline-flex min-h-11 items-center gap-2 rounded-sm font-medium text-civic-navy underline decoration-slate-300 underline-offset-4 hover:decoration-civic-navy'

export function StoryCard({ story, featured = false, headingLevel = 'h3' }: { story: CivicStory; featured?: boolean; headingLevel?: 'h2' | 'h3' }) {
  const Heading = headingLevel
  return (
    <article className={`flex h-full flex-col border-t-4 border-civic-navy p-6 sm:p-7 ${featured ? 'bg-slate-100' : 'bg-white ring-1 ring-inset ring-slate-200'}`}>
      <p className="mb-4 text-sm font-semibold text-civic-navy"><Localized {...story.category} /></p>
      <Heading className="mb-3 text-2xl font-semibold leading-tight tracking-tight"><Link href={`/stories/${story.slug}`} className="rounded-sm hover:underline decoration-slate-300 underline-offset-4"><Localized {...story.title} /></Link></Heading>
      <p className="mb-4 leading-7 text-slate-700"><Localized {...story.summary} /></p>
      <p className="mb-5 text-sm font-medium leading-6 text-slate-600"><Localized {...story.status} /></p>
      <Link className={`${civicLink} mt-auto self-start`} href={`/stories/${story.slug}`}><Localized en="Follow this story" es="Seguir este tema" /><span aria-hidden="true">→</span></Link>
    </article>
  )
}

export function SourceLink({ sourceId }: { sourceId: string }) {
  const source = CIVIC_SOURCES[sourceId]
  return <a href={source.url} className={`${civicLink} text-sm leading-6`}><Localized {...source.label} /><span className="shrink-0" aria-hidden="true">↗</span></a>
}

export function SourceNote() {
  return <p className="text-sm leading-6 text-slate-600"><Localized en="AI-written explanations, checked against the linked official records on " es="Explicaciones redactadas con IA y verificadas con los registros oficiales enlazados el " /><CivicDate date={STORY_CONTEXT_CHECKED_AT} />. <Localized en="Core explanations are available in Spanish; source documents and imported agenda titles keep their original language." es="Las explicaciones principales están disponibles en español; los documentos y títulos de agenda conservan su idioma original." /></p>
}

export function StorySources({ story }: { story: CivicStory }) {
  return (
    <section id="sources" aria-labelledby="sources-heading" className="scroll-mt-8 border-t border-slate-200 pt-8">
      <h2 id="sources-heading" className="text-2xl font-semibold"><Localized en="Check the sources" es="Consultar las fuentes" /></h2>
      <p className="mt-2 leading-7 text-slate-600"><Localized en="Tier 1 · Official primary records. Each document supports the specific event or context beside its link." es="Nivel 1 · Registros oficiales primarios. Cada documento respalda el hecho o contexto que aparece junto a su enlace." /></p>
      <ul className="my-4 divide-y divide-slate-200">{story.sourceIds.map(id => <li key={id} className="py-2"><SourceLink sourceId={id} /></li>)}</ul>
      <SourceNote />
    </section>
  )
}

export function StoryTimeline({ story }: { story: CivicStory }) {
  return (
    <section aria-labelledby="story-timeline-heading">
      <h2 id="story-timeline-heading" className="mb-6 text-2xl font-semibold"><Localized en="How we got here" es="Cómo llegamos aquí" /></h2>
      <ol className="border-l-2 border-slate-300 pl-6 sm:pl-8">
        {story.events.map(event => (
          <li key={`${event.date}-${event.sourceId}`} className="relative pb-8 last:pb-0">
            <span aria-hidden="true" className="absolute -left-[31px] top-1 h-3 w-3 rounded-full bg-civic-navy sm:-left-[39px]" />
            <p className="mb-2 text-sm text-slate-600">{event.dateLabel ? <Localized {...event.dateLabel} /> : <CivicDate date={event.date} />}</p>
            <p className="mb-2 text-sm font-semibold text-civic-navy">{event.state === 'decision' ? <Localized en="Adopted action" es="Acción aprobada" /> : event.state === 'proposal' ? <Localized en="Proposal · voters have not decided" es="Propuesta · pendiente del voto popular" /> : <Localized en="Official record" es="Registro oficial" />}</p>
            <h3 className="text-xl font-semibold"><Localized {...event.title} /></h3>
            <p className="mt-2 leading-7 text-slate-700"><Localized {...event.text} /></p>
            <SourceLink sourceId={event.sourceId} />
          </li>
        ))}
      </ol>
    </section>
  )
}

const STORY_AGENDA_DISPLAY_LIMIT = 8

function StoryAgendaEntries({ entries }: { entries: StoryAgendaEntry[] }) {
  return <ul className="divide-y divide-slate-200">{entries.map(entry => <li key={entry.id} className="py-4">
    <p className="mb-1 text-sm text-slate-600"><CivicDate date={entry.meeting_date} /> · <Localized en="Item" es="Punto" /> {entry.item_number}</p>
    <Link href={entry.href} className={`${civicLink} text-base leading-7`} lang="en">{entry.title}</Link>
  </li>)}</ul>
}

export function StoryAgenda({ story, snapshot }: { story: CivicStory; snapshot: ResidentSnapshot }) {
  const entries = snapshot.entries[story.slug] ?? []
  const upcoming = entries.filter(entry => entry.upcoming).sort((a, b) => a.meeting_date.localeCompare(b.meeting_date) || a.meeting_id.localeCompare(b.meeting_id) || a.item_number.localeCompare(b.item_number, 'en', { numeric: true }))
  const recent = entries.filter(entry => !entry.upcoming).sort((a, b) => b.meeting_date.localeCompare(a.meeting_date) || a.meeting_id.localeCompare(b.meeting_id) || a.item_number.localeCompare(b.item_number, 'en', { numeric: true }))
  const next = upcoming[0]
  const nextEntries = next ? upcoming.filter(entry => entry.meeting_id === next.meeting_id) : []
  return (
    <section id="story-agenda" aria-labelledby="story-agenda-heading" className="scroll-mt-8 border-t border-slate-200 pt-8">
      <h2 id="story-agenda-heading" className="text-2xl font-semibold"><Localized en="Follow the next step" es="Seguir el próximo paso" /></h2>
      <p className="mt-2 leading-7 text-slate-600"><Localized en="Automatically grouped by related phrases; this is a partial discovery aid. An agenda describes requested action; it does not establish what the council adopted." es="Agrupación automática por frases relacionadas; es una ayuda de búsqueda parcial. Una agenda describe lo que se solicita; no establece lo que aprobó el Concejo." /></p>
      {story.slug === 'chevron-settlement-and-city-budget' && <p className="mt-2 text-sm leading-6 text-slate-600"><Localized en="A related budget or Chevron entry does not establish that settlement money funded a particular project." es="Un punto relacionado con el presupuesto o Chevron no demuestra que un proyecto se financió con dinero del acuerdo." /></p>}
      {snapshot.status === 'unavailable' ? (
        <p role="status" className="my-5 border-l-4 border-amber-600 bg-amber-50 p-4 leading-7"><Localized en="Recent agenda records could not be loaded. This is a source-coverage gap, not evidence that nothing happened. The checked history above remains available." es="No se pudieron cargar los registros recientes de agenda. Es una falta de cobertura, no prueba de que no pasó nada. La historia verificada sigue disponible arriba." /></p>
      ) : (
        <>
          <div className="my-6 border-l-4 border-civic-navy bg-slate-100 p-4 sm:p-6">
            <h3 className="text-lg font-semibold"><Localized en="Coming up in the records checked" es="Lo próximo en los registros consultados" /></h3>
            {next ? <>
              <p className="mt-2 text-sm text-slate-600"><CivicDate date={next.meeting_date} /> · <Localized en="Scheduled agenda" es="Agenda programada" /></p>
              <StoryAgendaEntries entries={nextEntries.slice(0, STORY_AGENDA_DISPLAY_LIMIT)} />
              {nextEntries.length > STORY_AGENDA_DISPLAY_LIMIT && <p className="mb-3 text-sm leading-6 text-slate-600"><Localized en="Showing the first eight matching entries for this meeting." es="Se muestran los primeros ocho puntos coincidentes de esta reunión." /></p>}
              {next.agenda_url ? <>
                <a href={next.agenda_url} className={civicLink}><Localized en="Official agenda: time and how to take part" es="Agenda oficial: horario y cómo participar" /><span aria-hidden="true">↗</span></a>
                <p className="mt-2 text-sm leading-6 text-slate-600"><Localized en="Tier 1 · Official agenda. Check its latest meeting and public-comment instructions; plans can change." es="Nivel 1 · Agenda oficial. Consulte sus instrucciones vigentes para la reunión y los comentarios públicos; los planes pueden cambiar." /></p>
              </> : <p className="text-sm leading-6 text-slate-600"><Localized en="The original agenda link is unavailable here. Check the city calendar for meeting and participation details." es="El enlace a la agenda original no está disponible aquí. Consulte el calendario municipal para conocer los detalles de la reunión y cómo participar." /></p>}
              {upcoming.length > nextEntries.length && <p className="mt-2 text-sm leading-6 text-slate-600"><Localized en="Other future meetings also matched. The earliest meeting found is shown here; check the city calendar for later agendas." es="También hubo coincidencias en otras reuniones futuras. Aquí se muestra la primera encontrada; consulte las agendas posteriores en el calendario municipal." /></p>}
            </> : <p className="mt-3 leading-7"><Localized en="No matching upcoming agenda item was found in the meetings checked. That does not mean no action is planned. Check the city calendar for newly posted agendas or a different title." es="No se encontró un punto coincidente en las próximas reuniones consultadas. Eso no significa que no se planee actuar. Consulte el calendario municipal para ver nuevas agendas o títulos diferentes." /></p>}
          </div>
          <h3 className="text-lg font-semibold"><Localized en="Recent agenda trail" es="Recorrido por las agendas recientes" /></h3>
          {recent.length ? <StoryAgendaEntries entries={recent.slice(0, STORY_AGENDA_DISPLAY_LIMIT)} /> : <p className="my-4 leading-7 text-slate-600"><Localized en="No matching titles were found in the past council meetings checked. Related action may appear under another title or in records outside this window." es="No se encontraron títulos coincidentes en las reuniones anteriores consultadas. Puede haber acciones relacionadas con otro título o fuera de este período." /></p>}
          {recent.length > STORY_AGENDA_DISPLAY_LIMIT && <p className="mb-3 text-sm leading-6 text-slate-600"><Localized en="Showing the eight most recent matching agenda entries." es="Se muestran los ocho puntos de agenda coincidentes más recientes." /></p>}
          <p className="mb-3 text-sm leading-6 text-slate-600"><Localized en="Discovery window: " es="Período de búsqueda: " />{snapshot.recent.length} <Localized en="recent and " es="reuniones recientes y " />{snapshot.upcoming.length} <Localized en="upcoming council meetings. " es="próximas reuniones del Concejo. " />{snapshot.itemLimitReached && <Localized en="The agenda row limit was reached; this list may be incomplete, including earlier upcoming matches. " es="Se alcanzó el límite de registros; la lista puede estar incompleta, incluso para próximas reuniones más cercanas. " />}{snapshot.fetchedAt && <><Localized en="Records checked " es="Registros consultados el " /><CivicDate date={snapshot.fetchedAt.slice(0, 10)} />.</>}</p>
        </>
      )}
      <a href={CITY_AGENDAS_URL} className={civicLink}><Localized en="Open the city’s meeting calendar" es="Abrir el calendario municipal" /><span aria-hidden="true">↗</span></a>
    </section>
  )
}
