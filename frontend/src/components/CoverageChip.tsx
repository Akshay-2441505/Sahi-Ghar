import { useEffect, useState } from 'react'
import { SealCheck } from '@phosphor-icons/react'
import { getCoverage, type CoverageState } from '../api'

/** A persistent, honest statement of where this actually has data -- shown in the header on every page, not
    just on first load, so "which states" is never a claim buyers have to go looking for. */
export function CoverageChip() {
  const [states, setStates] = useState<CoverageState[] | null>(null)

  useEffect(() => {
    getCoverage().then(setStates).catch(() => setStates([]))
  }, [])

  if (!states || states.length === 0) return null

  return (
    <p className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-(--color-ink-muted)">
      <SealCheck size={14} weight="bold" className="text-(--color-accent)" />
      Live in {states.map((s, i) => (
        <span key={s.state}>
          {s.name} <span className="text-(--color-ink-faint)">({s.area})</span>
          {i < states.length - 1 ? ',' : ''}
        </span>
      ))}
    </p>
  )
}
