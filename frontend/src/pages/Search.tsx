import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { MagnifyingGlass, CheckCircle, WarningCircle, X } from '@phosphor-icons/react'
import { getCoverage, searchProjects, type CoverageState, type SearchResult, type TopBuilder } from '../api'

const STATE_THUMBNAILS: Record<string, string> = {
  MH: 'https://images.unsplash.com/photo-1553064483-f10fe837615f?w=200&q=70&auto=format&fit=crop',
  KA: 'https://images.unsplash.com/photo-1697130383976-38f28c444292?w=200&q=70&auto=format&fit=crop',
}

type Selected = { state: string; name: string; area: string; topBuilders: TopBuilder[] }

function RegionChoice({ onPick, selectedState }: { onPick: (s: CoverageState) => void; selectedState: string | null }) {
  const [states, setStates] = useState<CoverageState[] | null>(null)

  useEffect(() => {
    getCoverage().then(setStates).catch(() => setStates([]))
  }, [])

  return (
    <section aria-label="Coverage">
      <p className="text-sm text-(--color-ink-muted)">Choose a state to search the projects registered there.</p>
      <div className="mt-4 grid gap-6 sm:grid-cols-2">
        {states === null
          ? [0, 1].map((i) => (
              <div key={i} className="animate-pulse rounded-lg border border-(--color-border) bg-(--color-surface) p-8">
                <div className="flex items-center gap-4">
                  <div className="h-20 w-20 shrink-0 rounded-lg bg-(--color-border)" />
                  <div className="space-y-2">
                    <div className="h-6 w-28 rounded bg-(--color-border)" />
                    <div className="h-3 w-16 rounded bg-(--color-border)" />
                  </div>
                </div>
                <div className="mt-6 h-8 w-24 rounded bg-(--color-border)" />
              </div>
            ))
          : states.map((s) => {
              const active = selectedState === s.state
              return (
                <button
                  key={s.state}
                  type="button"
                  onClick={() => onPick(s)}
                  aria-pressed={active}
                  className={
                    'rise-in group rounded-lg border-2 p-8 text-left transition-[transform,box-shadow,border-color,background-color] duration-200 hover:-translate-y-[3px] hover:shadow-lg hover:shadow-black/5 ' +
                    (active
                      ? 'border-(--color-accent) bg-(--color-accent-soft)'
                      : 'border-(--color-border) bg-(--color-surface) hover:border-(--color-border-strong)')
                  }
                >
                  <div className="flex items-center gap-4">
                    {STATE_THUMBNAILS[s.state] && (
                      <img src={STATE_THUMBNAILS[s.state]} alt="" className="h-20 w-20 shrink-0 rounded-lg object-cover" style={{ objectPosition: '50% 40%' }} />
                    )}
                    <div>
                      <p className="text-xl font-bold text-(--color-ink)">{s.name}</p>
                      <p className="text-sm text-(--color-ink-faint)">{s.area}</p>
                    </div>
                  </div>
                  <p className="mt-6 flex items-baseline gap-1.5">
                    <span className="ledger-figure text-3xl font-medium text-(--color-accent)">{s.projects.toLocaleString('en-IN')}</span>
                    <span className="text-sm text-(--color-ink-muted)">registered projects</span>
                  </p>
                  <span className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-(--color-accent) group-hover:underline">
                    {active ? 'Currently searching' : `Search ${s.name} projects`}
                    <MagnifyingGlass size={13} weight="bold" />
                  </span>
                </button>
              )
            })}
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
  const [selected, setSelected] = useState<Selected | null>(null)
  const regionRef = useRef<HTMLDivElement>(null)
  const searchPanelRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(null), 6000)
    return () => clearTimeout(timer)
  }, [error])

  useEffect(() => {
    if (!selected) return
    searchPanelRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    inputRef.current?.focus()
  }, [selected])

  function pickState(s: CoverageState) {
    setQ('')
    setResults(null)
    setError(null)
    setSelected({ state: s.state, name: s.name, area: s.area, topBuilders: s.top_builders })
  }

  function changeState() {
    setSelected(null)
    setQ('')
    setResults(null)
    regionRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  async function runSearch(query: string) {
    setError(null)
    try {
      setResults(await searchProjects(query))
    } catch (e) {
      setResults(null)
      setError((e as Error).message)
    }
  }

  function trySample(name: string) {
    setQ(name)
    runSearch(name)
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    runSearch(q.trim())
  }

  const visibleResults = selected && results ? results.filter((r) => r.state === selected.state) : null

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
        <div className="relative mx-auto max-w-5xl px-4 pt-24 pb-16 sm:px-[calc((100vw-100%)/2+16px)]">
          <div className="rise-in max-w-xl text-(--color-band-ink)">
            <h1 className="hero-text-shadow text-3xl font-extrabold tracking-tight sm:text-4xl">
              Check a builder's real RERA record before you sign anything.
            </h1>
            <p className="hero-text-shadow mt-3 text-(--color-band-muted)">
              Every figure here comes from an official government filing and links straight to it. No builder pays to be featured.
            </p>
          </div>
        </div>
      </section>

      <section className="max-w-3xl">
        <h2 className="text-2xl font-bold">A score with nowhere to hide</h2>
        <p className="mt-3 text-(--color-ink-muted)">
          Most builder ratings are a single number with no way to check it. This one is a checklist you can read
          the whole way through: registration schedule, complaints, and what the builder itself has declared,
          each shown with the filings behind it.
        </p>
      </section>

      <div ref={regionRef} className="scroll-mt-6">
        <RegionChoice onPick={pickState} selectedState={selected?.state ?? null} />
      </div>

      {selected && (
        <div ref={searchPanelRef} className="scroll-mt-6">
          <div className="flex items-center justify-between gap-4 border-b border-(--color-border) pb-3">
            <p className="text-sm text-(--color-ink-muted)">
              Searching <span className="font-semibold text-(--color-ink)">{selected.name}</span> · {selected.area}
            </p>
            <button type="button" onClick={changeState} className="shrink-0 text-sm font-medium text-(--color-accent) hover:underline">
              Change state
            </button>
          </div>

          <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-2 sm:flex-row">
            <label className="sr-only" htmlFor="q">Builder, project name or RERA number</label>
            <input
              id="q"
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              minLength={2}
              required
              placeholder={`Builder, project name or RERA number in ${selected.name}`}
              className="min-w-0 flex-1 rounded border border-(--color-border) bg-(--color-surface) px-4 py-3 text-(--color-ink) placeholder:text-(--color-ink-faint)"
            />
            <button className="inline-flex items-center justify-center gap-1.5 rounded bg-(--color-accent) px-5 py-3 font-bold text-white hover:bg-(--color-accent-hover)">
              <MagnifyingGlass size={16} weight="bold" />
              Search
            </button>
          </form>

          {selected.topBuilders.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-sm text-(--color-ink-faint)">Nothing to search yet? Try:</span>
              {selected.topBuilders.map((b) => (
                <button
                  key={b.promoter_id}
                  type="button"
                  onClick={() => trySample(b.name)}
                  className="rounded-full border border-(--color-border) bg-(--color-surface) px-3 py-1 text-sm text-(--color-ink-muted) hover:border-(--color-accent) hover:text-(--color-accent)"
                >
                  {b.name}
                </button>
              ))}
            </div>
          )}

          <div className="mt-6">
            {visibleResults && visibleResults.length === 0 && (
              <p className="text-(--color-ink-muted)">No {selected.name} projects match "{q}".</p>
            )}
            {visibleResults && visibleResults.length > 0 && (
              <ul className="divide-y divide-(--color-border) border-t border-(--color-border)">
                {visibleResults.map((r) => (
                  <li key={r.id} className="py-4">
                    <Link className="font-semibold text-(--color-accent) hover:underline" to={`/projects/${r.id}`}>{r.name}</Link>
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
        </div>
      )}

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
