import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { MagnifyingGlass, CheckCircle } from '@phosphor-icons/react'
import { getCoverage, searchProjects, type CoverageState, type SearchResult } from '../api'
import { stateName } from '../format'

function CoverageBand() {
  const [states, setStates] = useState<CoverageState[] | null>(null)

  useEffect(() => {
    getCoverage().then(setStates).catch(() => setStates([]))
  }, [])

  return (
    <section aria-label="Coverage" className="-mx-4 bg-(--color-band) px-4 py-16 sm:-mx-[calc((100vw-100%)/2)] sm:px-[calc((100vw-100%)/2)]">
      <div className="mx-auto flex max-w-5xl flex-col gap-10 sm:flex-row sm:items-start">
        <div className="flex-1">
          <h2 className="text-2xl font-bold text-(--color-band-ink)">Where this has data right now</h2>
          <p className="mt-3 max-w-md text-(--color-band-muted)">
            Built one state at a time, straight from each regulator's own public filings. Nothing here is
            guessed to fill a gap on the map.
          </p>
        </div>
        <div className="flex-1">
          {states === null ? (
            <div className="divide-y divide-(--color-band-border) animate-pulse">
              {[0, 1].map((i) => (
                <div key={i} className="flex items-baseline justify-between gap-4 py-4">
                  <div className="space-y-2">
                    <div className="h-4 w-24 rounded bg-(--color-band-border)" />
                    <div className="h-3 w-20 rounded bg-(--color-band-border)" />
                  </div>
                  <div className="h-7 w-14 rounded bg-(--color-band-border)" />
                </div>
              ))}
            </div>
          ) : (
            <div className="divide-y divide-(--color-band-border)">
              {states.map((s) => (
                <div key={s.state} className="flex items-baseline justify-between gap-4 py-4">
                  <div>
                    <p className="font-semibold text-(--color-band-ink)">{s.name}</p>
                    <p className="text-sm text-(--color-band-muted)">{s.area}</p>
                  </div>
                  <p className="ledger-figure text-2xl text-(--color-accent)">{s.projects.toLocaleString('en-IN')}</p>
                </div>
              ))}
            </div>
          )}
          <p className="mt-4 text-sm text-(--color-band-muted)">
            Telangana is not yet covered; its records are not accessible without solving a CAPTCHA, which this project will not do.
          </p>
        </div>
      </div>
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
    <div className="-mt-8 space-y-16 sm:-mt-10">
      <section className="relative -mx-4 overflow-hidden sm:-mx-[calc((100vw-100%)/2)]">
        <img
          src="https://images.unsplash.com/photo-1553064483-f10fe837615f?w=1600&q=75&auto=format&fit=crop"
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          style={{ objectPosition: '50% 55%' }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/35 to-black/75" />
        <div className="relative mx-auto max-w-5xl px-4 pt-24 pb-14 sm:px-[calc((100vw-100%)/2+16px)]">
          <div className="rise-in max-w-xl text-(--color-band-ink)">
            <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Check a builder's real RERA record before you sign anything.
            </h1>
            <p className="mt-3 text-(--color-band-muted)">
              Every figure here comes from an official government filing and links straight to it. No builder pays to be featured.
            </p>
            <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-2 sm:flex-row">
              <label className="sr-only" htmlFor="q">Builder, project name or RERA number</label>
              <input
                id="q"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                minLength={2}
                required
                placeholder="Builder, project name or RERA number"
                className="min-w-0 flex-1 rounded bg-(--color-surface) px-4 py-3 text-(--color-ink) placeholder:text-(--color-ink-faint)"
              />
              <button className="inline-flex items-center justify-center gap-1.5 rounded bg-(--color-accent) px-5 py-3 font-bold text-white hover:bg-(--color-accent-hover)">
                <MagnifyingGlass size={16} weight="bold" />
                Search
              </button>
            </form>
          </div>
        </div>
      </section>

      <section className="max-w-2xl">
        <h2 className="text-2xl font-bold">A score with nowhere to hide</h2>
        <p className="mt-3 text-(--color-ink-muted)">
          Most builder ratings are a single number with no way to check it. This one is a checklist you can read
          the whole way through: registration schedule, complaints, and what the builder itself has declared,
          each shown with the filings behind it.
        </p>
      </section>

      <CoverageBand />

      {error && <p role="alert" className="text-(--color-alert)">{error}</p>}
      {results && results.length === 0 && <p className="text-(--color-ink-muted)">No registered projects match "{q}".</p>}
      {results && results.length > 0 && (
        <ul className="divide-y divide-(--color-border) border-t border-(--color-border)">
          {results.map((r) => (
            <li key={r.id} className="py-4">
              <Link className="font-semibold text-(--color-accent) hover:underline" to={`/projects/${r.id}`}>{r.name}</Link>{' '}
              <span className="rounded bg-(--color-accent-soft) px-1.5 py-0.5 text-xs font-medium text-(--color-accent)">{stateName(r.state)}</span>
              <p className="mt-0.5 flex items-center gap-1.5 text-sm text-(--color-ink-muted)">
                <CheckCircle size={13} weight="bold" className="text-(--color-ink-faint)" />
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
