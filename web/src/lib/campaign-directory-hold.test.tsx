import type { ReactNode } from 'react'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const PAGE_NOT_FOUND = new Error('NEXT_HTTP_ERROR_FALLBACK;404')

const mocks = vi.hoisted(() => ({
  requireOperatorPage: vi.fn(),
  getPACListWithCycleBars: vi.fn(),
  getPACBySlug: vi.fn(),
  getPACList: vi.fn(),
  getPACContributions: vi.fn(),
  getPACOutgoing: vi.fn(),
  getPACIndependentExpenditures: vi.fn(),
  getOrgList: vi.fn(),
  getOrgBySlug: vi.fn(),
  getOrgOutgoing: vi.fn(),
  getOrgIndependentExpenditures: vi.fn(),
}))

vi.mock('@/lib/operator-page', () => ({
  requireOperatorPage: mocks.requireOperatorPage,
}))

vi.mock('@/lib/queries', () => ({
  getPACListWithCycleBars: mocks.getPACListWithCycleBars,
  getPACBySlug: mocks.getPACBySlug,
  getPACList: mocks.getPACList,
  getPACContributions: mocks.getPACContributions,
  getPACOutgoing: mocks.getPACOutgoing,
  getPACIndependentExpenditures: mocks.getPACIndependentExpenditures,
  getOrgList: mocks.getOrgList,
  getOrgBySlug: mocks.getOrgBySlug,
  getOrgOutgoing: mocks.getOrgOutgoing,
  getOrgIndependentExpenditures: mocks.getOrgIndependentExpenditures,
}))

vi.mock('@/components/OperatorGate', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('@/components/CampaignEntityFinancialDetails', () => ({
  default: () => null,
}))

vi.mock('@/components/CampaignEntityProfile', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('@/components/OrgList', () => ({
  default: () => null,
}))

vi.mock('@/app/pac/PACIndexClient', () => ({
  default: () => null,
}))

import PACIndexPage, {
  metadata as pacIndexMetadata,
} from '@/app/pac/page'
import PACProfilePage, {
  generateMetadata as generatePACMetadata,
} from '@/app/pac/[slug]/page'
import UnionsPage, {
  metadata as unionsMetadata,
} from '@/app/unions/page'
import CorporationsPage, {
  metadata as corporationsMetadata,
} from '@/app/corporations/page'
import OrgProfilePage, {
  generateMetadata as generateOrgMetadata,
} from '@/app/orgs/[slug]/page'

const pacProps = { params: Promise.resolve({ slug: 'example-pac' }) }
const orgProps = { params: Promise.resolve({ slug: 'example-union' }) }

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

describe('November campaign-directory hold', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.requireOperatorPage.mockResolvedValue(undefined)
  })

  it('rejects anonymous page and metadata requests before every directory query', async () => {
    mocks.requireOperatorPage.mockRejectedValue(PAGE_NOT_FOUND)

    await expect(PACIndexPage()).rejects.toBe(PAGE_NOT_FOUND)
    await expect(PACProfilePage(pacProps)).rejects.toBe(PAGE_NOT_FOUND)
    await expect(generatePACMetadata(pacProps)).rejects.toBe(PAGE_NOT_FOUND)
    await expect(UnionsPage()).rejects.toBe(PAGE_NOT_FOUND)
    await expect(CorporationsPage()).rejects.toBe(PAGE_NOT_FOUND)
    await expect(OrgProfilePage(orgProps)).rejects.toBe(PAGE_NOT_FOUND)
    await expect(generateOrgMetadata(orgProps)).rejects.toBe(PAGE_NOT_FOUND)

    for (const query of [
      mocks.getPACListWithCycleBars,
      mocks.getPACBySlug,
      mocks.getPACList,
      mocks.getPACContributions,
      mocks.getPACOutgoing,
      mocks.getPACIndependentExpenditures,
      mocks.getOrgList,
      mocks.getOrgBySlug,
      mocks.getOrgOutgoing,
      mocks.getOrgIndependentExpenditures,
    ]) {
      expect(query).not.toHaveBeenCalled()
    }
  })

  it('marks every held directory as non-indexable for authenticated operators', async () => {
    mocks.getPACBySlug.mockResolvedValue({
      name: 'Example Committee',
      sponsor_disclosure: null,
    })
    mocks.getOrgBySlug.mockResolvedValue({
      display_name: 'Example Union',
      entity_type: 'union',
    })

    expect(pacIndexMetadata.robots).toEqual({ index: false, follow: false })
    expect(unionsMetadata.robots).toEqual({ index: false, follow: false })
    expect(corporationsMetadata.robots).toEqual({ index: false, follow: false })
    await expect(generatePACMetadata(pacProps)).resolves.toMatchObject({
      robots: { index: false, follow: false },
    })
    await expect(generateOrgMetadata(orgProps)).resolves.toMatchObject({
      robots: { index: false, follow: false },
    })
  })

  it('removes public navigation and sends the legacy index to elections', () => {
    const navigation = source('../components/Nav.tsx')
    const legacyRedirect = source('../app/orgs/page.tsx')

    expect(navigation).not.toContain("label: 'Contributions'")
    expect(legacyRedirect).toContain("redirect('/elections')")
    expect(legacyRedirect).not.toContain("redirect('/unions')")
  })

  it('retains the operator detail and CSV-export surfaces without publishing them', () => {
    const heldPages = [
      '../app/pac/page.tsx',
      '../app/pac/[slug]/page.tsx',
      '../app/unions/page.tsx',
      '../app/corporations/page.tsx',
      '../app/orgs/[slug]/page.tsx',
    ]
    const operatorGateOpen = ['<', 'OperatorGate', '>'].join('')
    const operatorGateClose = ['</', 'OperatorGate', '>'].join('')
    for (const page of heldPages) {
      const pageSource = source(page)
      expect(pageSource).toContain("from '@/components/OperatorGate'")
      expect(pageSource).toContain(operatorGateOpen)
      expect(pageSource).toContain(operatorGateClose)
    }

    expect(source('../app/pac/page.tsx')).toContain('PACIndexClient')
    expect(source('../app/unions/page.tsx')).toContain('OrgList')
    expect(source('../app/corporations/page.tsx')).toContain('OrgList')
    expect(source('../app/pac/[slug]/page.tsx')).toContain(
      'CampaignEntityFinancialDetails',
    )
    expect(source('../app/orgs/[slug]/page.tsx')).toContain(
      'CampaignEntityFinancialDetails',
    )
    for (const table of [
      '../app/pac/[slug]/PACDonorTable.tsx',
      '../app/pac/[slug]/PACOutgoingTable.tsx',
      '../app/pac/[slug]/PACIndependentExpendituresTable.tsx',
    ]) {
      expect(source(table)).toContain('CsvDownloadButton')
    }
  })
})
