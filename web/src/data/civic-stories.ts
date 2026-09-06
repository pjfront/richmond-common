/** Initial source-checked context, not a claim of exhaustive coverage.
 * New facts require dated evidence; agenda matches never change these outcomes.
 * English and Spanish copy share the same source IDs and publication version.
 */
export type StoryLanguage = 'en' | 'es'
export type LocalizedText = Record<StoryLanguage, string>
const text = (en: string, es: string): LocalizedText => ({ en, es })

export interface CivicSource {
  id: string
  label: LocalizedText
  url: string
  checkedAt: string
  tier: 1
}

export interface StoryEvent {
  date: string
  dateLabel?: LocalizedText
  title: LocalizedText
  text: LocalizedText
  state: 'decision' | 'proposal' | 'record'
  sourceId: string
}

export interface CivicStory {
  slug: string
  title: LocalizedText
  category: LocalizedText
  question: LocalizedText
  summary: LocalizedText
  why: LocalizedText
  disputed: LocalizedText
  next: LocalizedText
  coverage: LocalizedText
  status: LocalizedText
  nextDate?: string
  aliases: string[]
  sourceIds: string[]
  events: StoryEvent[]
}

export const STORY_CONTEXT_VERSION = '2026-09-06.2'
export const STORY_CONTEXT_CHECKED_AT = '2026-09-06'
export const CITY_AGENDAS_URL = 'https://www.richmondca.gov/4157/City-of-Richmond-Council-Meetings'

export const CIVIC_SOURCES: Record<string, CivicSource> = {
  'chevron-agreement': {
    id: 'chevron-agreement',
    label: text('City announcement of the Chevron agreement · August 8, 2024', 'Anuncio municipal del acuerdo con Chevron · 8 de agosto de 2024'),
    url: 'https://myemail.constantcontact.com/Richmond-Secures--550-Million-Settlement-with-Chevron-to-Fund-Vital-City-Services.html?aid=lI4KfozjI3M&soid=1141161791641',
    checkedAt: STORY_CONTEXT_CHECKED_AT, tier: 1,
  },
  'budget-2026': {
    id: 'budget-2026',
    label: text('City Finance Department · adopted 2026–27 budget overview', 'Departamento de Finanzas · resumen del presupuesto aprobado para 2026–27'),
    url: 'https://www.richmondca.gov/998/FY-2026-27-Adopted-Budget---Financial-Sn',
    checkedAt: STORY_CONTEXT_CHECKED_AT, tier: 1,
  },
  'fire-bond': {
    id: 'fire-bond',
    label: text('Resolution 143-26 · July 28, 2026 · pages 1–2', 'Resolución 143-26 · 28 de julio de 2026 · páginas 1–2'),
    url: 'https://www.richmondca.gov/Archive.aspx?ADID=17838#page=1',
    checkedAt: STORY_CONTEXT_CHECKED_AT, tier: 1,
  },
  'runoff-2026': {
    id: 'runoff-2026',
    label: text('Resolution 119-26 · July 21, 2026 · page 2', 'Resolución 119-26 · 21 de julio de 2026 · página 2'),
    url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785#page=2',
    checkedAt: STORY_CONTEXT_CHECKED_AT, tier: 1,
  },
  'flock-march-vote': {
    id: 'flock-march-vote',
    label: text('March 17, 2026 council minutes · item X.2 · pages 10–11', 'Acta del Concejo del 17 de marzo de 2026 · punto X.2 · páginas 10–11'),
    url: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/17557#page=10',
    checkedAt: STORY_CONTEXT_CHECKED_AT, tier: 1,
  },
  'flock-policy': {
    id: 'flock-policy',
    label: text('Richmond Police · license plate reader policies and reports', 'Policía de Richmond · políticas e informes sobre lectores de placas'),
    url: 'https://www.richmondca.gov/4597/Flock-SafetyAutomated-License-Plate-Read',
    checkedAt: STORY_CONTEXT_CHECKED_AT, tier: 1,
  },
}

export const CIVIC_STORIES: CivicStory[] = [
  {
    slug: 'chevron-settlement-and-city-budget',
    title: text('Chevron money and the city budget', 'El dinero de Chevron y el presupuesto municipal'),
    category: text('Public money', 'Dinero público'),
    question: text('What becomes of the settlement money?', '¿Qué pasa con el dinero del acuerdo?'),
    summary: text('Richmond announced a $550 million agreement with Chevron over ten years. The city’s annual budget is where spending choices take shape. An agreement, a budget allocation and a completed project are three different steps.', 'Richmond anunció un acuerdo de $550 millones con Chevron a lo largo de diez años. El presupuesto anual define las decisiones de gasto. Un acuerdo, una asignación presupuestaria y un proyecto terminado son tres pasos distintos.'),
    why: text('The adopted 2026–27 budget funds services including streets, libraries, parks and public safety. Following individual allocations helps explain what residents receive, rather than treating the whole settlement as money already spent.', 'El presupuesto aprobado para 2026–27 financia calles, bibliotecas, parques y seguridad pública, entre otros servicios. Seguir cada asignación permite entender qué reciben los residentes, sin confundir el acuerdo total con dinero ya gastado.'),
    disputed: text('How to use the funds is a spending decision. This starting record does not assign positions to officials or claim a complete account of settlement-funded projects.', 'El uso de los fondos requiere decisiones de gasto. Este registro inicial no atribuye posturas a funcionarios ni presenta una lista completa de proyectos financiados por el acuerdo.'),
    next: text('Watch for budget changes, contracts and reports on completed work. A new agenda item is a proposal to consider, not proof that a project was funded or finished.', 'Busque cambios presupuestarios, contratos e informes de obras terminadas. Un nuevo punto del orden del día es un asunto por considerar, no prueba de financiamiento o conclusión.'),
    coverage: text('Agreement terms and the adopted budget overview are linked below. Individual payments, project allocations and completed work have not yet been reconciled here.', 'Abajo se enlazan los términos anunciados y el resumen del presupuesto aprobado. Aquí todavía no se han cotejado los pagos, las asignaciones y las obras terminadas.'),
    status: text('Budget adopted · follow-through to track', 'Presupuesto aprobado · ejecución por seguir'),
    aliases: ['chevron', 'polluters pay', 'settlement funds', 'city budget', 'operating budget', 'proposed budget', 'budget amendment', 'mid-year budget', 'midyear budget'],
    sourceIds: ['chevron-agreement', 'budget-2026'],
    events: [
      { date: '2024-08-08', title: text('The city announces a ten-year agreement', 'La ciudad anuncia un acuerdo de diez años'), text: text('The announced schedule is $50 million annually for five years, followed by $60 million annually for five years. Council decides how General Fund money is allocated.', 'El calendario anunciado prevé $50 millones anuales durante cinco años y $60 millones anuales durante los cinco siguientes. El Concejo decide las asignaciones del Fondo General.'), state: 'record', sourceId: 'chevron-agreement' },
      { date: '2026-07-01', dateLabel: text('Budget year 2026–27', 'Año presupuestario 2026–27'), title: text('The adopted budget provides the spending framework', 'El presupuesto aprobado establece el marco de gasto'), text: text('The Finance Department’s overview separates the General Fund, capital projects and other funds. It is a spending plan, not a receipt for completed services.', 'El resumen de Finanzas distingue el Fondo General, los proyectos de capital y otros fondos. Es un plan de gasto, no un comprobante de servicios ya prestados.'), state: 'record', sourceId: 'budget-2026' },
    ],
  },
  {
    slug: 'fire-stations-and-emergency-response',
    title: text('The fire-station bond', 'El bono para estaciones de bomberos'),
    category: text('November ballot', 'Elección de noviembre'),
    question: text('What would voters authorize?', '¿Qué autorizarían los votantes?'),
    summary: text('The council placed a proposal for up to $120 million in fire-station bonds on the November 3 ballot. Placing it on the ballot did not approve the borrowing. Voters decide, with a two-thirds approval requirement.', 'El Concejo puso en la boleta del 3 de noviembre una propuesta de bonos por hasta $120 millones para estaciones de bomberos. Incluirla no autorizó el préstamo. Deciden los votantes; se requiere la aprobación de dos tercios.'),
    why: text('Bonds borrow money for work now and repay it over time. Read the project description and tax estimate together; the borrowing limit is not the total cost of repayment.', 'Los bonos permiten pedir dinero prestado para realizar obras y pagarlo con el tiempo. Lea juntos la descripción de proyectos y el cálculo del impuesto; el límite del préstamo no es el costo total de pagarlo.'),
    disputed: text('The decision is whether to authorize the proposed borrowing and repayment. Ballot arguments and any final measure letter are not yet verified in this guide.', 'La decisión es si se autoriza el préstamo propuesto y su pago. Esta guía todavía no ha verificado los argumentos electorales ni la letra definitiva de la medida.'),
    next: text('Read the adopted resolution before deciding. Check the official voter guide for the final ballot wording, arguments and voting instructions.', 'Lea la resolución aprobada antes de decidir. Consulte la guía oficial del votante para ver la redacción final, los argumentos y las instrucciones para votar.'),
    coverage: text('This explains the adopted ballot-placement resolution. It does not report an election result or claim that bond-funded work has begun.', 'Este resumen explica la resolución que incluyó la propuesta en la boleta. No informa un resultado electoral ni afirma que hayan comenzado las obras financiadas por bonos.'),
    status: text('On the ballot · voters decide November 3', 'En la boleta · se decide el 3 de noviembre'),
    nextDate: '2026-11-03',
    aliases: ['fire station', 'fire stations', 'fire-station', 'fire-stations', 'fire facilities', 'fire bond', 'fire infrastructure'],
    sourceIds: ['fire-bond'],
    events: [{ date: '2026-07-28', title: text('Council places the bond before voters', 'El Concejo somete el bono a votación'), text: text('Resolution 143-26 calls the November 3 election on up to $120 million in bonds. This is approval to ask voters, not voter approval of the debt.', 'La Resolución 143-26 convoca la elección del 3 de noviembre sobre bonos de hasta $120 millones. Autoriza consultar al electorado; no equivale a su aprobación de la deuda.'), state: 'decision', sourceId: 'fire-bond' }],
  },
  {
    slug: 'flock-cameras-and-data-privacy',
    title: text('Flock cameras and data privacy', 'Cámaras Flock y privacidad de datos'),
    category: text('Public safety', 'Seguridad pública'),
    question: text('Who controls the data?', '¿Quién controla los datos?'),
    summary: text('On March 17, the council voted 4–3 to direct negotiations with Flock, seeking restrictions on unauthorized sharing and city ownership of data.', 'El 17 de marzo, el Concejo votó 4–3 para ordenar negociaciones con Flock, buscando limitar el intercambio no autorizado y asegurar la propiedad municipal de los datos.'),
    why: text('The issue connects policing technology with rules for access to residents’ data.', 'El asunto conecta la tecnología policial con las reglas de acceso a los datos de residentes.'),
    disputed: text('Members considered seeking another California provider instead. The negotiating direction passed.', 'Se consideró buscar otro proveedor de California. Se aprobó la instrucción de negociar.'),
    next: text('Look for the resulting contract and data-sharing rules.', 'Busque el contrato resultante y sus reglas para compartir datos.'),
    coverage: text('Negotiating instructions do not prove a final contract was signed. Later implementation is not verified here.', 'La instrucción de negociar no prueba que se firmó un contrato. Aquí no se ha verificado su ejecución posterior.'),
    status: text('Recorded decision · implementation to verify', 'Decisión registrada · ejecución por verificar'),
    aliases: ['flock', 'license plate reader', 'licence plate reader', 'alpr', 'automated license plate'],
    sourceIds: ['flock-march-vote', 'flock-policy'],
    events: [{ date: '2026-03-17', title: text('A split vote directs negotiations', 'Una votación dividida ordena negociar'), text: text('Bana, Brown, Zepeda and Robinson voted yes; Jimenez, Wilson and Martinez voted no. See the exact motion in the minutes.', 'Bana, Brown, Zepeda y Robinson votaron sí; Jimenez, Wilson y Martinez votaron no. Consulte la moción exacta en el acta.'), state: 'decision', sourceId: 'flock-march-vote' }],
  },
]

export function getCivicStory(slug: string): CivicStory | undefined {
  return CIVIC_STORIES.find(story => story.slug === slug)
}

/** Exact reviewed phrase aliases group discovery results, not entities or votes. */
export function matchesCivicStory(story: CivicStory, title: string, topicLabel: string | null): boolean {
  const value = `${title} ${topicLabel ?? ''}`.toLocaleLowerCase('en-US').replace(/[–—]/g, '-').replace(/\s+/g, ' ')
  return story.aliases.some(alias => {
    const escaped = alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return new RegExp(`(?:^|[^a-z0-9])${escaped}(?:$|[^a-z0-9])`, 'i').test(value)
  })
}
