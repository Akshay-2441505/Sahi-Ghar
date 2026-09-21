import type { ScheduleItem } from './api'

// The API sends naive UTC datetimes (no "Z"); without this the browser reads them as local time.
const asUtc = (value: string) => (/T[\d:.]+$/.test(value) ? `${value}Z` : value)

export function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(asUtc(value)).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

/** The source publishes year and month only, so never show a day. */
export function formatMonthYear(year: number | null, month: number | null): string {
  if (!year) return '—'
  return month ? `${MONTHS[month - 1]} ${year}` : String(year)
}

export function outcomeText(item: Pick<ScheduleItem, 'outcome' | 'months_extended' | 'covid_months'>): string {
  switch (item.outcome) {
    case 'extended':
      return `Registration extended by ${item.months_extended} months` +
        (item.covid_months ? `, plus ${item.covid_months} months of COVID-19 relief` : '')
    case 'covid_only':
      return `Extended only under COVID-19 relief (${item.covid_months} months)`
    case 'not_extended':
      return 'Original end date passed; no extension on record'
    case 'within_registration':
      return 'Within the registered period'
    default:
      return 'No end date in the filing'
  }
}
