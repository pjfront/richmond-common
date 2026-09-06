'use client'

import { createContext, useContext, useState, type ReactNode } from 'react'
import type { LocalizedText, StoryLanguage } from '@/data/civic-stories'

const LanguageContext = createContext<{ language: StoryLanguage; setLanguage: (language: StoryLanguage) => void } | null>(null)

/** Keep the chosen guide language through client-side navigation. */
export function CivicLanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<StoryLanguage>('en')
  return <LanguageContext.Provider value={{ language, setLanguage }}>{children}</LanguageContext.Provider>
}

/** Only checked explanatory copy changes language; imported records retain theirs. */
export function CivicLanguageScope({ children }: { children: ReactNode }) {
  const sharedLanguage = useContext(LanguageContext)
  const [localLanguage, setLocalLanguage] = useState<StoryLanguage>('en')
  const { language, setLanguage } = sharedLanguage ?? { language: localLanguage, setLanguage: setLocalLanguage }
  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      <div lang={language}>
        <div className="mb-6 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-slate-200 pb-4 sm:mb-8">
          <p className="text-sm text-slate-600"><Localized en="Richmond, California · Public records, local context" es="Richmond, California · Registros públicos y contexto local" /></p>
          <div className="flex items-center gap-1" role="group" aria-label="Guide language / Idioma de la guía">
            {(['en', 'es'] as const).map(locale => (
              <button key={locale} type="button" lang={locale} aria-pressed={language === locale} onClick={() => setLanguage(locale)} className={`min-h-11 rounded-md px-3 text-sm font-medium ${language === locale ? 'bg-civic-navy text-white' : 'text-slate-700 hover:bg-slate-100'}`}>
                {locale === 'en' ? 'English' : 'Español'}
              </button>
            ))}
          </div>
        </div>
        {children}
      </div>
    </LanguageContext.Provider>
  )
}

export function Localized({ en, es }: LocalizedText) {
  return <>{useContext(LanguageContext)?.language === 'es' ? es : en}</>
}

export function CivicDate({ date }: { date: string }) {
  const language = useContext(LanguageContext)?.language ?? 'en'
  return <time dateTime={date}>{new Intl.DateTimeFormat(language === 'es' ? 'es-US' : 'en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`))}</time>
}
