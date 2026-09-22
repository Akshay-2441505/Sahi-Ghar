import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Search from './Search'

describe('Search', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        projects: [
          { id: 1, state: 'MH', name: 'Shree Heights', rera_reg_no: 'P1', city: 'Pune', promoter_id: 1, promoter_name: 'Shree Realty' },
          { id: 2, state: 'KA', name: 'Casagrand Meridian', rera_reg_no: 'PRM/KA/1', city: 'Bengaluru Urban', promoter_id: 2, promoter_name: 'Casa Grande' },
        ],
      }),
    })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows which state each result is registered in, so builders from different states are never confused', async () => {
    render(<Search />, { wrapper: MemoryRouter })
    await userEvent.type(screen.getByLabelText(/Builder, project name/), 'casa')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(screen.getByText('Shree Heights')).toBeInTheDocument())
    expect(screen.getByText('Maharashtra')).toBeInTheDocument()
    expect(screen.getByText('Karnataka')).toBeInTheDocument()
  })
})
