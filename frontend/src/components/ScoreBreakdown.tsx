import type { Score } from '../api'

function Section({ title, score, children }: { title: string; score: number | null; children: React.ReactNode }) {
  const hasScore = score !== null
  return (
    <div
      className={
        hasScore
          ? 'rise-in rounded-lg border border-(--color-border) bg-(--color-surface) p-4 transition-[transform,box-shadow] duration-200 hover:-translate-y-[3px] hover:shadow-lg hover:shadow-black/5'
          : 'rise-in rounded-lg border border-dashed border-(--color-border) p-4'
      }
    >
      <h3 className="text-sm font-medium text-(--color-ink-muted)">{title}</h3>
      <p className="ledger-figure mt-1 text-3xl font-medium">
        {hasScore ? <>{score}<span className="text-lg text-(--color-ink-faint)">/100</span></> : <span className="text-(--color-ink-faint)">—</span>}
      </p>
      <p className="mt-2 text-sm text-(--color-ink-muted)">{children}</p>
    </div>
  )
}

/** The overall number is only ever rendered below, and as a summary of, the three sections. */
export function ScoreBreakdown({ score, state }: { score: Score; state: string }) {
  const { schedule, complaints, declared, progress } = score
  const evaluated = schedule.extended + schedule.covid_only + schedule.not_extended
  return (
    <section aria-label="Score breakdown">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Section title="Registration schedule" score={schedule.score}>
          {schedule.available
            ? `${schedule.extended} of ${evaluated} projects had their registration extended` +
              (schedule.median_months_extended !== null ? ` (median ${Math.round(schedule.median_months_extended * 10) / 10} months)` : '') +
              (schedule.covid_only ? `; ${schedule.covid_only} only under COVID-19 relief (not counted against the builder)` : '') +
              `; ${schedule.not_extended} passed the original end date with no extension on record.`
            : 'Not enough history to summarise (at least 2 projects past their original end date or extended are needed).'}
        </Section>
        <Section title="Complaints" score={complaints.score}>
          {complaints.available
            ? `${complaints.total} on record: ${complaints.pending} hearing pending, ${complaints.order_issued} order issued; ` +
              (state === 'MH'
                ? `${complaints.order_not_executed} with a request to enforce an order that was not complied with. `
                : 'enforcement-of-order requests are not tracked for this state. ') +
              `${complaints.unresolved} unresolved across ${complaints.project_count} registered projects.`
            : complaints.reason === 'not_collected'
              ? 'Not collected for this data set yet. A missing complaint list here does not mean the builder has none.'
              : 'No registered projects on record.'}
        </Section>
        <Section title="Declared delivery" score={declared.score}>
          {declared.available
            ? `${declared.on_or_before} of ${declared.total} completed projects were declared finished on or before the proposed date; ${declared.later} later` +
              (declared.median_months_later !== null ? ` (median ${Math.round(declared.median_months_later * 10) / 10} months). ` : '. ') +
              'The promoter’s own account, not verified.'
            : 'Not enough declared history (at least 2 completed projects listed in the registration applications are needed).'}
        </Section>
        <Section title="Progress vs promise" score={progress.score}>
          Not yet available. Quarterly progress reports are not included in this version.
        </Section>
      </div>
      <p className="mt-4 rounded-lg border border-(--color-border) bg-(--color-surface) px-4 py-3 text-sm text-(--color-ink-muted)">
        {score.overall === null ? (
          score.notices.count > 0 ? (
            <>Overall: not shown, because the regulator lists {score.notices.count} notice{score.notices.count > 1 ? 's' : ''} about this builder's projects (below). An average cannot speak for those.</>
          ) : (
            'Overall: not shown until at least two sections above have data.'
          )
        ) : (
          <>Overall: <span className="ledger-figure text-base font-medium text-(--color-accent)">{score.overall}/100</span>, the average of the sections above that have data.</>
        )}
      </p>
    </section>
  )
}
