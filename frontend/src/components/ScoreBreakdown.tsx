import type { Score } from '../api'

function Section({ title, score, children }: { title: string; score: number | null; children: React.ReactNode }) {
  return (
    <div className="rounded border border-stone-300 bg-white p-4">
      <h3 className="text-sm font-semibold text-stone-700">{title}</h3>
      <p className="mt-1 text-2xl font-semibold text-stone-900">{score === null ? '—' : `${score}/100`}</p>
      <p className="mt-1 text-sm text-stone-600">{children}</p>
    </div>
  )
}

/** The overall number is only ever rendered below, and as a summary of, the three sections. */
export function ScoreBreakdown({ score }: { score: Score }) {
  const { schedule, complaints, declared, progress } = score
  const evaluated = schedule.extended + schedule.covid_only + schedule.not_extended
  return (
    <section aria-label="Score breakdown">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
              `${complaints.order_not_executed} with a request to enforce an order that was not complied with. ` +
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
      <p className="mt-3 text-sm text-stone-700">
        {score.overall === null
          ? score.notices.count > 0
            ? `Overall: not shown, because the regulator lists ${score.notices.count} notice${score.notices.count > 1 ? 's' : ''} about this builder's projects (below). An average cannot speak for those.`
            : 'Overall: not shown until at least two sections above have data.'
          : `Overall: ${score.overall}/100, the average of the sections above that have data.`}
      </p>
    </section>
  )
}
