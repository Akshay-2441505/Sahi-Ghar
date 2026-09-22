import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { MagnifyingGlass, CheckCircle, WarningCircle, X } from '@phosphor-icons/react'
import { getCoverage, searchProjects, type CoverageState, type SearchResult } from '../api'
import { stateName } from '../format'

const STATE_THUMBNAILS: Record<string, string> = {
  MH: 'https://images.unsplash.com/photo-1553064483-f10fe837615f?w=200&q=70&auto=format&fit=crop',
  KA: 'https://images.unsplash.com/photo-1697130383976-38f28c444292?w=200&q=70&auto=format&fit=crop',
}

function RegionChoice({ onPick }: { onPick: (state: string) => void }) {
  const [states, setStates] = useState<CoverageState[] | null>(null)

  useEffect(() => {
    getCoverage().then(setStates).catch(() => setStates([]))
  }, [])

  return (
    <section aria-label="Coverage" className="max-w-2xl">
      <p className="text-sm text-(--color-ink-muted)">Pick a state to see projects registered there.</p>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {states === null
          ? [0, 1].map((i) => (
              <div key={i} className="animate-pulse rounded-lg border border-(--color-border) bg-(--color-surface) p-6">
                <div className="flex items-center gap-3.5">
                  <div className="h-16 w-16 shrink-0 rounded-lg bg-(--color-border)" />
                  <div className="space-y-2">
                    <div className="h-5 w-24 rounded bg-(--color-border)" />
                    <div className="h-3 w-16 rounded bg-(--color-border)" />
                  </div>
                </div>
                <div className="mt-5 h-7 w-20 rounded bg-(--color-border)" />
              </div>
            ))
          : states.map((s) => (
              <button
                key={s.state}
                type="button"
                onClick={() => onPick(s.state)}
                className="rise-in group rounded-lg border border-(--color-border) bg-(--color-surface) p-6 text-left transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-[3px] hover:border-(--color-border-strong) hover:shadow-lg hover:shadow-black/5"
              >
                <div className="flex items-center gap-3.5">
                  {STATE_THUMBNAILS[s.state] && (
                    <img src={STATE_THUMBNAILS[s.state]} alt="" className="h-16 w-16 shrink-0 rounded-lg object-cover" style={{ objectPosition: '50% 40%' }} />
                  )}
                  <div>
                    <p className="text-lg font-bold text-(--color-ink)">{s.name}</p>
                    <p className="text-sm text-(--color-ink-faint)">{s.area}</p>
                  </div>
                </div>
                <p className="mt-5 flex items-baseline gap-1.5">
                  <span className="ledger-figure text-2xl font-medium text-(--color-accent)">{s.projects.toLocaleString('en-IN')}</span>
                  <span className="text-sm text-(--color-ink-muted)">registered projects</span>
                </p>
                <span className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-(--color-accent) group-hover:underline">
                  Search {s.name} projects
                  <MagnifyingGlass size={13} weight="bold" />
                </span>
              </button>
            ))}
      </div>
      <p className="mt-4 text-sm text-(--color-ink-faint)">
        More states will be added over time, as each one's filings become reachable without solving a CAPTCHA.
      </p>
    </section>
  )
}

export default function Search() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedState, setSelectedState] = useState<string | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(null), 6000)
    return () => clearTimeout(timer)
  }, [error])

  function pickState(state: string) {
    setSelectedState(state)
    inputRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    inputRef.current?.focus()
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      setResults(await searchProjects(q.trim()))
      resultsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    } catch (e) {
      setResults(null)
      setError((e as Error).message)
    }
  }

  const visibleResults = results && selectedState ? results.filter((r) => r.state === selectedState) : results

  return (
    <div className="-mt-8 space-y-16 sm:-mt-10">
      <section className="relative -mx-4 overflow-hidden sm:-mx-[calc((100vw-100%)/2)]">
        <img
          src="https://images.unsplash.com/photo-1553064483-f10fe837615f?w=1600&q=75&auto=format&fit=crop"
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          style={{ objectPosition: '50% 55%' }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-black/50 to-black/85" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/20 to-transparent" />
        <div className="relative mx-auto max-w-5xl px-4 pt-24 pb-14 sm:px-[calc((100vw-100%)/2+16px)]">
          <div className="rise-in max-w-xl text-(--color-band-ink)">
            <h1 className="hero-text-shadow text-3xl font-extrabold tracking-tight sm:text-4xl">
              Check a builder's real RERA record before you sign anything.
            </h1>
            <p className="hero-text-shadow mt-3 text-(--color-band-muted)">
              Every figure here comes from an official government filing and links straight to it. No builder pays to be featured.
            </p>
            <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-2 sm:flex-row">
              <label className="sr-only" htmlFor="q">Builder, project name or RERA number</label>
              <input
                id="q"
                ref={inputRef}
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
            {selectedState && (
              <button
                type="button"
                onClick={() => setSelectedState(null)}
                className="mt-3 inline-flex items-center gap-1.5 rounded bg-white/10 px-2.5 py-1 text-xs font-medium text-(--color-band-ink) hover:bg-white/20"
              >
                Showing {stateName(selectedState)} only
                <X size={12} weight="bold" />
              </button>
            )}
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

      <RegionChoice onPick={pickState} />

      <div ref={resultsRef}>
        {visibleResults && visibleResults.length === 0 && <p className="text-(--color-ink-muted)">No registered projects match "{q}"{selectedState ? ` in ${stateName(selectedState)}` : ''}.</p>}
        {visibleResults && visibleResults.length > 0 && (
          <ul className="divide-y divide-(--color-border) border-t border-(--color-border)">
            {visibleResults.map((r) => (
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

      {error && (
        <div
          role="alert"
          className="rise-in fixed inset-x-4 bottom-6 z-20 mx-auto flex max-w-md items-start gap-2 rounded-lg border border-(--color-alert) bg-(--color-alert-soft) p-4 text-sm text-(--color-alert) shadow-lg sm:inset-x-auto sm:right-6"
        >
          <WarningCircle size={18} weight="fill" className="mt-0.5 shrink-0" />
          <p className="flex-1">{error}</p>
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss" className="shrink-0 text-(--color-alert) opacity-70 hover:opacity-100">
            <X size={16} weight="bold" />
          </button>
        </div>
      )}
    </div>
  )
}
