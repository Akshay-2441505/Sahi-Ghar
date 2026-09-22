import { SealCheck } from '@phosphor-icons/react'
import type { Source } from '../api'
import { formatDate } from '../format'

/** Every figure on the trust page renders one of these next to it: the seal is the product's core claim made visible. */
export function SourceLink({ id, sources }: { id: number; sources: Record<string, Source> }) {
  const source = sources[String(id)]
  if (!source) return null
  const label = `Source, fetched ${formatDate(source.fetched_at)}`
  if (!source.url.startsWith('http')) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-(--color-ink-faint)">
        <SealCheck size={13} weight="bold" />
        {label} ({source.origin})
      </span>
    )
  }
  return (
    <a
      className="inline-flex items-center gap-1 text-xs text-(--color-accent) hover:text-(--color-accent-hover) hover:underline"
      href={source.url} target="_blank" rel="noopener noreferrer"
    >
      <SealCheck size={13} weight="bold" />
      {label}
    </a>
  )
}
