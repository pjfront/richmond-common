import { describe, expect, it } from 'vitest'
import { escapeCsv } from './CsvDownloadButton'

describe('escapeCsv', () => {
  it.each([
    ['=1+1', "'=1+1"],
    ['+SUM(A1:A2)', "'+SUM(A1:A2)"],
    ['-10+20', "'-10+20"],
    ['@cmd', "'@cmd"],
    ['\t=1+1', "'\t=1+1"],
    ['\r=1+1', '"\'\r=1+1"'],
    ['\n=1+1', '"\'\n=1+1"'],
    ['＝1+1', "'＝1+1"],
    ['＋SUM(A1:A2)', "'＋SUM(A1:A2)"],
    ['－10+20', "'－10+20"],
    ['＠cmd', "'＠cmd"],
  ])('neutralizes formula-leading string cells: %s', (value, expected) => {
    expect(escapeCsv(value)).toBe(expected)
  })

  it.each([
    ['ordinary text', 'ordinary text'],
    [' Richmond resident', ' Richmond resident'],
    ['1+1', '1+1'],
  ])('does not alter safe string cells: %s', (value, expected) => {
    expect(escapeCsv(value)).toBe(expected)
  })

  it('preserves numeric values, including negative numbers', () => {
    expect(escapeCsv(-10)).toBe('-10')
    expect(escapeCsv(42)).toBe('42')
  })

  it.each([
    ['Richmond, California', '"Richmond, California"'],
    ['She said "yes"', '"She said ""yes"""'],
    ['first line\nsecond line', '"first line\nsecond line"'],
    ['=SUM(1,2)', '"\'=SUM(1,2)"'],
  ])('applies RFC 4180 quoting after safety neutralization: %s', (value, expected) => {
    expect(escapeCsv(value)).toBe(expected)
  })

  it('renders null as an empty cell', () => {
    expect(escapeCsv(null)).toBe('')
  })
})
