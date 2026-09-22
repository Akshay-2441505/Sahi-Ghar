import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Search from './Search'

function mockFetch(url: string) {
  if (url.includes('/coverage')) {
    return {
      ok: true,
      json: async () => ({
        states: [
          { state: 'MH', name: 'Maharashtra', area: 'Central Pune', projects: 2002 },
          { state: 'KA', name: 'Karnataka', area: 'Statewide', projects: 6501 },
        ],
      }),
    }
  }
  return {
    ok: true,
    json: async () => ({
      projects: [
        { id: 1, state: 'MH', name: 'Shree Heights', rera_reg_no: 'P1', city: 'Pune', promoter_id: 1, promoter_name: 'Shree Realty' },
        { id: 2, state: 'KA', name: 'Casagrand Meridian', rera_reg_no: 'PRM/KA/1', city: 'Bengaluru Urban', promoter_id: 2, promoter_name: 'Casa Grande' },
      ],
    }),
  }
}

describe('Search', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => mockFetch(url)))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows which state each result is registered in, so builders from different states are never confused', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    await userEvent.type(screen.getByLabelText(/Builder, project name/), 'casa')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(screen.getByText('Shree Heights')).toBeInTheDocument())
    const results = screen.getByText('Shree Heights').closest('ul')!
    expect(within(results).getByText('Maharashtra')).toBeInTheDocument()
    expect(within(results).getByText('Karnataka')).toBeInTheDocument()
  })

  it('states plainly what the site is and where it actually has data, with real counts', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/RERA/)
    const coverage = await screen.findByRole('region', { name: /coverage/i })
    expect(within(coverage).getByText('Maharashtra')).toBeInTheDocument()
    expect(within(coverage).getByText('Central Pune')).toBeInTheDocument()
    expect(within(coverage).getByText('2,002')).toBeInTheDocument()
    expect(within(coverage).getByText('Karnataka')).toBeInTheDocument()
    expect(within(coverage).getByText('6,501')).toBeInTheDocument()
    expect(within(coverage).getByText(/Telangana/)).toBeInTheDocument()
    expect(within(coverage).getByText(/not yet/i)).toBeInTheDocument()
  })
})
