import type { Source } from '../api'
import { formatDate } from '../format'

/** Every figure on the trust page renders one of these next to it. */
export function SourceLink({ id, sources }: { id: number; sources: Record<string, Source> }) {
  const source = sources[String(id)]
  if (!source) return null
  const label = `Source, fetched ${formatDate(source.fetched_at)}`
  if (!source.url.startsWith('http')) {
    return <span className="text-xs text-stone-500">{label} ({source.origin})</span>
  }
  return (
    <a className="text-xs text-blue-800 underline" href={source.url} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  )
}
