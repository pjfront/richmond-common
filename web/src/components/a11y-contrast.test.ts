import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function readComponent(filename: string): string {
  return readFileSync(fileURLToPath(new URL(filename, import.meta.url)), 'utf8')
}

describe('shared muted-text contrast', () => {
  it('keeps subscription form helper text on an AA-safe slate token', () => {
    const source = readComponent('./SubscribeForm.tsx')

    expect(source).toMatch(
      /<span className="text-slate-500 font-normal">\(optional\)<\/span>/,
    )
    expect(source).toMatch(
      /<p className="text-xs text-slate-500">\s*No spam\. Unsubscribe anytime\./,
    )
  })

  it('keeps the subscribe page source note on an AA-safe slate token', () => {
    const source = readComponent('../app/subscribe/page.tsx')

    expect(source).toMatch(
      /<p className="text-xs text-slate-500">\s*Explanations link to public records and identified reporting\./,
    )
  })

  it('keeps the footer version legible on the dark footer surface', () => {
    const source = readComponent('./Footer.tsx')

    expect(source).toMatch(
      /<p className="text-xs mt-1 text-slate-400">\s*v\{packageJson\.version\}/,
    )
  })
})
