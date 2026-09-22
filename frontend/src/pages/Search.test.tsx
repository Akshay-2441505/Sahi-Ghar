import { render, screen, waitFor } from '@testing-library/react'
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

  it('states plainly what the site is and where it actually has data, with real counts', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/RERA/)
    const coverage = await screen.findByRole('region', { name: /coverage/i })
    expect(coverage).toHaveTextContent('Maharashtra')
    expect(coverage).toHaveTextContent('Central Pune')
    expect(coverage).toHaveTextContent('2,002')
    expect(coverage).toHaveTextContent('Karnataka')
    expect(coverage).toHaveTextContent('6,501')
    expect(coverage).toHaveTextContent(/More states will be added/)
    expect(coverage).not.toHaveTextContent(/Telangana/)
  })

  it('has no search box until a state is chosen', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    await screen.findByRole('region', { name: /coverage/i })
    expect(screen.queryByLabelText(/Builder, project name/)).not.toBeInTheDocument()
  })

  it('scopes the search to the chosen state, and only that state, once picked', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /Search Karnataka projects/ }))
    const input = await screen.findByLabelText(/Builder, project name/)
    expect(screen.getByText(/Searching/)).toHaveTextContent('Karnataka')

    await userEvent.type(input, 'casa')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(screen.getByText('Casagrand Meridian')).toBeInTheDocument())
    expect(screen.queryByText('Shree Heights')).not.toBeInTheDocument()
  })

  it('lets the visitor change state, which clears the search and its box', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /Search Karnataka projects/ }))
    await screen.findByLabelText(/Builder, project name/)

    await userEvent.click(screen.getByRole('button', { name: 'Change state' }))
    expect(screen.queryByLabelText(/Builder, project name/)).not.toBeInTheDocument()

    await userEvent.click(await screen.findByRole('button', { name: /Search Maharashtra projects/ }))
    const input = await screen.findByLabelText(/Builder, project name/)
    expect(input).toHaveValue('')
  })
})
