import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { MagnifyingGlass, SealCheck } from '@phosphor-icons/react'
import { getCoverage, searchProjects, type CoverageState, type SearchResult } from '../api'
import { stateName } from '../format'

function CoveragePanel() {
  const [states, setStates] = useState<CoverageState[] | null>(null)

  useEffect(() => {
    getCoverage().then(setStates).catch(() => setStates([]))
  }, [])

  return (
    <section aria-label="Coverage" className="border border-(--color-border) bg-(--color-surface)">
      <h2 className="border-b border-(--color-border) px-5 py-3 text-sm font-semibold">Where this has data right now</h2>
      {states === null ? (
        <p className="px-5 py-6 text-sm text-(--color-ink-muted)">Loading coverage.</p>
      ) : (
        <div className="divide-y divide-(--color-border)">
          {states.map((s) => (
            <div key={s.state} className="flex items-center justify-between gap-4 px-5 py-4">
              <div>
                <p className="font-medium">{s.name}</p>
                <p className="text-sm text-(--color-ink-muted)">{s.area}</p>
              </div>
              <p className="ledger-figure text-2xl font-medium text-(--color-accent)">{s.projects.toLocaleString('en-IN')}</p>
            </div>
          ))}
        </div>
      )}
      <p className="border-t border-(--color-border) px-5 py-3 text-sm text-(--color-ink-muted)">
        Telangana is not yet covered; its records are not accessible without solving a CAPTCHA, which this project will not do.
      </p>
    </section>
  )
}

export default function Search() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      setResults(await searchProjects(q.trim()))
    } catch (e) {
      setResults(null)
      setError((e as Error).message)
    }
  }

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <h1 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
          Check a builder's real RERA record before you sign anything.
        </h1>
        <p className="max-w-xl text-(--color-ink-muted)">
          Every figure here comes from an official government filing and links straight to it. No builder pays to be featured.
        </p>
        <form onSubmit={onSubmit} className="flex max-w-xl flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="q">Builder, project name or RERA number</label>
          <input
            id="q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            minLength={2}
            required
            placeholder="Builder, project name or RERA number"
            className="min-w-0 flex-1 border border-(--color-border-strong) bg-(--color-surface) px-3 py-2.5 text-(--color-ink) placeholder:text-(--color-ink-faint) focus:border-(--color-accent)"
          />
          <button className="inline-flex items-center justify-center gap-1.5 rounded bg-(--color-accent) px-4 py-2.5 font-medium text-white hover:bg-(--color-accent-hover)">
            <MagnifyingGlass size={16} weight="bold" />
            Search
          </button>
        </form>
      </section>

      <CoveragePanel />

      {error && <p role="alert" className="text-(--color-alert)">{error}</p>}
      {results && results.length === 0 && <p className="text-(--color-ink-muted)">No registered projects match "{q}".</p>}
      {results && results.length > 0 && (
        <ul className="divide-y divide-(--color-border) border-t border-(--color-border)">
          {results.map((r) => (
            <li key={r.id} className="py-4">
              <Link className="font-medium text-(--color-accent) hover:underline" to={`/projects/${r.id}`}>{r.name}</Link>{' '}
              <span className="rounded bg-(--color-accent-soft) px-1.5 py-0.5 text-xs font-medium text-(--color-accent)">{stateName(r.state)}</span>
              <p className="mt-0.5 flex items-center gap-1.5 text-sm text-(--color-ink-muted)">
                <SealCheck size={13} weight="bold" className="text-(--color-ink-faint)" />
                <span className="ledger-figure">{r.rera_reg_no}</span> · {r.promoter_name}
                {r.city ? ` · ${r.city}` : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
