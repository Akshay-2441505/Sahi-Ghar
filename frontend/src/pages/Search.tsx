import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { searchProjects, type SearchResult } from '../api'
import { stateName } from '../format'

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
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="flex gap-2">
        <label className="sr-only" htmlFor="q">Builder, project name or RERA number</label>
        <input
          id="q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          minLength={2}
          required
          placeholder="Builder, project name or RERA number"
          className="flex-1 rounded border border-stone-400 px-3 py-2"
        />
        <button className="rounded bg-stone-900 px-4 py-2 text-white">Search</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {results && results.length === 0 && <p>No registered projects match “{q}”.</p>}
      {results && results.length > 0 && (
        <ul className="divide-y divide-stone-200">
          {results.map((r) => (
            <li key={r.id} className="py-3">
              <Link className="font-medium text-blue-800 underline" to={`/projects/${r.id}`}>{r.name}</Link>{' '}
              <span className="rounded bg-stone-200 px-1.5 py-0.5 text-xs font-medium text-stone-700">{stateName(r.state)}</span>
              <p className="text-sm text-stone-600">
                <span className="font-mono">{r.rera_reg_no}</span> · {r.promoter_name}
                {r.city ? ` · ${r.city}` : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
