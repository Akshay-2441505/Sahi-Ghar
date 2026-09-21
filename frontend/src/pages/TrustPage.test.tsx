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
    schedule: { available: true, reason: null, score: 50, extended: 1, not_extended: 1, within_registration: 0, unknown: 0, median_months_extended: 12 },
    complaints: { available: true, reason: null, score: 0, total: 2, pending: 1, order_issued: 1, order_not_executed: 1, unresolved: 2, project_count: 2 },
    progress: { available: false, reason: 'not_yet_available', score: null },
  },
  group_promoters: [{ promoter_id: 1, name: 'Shree Realty LLP', source_document_id: 1 }],
  schedule: [
    { project_id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', registration_end_date: '2022-01-01', extended_end_date: null,
      outcome: 'not_extended', months_extended: null, source_document_id: 1 },
    { project_id: 2, name: 'Shree Gardens', rera_reg_no: 'MH-2', registration_end_date: '2022-01-01', extended_end_date: '2023-01-01',
      outcome: 'extended', months_extended: 12, source_document_id: 2 },
  ],
  complaints: [
    { complaint_ref: 'C1', status: 'Hearing Scheduled', stage: 'pending', non_execution_applied: false,
      filed_year: 2024, filed_month: 3, order_url: null, source_document_id: 3 },
    { complaint_ref: 'C2', status: 'Order Approved', stage: 'order_issued', non_execution_applied: true,
      filed_year: 2023, filed_month: 11, order_url: 'https://example.test/C2.pdf', source_document_id: 3 },
  ],
  possibly_related: [
    { promoter_id: 3, name: 'Shree Realty Phase 2 LLP',
      evidence: { shared_partners: [], same_address: true, name_similarity: 100 }, source_document_id: 4 },
  ],
  sources: {
    '1': { url: 'https://maharera.example/p/1', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '2': { url: 'https://maharera.example/p/2', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '3': { url: 'https://maharera.example/c', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '4': { url: 'file:import.csv', origin: 'file-import', fetched_at: '2026-09-01T00:00:00' },
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

  it('says so when there is not enough data instead of showing a number', () => {
    const empty = { ...data, score: { ...data.score!, overall: null,
      schedule: { ...data.score!.schedule, available: false, score: null, reason: 'insufficient_history' } } }
    render(<TrustPageView data={empty} />)
    expect(screen.getByText(/Not enough history to summarise/)).toBeInTheDocument()
  })
})
