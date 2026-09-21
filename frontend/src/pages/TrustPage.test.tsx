import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ProjectPayload } from '../api'
import { TrustPageView } from './TrustPage'

const data: ProjectPayload = {
  project: { id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', city: 'Pune', locality: null,
    registration_end_date: '2022-01-01', extended_end_date: null, promoter_name: 'Shree Realty LLP', source_document_id: 1 },
  data_as_of: '2026-09-01T00:00:00',
  score_computed_at: '2026-09-01T00:00:00',
  score: {
    overall: 25,
    schedule: { available: true, reason: null, score: 50, extended: 1, not_extended: 1, covid_only: 0, within_registration: 0, unknown: 0, median_months_extended: 12 },
    complaints: { available: true, reason: null, score: 0, total: 2, pending: 1, order_issued: 1, order_not_executed: 1, unresolved: 2, project_count: 2 },
    declared: { available: true, reason: null, score: 33, total: 3, on_or_before: 1, later: 2, median_months_later: 23.65 },
    progress: { available: false, reason: 'not_yet_available', score: null },
  },
  group_promoters: [{ promoter_id: 1, name: 'Shree Realty LLP', source_document_id: 1 }],
  group_basis: null,
  schedule: [
    { project_id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', registration_end_date: '2022-01-01', extended_end_date: null,
      outcome: 'not_extended', months_extended: null, covid_months: null, source_document_id: 1 },
    { project_id: 2, name: 'Shree Gardens', rera_reg_no: 'MH-2', registration_end_date: '2022-01-01', extended_end_date: '2023-01-01',
      outcome: 'extended', months_extended: 12, covid_months: null, source_document_id: 2 },
  ],
  complaints: [
    { complaint_ref: 'C1', status: 'Hearing Scheduled', stage: 'pending', non_execution_applied: false,
      filed_year: 2024, filed_month: 3, order_url: null, source_document_id: 3 },
    { complaint_ref: 'C2', status: 'Order Approved', stage: 'order_issued', non_execution_applied: true,
      filed_year: 2023, filed_month: 11, order_url: 'https://example.test/C2.pdf', source_document_id: 3 },
  ],
  declared_history: [
    { name: 'Shree Old', project_type: 'Residential', original_proposed_date: '2015-01-01', actual_completion_date: '2016-07-01', source_document_id: 5 },
    { name: 'Shree Older', project_type: null, original_proposed_date: '2012-01-01', actual_completion_date: '2012-01-01', source_document_id: 5 },
  ],
  possibly_related: [
    { promoter_id: 3, name: 'Shree Realty Phase 2 LLP',
      evidence: { shared_count: 0, same_address: true, name_similarity: 100 }, source_document_id: 4 },
  ],
  sources: {
    '1': { url: 'https://maharera.example/p/1', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '2': { url: 'https://maharera.example/p/2', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '3': { url: 'https://maharera.example/c', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '4': { url: 'file:import.csv', origin: 'file-import', fetched_at: '2026-09-01T00:00:00' },
    '5': { url: 'https://maharera.example/app/1', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
  },
}

describe('TrustPageView', () => {
  it('shows the breakdown before the overall number, and never the overall alone', () => {
    render(<TrustPageView data={data} />)
    const breakdown = screen.getByRole('region', { name: 'Score breakdown' })
    expect(within(breakdown).getByText('Registration schedule')).toBeInTheDocument()
    expect(within(breakdown).getByText(/1 of 2 projects had their registration extended \(median 12 months\); 1 passed the original end date/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/1 hearing pending, 1 order issued; 1 with a request to enforce/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/Progress vs promise/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/Overall: 25\/100, the average of the sections above/)).toBeInTheDocument()
  })

  it('stamps the data date and states it is not a verdict', () => {
    render(<TrustPageView data={data} />)
    expect(screen.getByText(/Data as of 1 Sep(t)? 2026/)).toBeInTheDocument()
    expect(screen.getByText(/not an independent verdict/)).toBeInTheDocument()
  })

  it('never calls a project late, and says what the dates are', () => {
    render(<TrustPageView data={data} />)
    const schedule = screen.getByRole('region', { name: 'Registration schedule' })
    expect(within(schedule).getByText(/these are dates, not a verdict/)).toBeInTheDocument()
    expect(within(schedule).getByText('Registration extended by 12 months')).toBeInTheDocument()
    expect(within(schedule).getByText('Original end date passed; no extension on record')).toBeInTheDocument()
    expect(screen.queryByText(/\blate\b|delayed/i)).not.toBeInTheDocument()
  })

  it('shows complaints with the status exactly as published and only month and year', () => {
    render(<TrustPageView data={data} />)
    const complaints = screen.getByRole('region', { name: 'Complaints' })
    expect(within(complaints).getByText('Order Approved')).toBeInTheDocument()
    expect(within(complaints).getByText('March 2024')).toBeInTheDocument()
    expect(within(complaints).getByText('Yes, order not complied with')).toBeInTheDocument()
  })

  it('puts a source link beside every schedule and complaint row', () => {
    render(<TrustPageView data={data} />)
    for (const name of ['Registration schedule', 'Complaints']) {
      const rows = within(screen.getByRole('region', { name })).getAllByRole('row').slice(1)
      expect(rows.length).toBeGreaterThan(0)
      for (const row of rows) expect(within(row).getByText(/^Source, fetched/)).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: 'Original order' })).toHaveAttribute('href', 'https://example.test/C2.pdf')
  })

  it('keeps possibly related entities separate and labelled as not counted', () => {
    render(<TrustPageView data={data} />)
    const block = screen.getByRole('region', { name: 'Possibly related entities' })
    expect(within(block).getByText(/not counted in this score/)).toBeInTheDocument()
    expect(within(block).getByText(/Shree Realty Phase 2 LLP/)).toBeInTheDocument()
    expect(within(block).getByText(/same registered address/)).toBeInTheDocument()
    expect(within(block).getByText(/^Source, fetched/)).toBeInTheDocument()
    const schedule = screen.getByRole('region', { name: 'Registration schedule' })
    expect(within(schedule).queryByText(/Phase 2/)).not.toBeInTheDocument()
  })

  it('never presents complaints that were not collected as a clean record', () => {
    const c = data.score!.complaints
    const uncollected = { ...data, complaints: [], score: { ...data.score!, overall: 50,
      complaints: { ...c, available: false, score: null, reason: 'not_collected', total: 0, pending: 0, order_issued: 0, order_not_executed: 0, unresolved: 0 } } }
    render(<TrustPageView data={uncollected} />)
    expect(screen.queryByText(/No complaints on record/)).not.toBeInTheDocument()
    expect(screen.queryByText(/0 on record/)).not.toBeInTheDocument()
    const complaints = screen.getByRole('region', { name: 'Complaints' })
    expect(within(complaints).getByText(/not been collected/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Score breakdown' })).getByText(/Not collected for this data set/)).toBeInTheDocument()
  })

  it('says why builders are grouped as one, without showing the identifier', () => {
    const grouped = { ...data, group_basis: 'same PAN',
      group_promoters: [{ promoter_id: 1, name: 'Shree Realty LLP', source_document_id: 1 }, { promoter_id: 2, name: 'Shree Homes LLP', source_document_id: 1 }] }
    render(<TrustPageView data={grouped} />)
    const schedule = screen.getByRole('region', { name: 'Registration schedule' })
    expect(within(schedule).getByText(/grouped as one because the filings show the same PAN/)).toBeInTheDocument()
    expect(screen.queryByText(/pan:/)).not.toBeInTheDocument()
  })

  it('says how many partners or directors are shared, never who', () => {
    const shared = { ...data, possibly_related: [{ ...data.possibly_related[0], evidence: { shared_count: 2, same_address: false, name_similarity: 91 } }] }
    render(<TrustPageView data={shared} />)
    const block = screen.getByRole('region', { name: 'Possibly related entities' })
    expect(within(block).getByText(/shares 2 registered members/)).toBeInTheDocument()
  })

  it('shows the declared delivery record as the promoter’s own account, with a source per row', () => {
    render(<TrustPageView data={data} />)
    const breakdown = screen.getByRole('region', { name: 'Score breakdown' })
    expect(within(breakdown).getByText(/1 of 3 completed projects were declared finished on or before the proposed date; 2 later \(median 23.7 months\)/)).toBeInTheDocument()
    const declared = screen.getByRole('region', { name: 'Declared delivery record' })
    expect(within(declared).getByText(/declared by the promoter, not verified/)).toBeInTheDocument()
    expect(within(declared).getByText('Shree Old')).toBeInTheDocument()
    expect(within(declared).getByText('1 Jul 2016')).toBeInTheDocument()
    const rows = within(declared).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    for (const row of rows) expect(within(row).getByText(/^Source, fetched/)).toBeInTheDocument()
  })

  it('separates COVID-19 relief from the builder’s own extensions', () => {
    const covid = { ...data,
      score: { ...data.score!, schedule: { ...data.score!.schedule, covid_only: 1 } },
      schedule: [
        { ...data.schedule[1], months_extended: 84, covid_months: 12 },
        { ...data.schedule[0], project_id: 3, outcome: 'covid_only' as const, months_extended: null, covid_months: 6 },
      ] }
    render(<TrustPageView data={covid} />)
    const schedule = screen.getByRole('region', { name: 'Registration schedule' })
    expect(within(schedule).getByText('Registration extended by 84 months, plus 12 months of COVID-19 relief')).toBeInTheDocument()
    expect(within(schedule).getByText('Extended only under COVID-19 relief (6 months)')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Score breakdown' })).getByText(/1 only under COVID-19 relief \(not counted against the builder\)/)).toBeInTheDocument()
  })

  it('says so when no past projects were declared', () => {
    const none = { ...data, declared_history: [], score: { ...data.score!,
      declared: { available: false, reason: 'insufficient_history', score: null, total: 0, on_or_before: 0, later: 0, median_months_later: null } } }
    render(<TrustPageView data={none} />)
    expect(screen.getByText(/Not enough declared history/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Declared delivery record' })).getByText(/No completed projects were declared/)).toBeInTheDocument()
  })

  it('says so when there is not enough data instead of showing a number', () => {
    const empty = { ...data, score: { ...data.score!, overall: null,
      schedule: { ...data.score!.schedule, available: false, score: null, reason: 'insufficient_history' } } }
    render(<TrustPageView data={empty} />)
    expect(screen.getByText(/Not enough history to summarise/)).toBeInTheDocument()
  })
})
