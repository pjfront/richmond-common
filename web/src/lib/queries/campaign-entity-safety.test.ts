import { describe, expect, it, vi } from 'vitest'
import {
  CampaignEntityDataError,
  campaignEntityRows,
  completeCampaignEntityRows,
} from './campaign-entity-safety'

describe('campaign entity query completeness', () => {
  it('returns a response only when the exact count proves it is complete', () => {
    const rows = [{ id: 'one' }, { id: 'two' }]

    expect(
      completeCampaignEntityRows({
        dataset: 'Fixture',
        data: rows,
        error: null,
        count: 2,
        maximumRows: 100,
      }),
    ).toBe(rows)
  })

  it('distinguishes a query error from a legitimate empty response', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() =>
      completeCampaignEntityRows({
        dataset: 'Fixture',
        data: null,
        error: { message: 'timeout' },
        count: null,
        maximumRows: 100,
      }),
    ).toThrowError(
      expect.objectContaining<Partial<CampaignEntityDataError>>({
        failure: 'query-error',
      }),
    )
    expect(consoleError).toHaveBeenCalledOnce()
    consoleError.mockRestore()
  })

  it('preserves the legacy empty fallback for unrelated non-strict callers', () => {
    expect(
      campaignEntityRows({
        dataset: 'Fixture',
        data: null,
        error: { message: 'timeout' },
        count: null,
        maximumRows: 100,
        requireComplete: false,
      }),
    ).toEqual([])
  })

  it.each([
    { data: null, count: null, maximumRows: 100 },
    { data: [{ id: 'one' }], count: 2, maximumRows: 100 },
    { data: [{ id: 'one' }], count: 1, maximumRows: 1 },
  ])('rejects incomplete or ceiling-bound responses: %o', (response) => {
    expect(() =>
      completeCampaignEntityRows({
        dataset: 'Fixture',
        error: null,
        ...response,
      }),
    ).toThrowError(
      expect.objectContaining<Partial<CampaignEntityDataError>>({
        failure: 'incomplete',
      }),
    )
  })
})
