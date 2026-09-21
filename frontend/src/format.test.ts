import { describe, expect, it } from 'vitest'
import { formatDate, formatMonthYear, outcomeText } from './format'

describe('formatDate', () => {
  it('reads naive API datetimes as UTC, not local time', () => {
    // 2026-09-01T00:00:00 must not become 31 Aug for viewers east of UTC (India is +05:30).
    expect(formatDate('2026-09-01T00:00:00')).toMatch(/^1 Sep(t)? 2026$/)
  })
  it('formats plain dates and handles null', () => {
    expect(formatDate('2022-01-01')).toMatch(/^1 Jan 2022$/)
    expect(formatDate(null)).toBe('—')
  })
})

describe('formatMonthYear', () => {
  it('never invents a day when the source gives year and month only', () => {
    expect(formatMonthYear(2024, 3)).toBe('March 2024')
    expect(formatMonthYear(2024, null)).toBe('2024')
    expect(formatMonthYear(null, null)).toBe('—')
  })
})

describe('outcomeText', () => {
  it('states the schedule against the original end date in neutral words', () => {
    expect(outcomeText({ outcome: 'extended', months_extended: 12, covid_months: null })).toBe('Registration extended by 12 months')
    expect(outcomeText({ outcome: 'not_extended', months_extended: null, covid_months: null })).toBe('Original end date passed; no extension on record')
    expect(outcomeText({ outcome: 'unknown', months_extended: null, covid_months: null })).toBe('No end date in the filing')
  })
})
