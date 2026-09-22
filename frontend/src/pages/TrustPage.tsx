import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { WarningCircle } from '@phosphor-icons/react'
import { getProject, type ProjectPayload } from '../api'
import { ScoreBreakdown } from '../components/ScoreBreakdown'
import { SourceLink } from '../components/SourceLink'
import { formatDate, formatMonthYear, noticeText, outcomeText, stateName } from '../format'

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-(--color-border)">
      <table className="w-full min-w-[42rem] text-left text-sm">
        <thead>
          <tr className="border-b border-(--color-border-strong) text-(--color-ink-muted)">
            {head.map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-(--color-border) [&_td]:px-3 [&_td]:py-2.5">{children}</tbody>
      </table>
    </div>
  )
}

export function TrustPageView({ data }: { data: ProjectPayload }) {
  const { project, sources } = data
  const hasNotices = data.status_notices.length > 0
  return (
    <article className="space-y-10">
      <header className="rise-in border-b border-(--color-border) pb-6">
        <p className="text-sm font-medium text-(--color-accent)">{stateName(project.state)}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{project.name}</h1>
        <p className="mt-2 text-sm text-(--color-ink-muted)">
          RERA registration <span className="ledger-figure text-(--color-ink)">{project.rera_reg_no}</span> · Promoter: {project.promoter_name}
          {project.city ? ` · ${project.city}` : ''}
        </p>
        <p className="mt-3 text-sm text-(--color-ink-faint)">
          Data as of {formatDate(data.data_as_of)}. RERA filings are updated quarterly, not live. This page mirrors public
          records; it is not an independent verdict.
        </p>
      </header>

      {data.score ? <ScoreBreakdown score={data.score} state={project.state} /> : <p>No score has been computed for this promoter yet.</p>}

      <section aria-label="Registration schedule">
        <h2 className="text-lg font-semibold">Registration schedule</h2>
        <p className="mt-1 max-w-3xl text-sm text-(--color-ink-muted)">
          Projects registered by {data.group_promoters.map((p) => p.name).join(', ')}
          {data.group_basis ? ` (grouped as one because the filings show the ${data.group_basis})` : ''}. Dates are the end of each
          registration, taken from the registration and extension certificates. An extension is not necessarily the
          promoter's fault, and a project past its end date may already be complete: these are dates, not a verdict.
        </p>
        <Table head={['Project', 'Registered until', 'Extended to', 'Outcome', 'Source']}>
          {data.schedule.map((h) => (
            <tr key={h.project_id} className="align-top">
              <td>{h.name} <span className="ledger-figure text-xs text-(--color-ink-faint)">{h.rera_reg_no}</span></td>
              <td className="ledger-figure whitespace-nowrap">{formatDate(h.registration_end_date)}</td>
              <td className="ledger-figure whitespace-nowrap">{formatDate(h.extended_end_date)}</td>
              <td>{outcomeText(h)}</td>
              <td><SourceLink id={h.source_document_id} sources={sources} /></td>
            </tr>
          ))}
        </Table>
      </section>

      <section aria-label="Complaints">
        <h2 className="text-lg font-semibold">Complaints</h2>
        {data.complaints.length === 0 ? (
          <p className="mt-1 text-sm text-(--color-ink-muted)">
            {data.score?.complaints.reason === 'not_collected'
              ? 'Complaints have not been collected for this data set, so nothing can be said about them. This is not the same as having none.'
              : 'No complaints on record for this promoter.'}
          </p>
        ) : (
          <Table head={['Reference', 'Status as published', 'Filed', 'Enforcement requested', 'Order', 'Source']}>
            {data.complaints.map((c) => (
              <tr key={c.complaint_ref} className="align-top">
                <td className="ledger-figure">{c.complaint_ref}</td>
                <td>{c.status}</td>
                <td className="ledger-figure whitespace-nowrap">{formatMonthYear(c.filed_year, c.filed_month)}</td>
                <td>{project.state !== 'MH' ? 'Not tracked for this state' : c.non_execution_applied ? 'Yes, order not complied with' : 'No'}</td>
                <td>
                  {c.order_url ? (
                    <a className="text-(--color-accent) hover:underline" href={c.order_url} target="_blank" rel="noopener noreferrer">
                      Original order
                    </a>
                  ) : '—'}
                </td>
                <td><SourceLink id={c.source_document_id} sources={sources} /></td>
              </tr>
            ))}
          </Table>
        )}
      </section>

      <section
        aria-label={project.state === 'MH' ? 'MahaRERA notices' : 'Regulator notices'}
        className={hasNotices ? 'rounded-lg border border-(--color-alert) bg-(--color-alert-soft) p-4' : undefined}
      >
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          {hasNotices && <WarningCircle size={20} weight="fill" className="text-(--color-alert)" />}
          {project.state === 'MH' ? 'MahaRERA notices' : 'Regulator notices'}
        </h2>
        {hasNotices ? (
          <Table head={['Project', 'Notice, as published by MahaRERA', 'Source']}>
            {data.status_notices.map((n) => (
              <tr key={`${n.rera_reg_no}|${n.kind}`} className="align-top">
                <td>{n.project_name} <span className="ledger-figure text-xs text-(--color-ink-faint)">{n.rera_reg_no}</span></td>
                <td>
                  {noticeText(n)}
                  {!n.in_our_project_list && (
                    <span className="mt-1 block text-xs text-(--color-ink-faint)">
                      Not among the projects returned by MahaRERA’s project search; matched to this builder by name only.
                    </span>
                  )}
                </td>
                <td><SourceLink id={n.source_document_id} sources={sources} /></td>
              </tr>
            ))}
          </Table>
        ) : (
          <p className="mt-1 text-sm text-(--color-ink-muted)">
            {project.state !== 'MH'
              ? 'Regulator notice lists (projects kept in abeyance, revoked or otherwise flagged) are not yet read for this state.'
              : data.status_lists_as_of
                ? `None of these projects appears on the two MahaRERA notice lists checked (projects kept in abeyance, and NCLT projects), as of ${formatDate(data.status_lists_as_of)}.`
                : 'MahaRERA’s notice lists (projects kept in abeyance, NCLT projects) have not been collected for this data set, so nothing can be said here. This is not the same as having none.'}
          </p>
        )}
      </section>

      <section aria-label="Declared delivery record">
        <h2 className="text-lg font-semibold">Declared delivery record</h2>
        <p className="mt-1 max-w-3xl text-sm text-(--color-ink-muted)">
          Completed projects the promoter listed in its registration applications, with the completion date it first proposed and
          the date it reports finishing: declared by the promoter, not verified. Extensions, including blanket ones granted for
          reasons outside the promoter’s control, are not separated out.
        </p>
        {data.declared_history.length === 0 ? (
          <p className="mt-2 text-sm text-(--color-ink-muted)">No completed projects were declared in the applications collected so far.</p>
        ) : (
          <Table head={['Project', 'Proposed completion', 'Reported completion', 'Source']}>
            {data.declared_history.map((d) => (
              <tr key={`${d.name}|${d.original_proposed_date}`} className="align-top">
                <td>{d.name}{d.project_type ? <span className="text-xs text-(--color-ink-faint)"> ({d.project_type})</span> : null}</td>
                <td className="ledger-figure whitespace-nowrap">{formatDate(d.original_proposed_date)}</td>
                <td className="ledger-figure whitespace-nowrap">{formatDate(d.actual_completion_date)}</td>
                <td><SourceLink id={d.source_document_id} sources={sources} /></td>
              </tr>
            ))}
          </Table>
        )}
      </section>

      {data.possibly_related.length > 0 && (
        <section aria-label="Possibly related entities" className="rounded-lg border border-dashed border-(--color-border-strong) p-4">
          <h2 className="text-lg font-semibold">Possibly related entities</h2>
          <p className="mt-1 max-w-3xl text-sm text-(--color-ink-muted)">
            Records of possibly related entities (not counted in this score). They are matched on details such as a shared
            registered address, similar name, or overlapping partners or directors; the filings do not confirm a link.
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            {data.possibly_related.map((r) => (
              <li key={r.promoter_id}>
                <span className="font-medium">{r.name}</span>:{' '}
                {[
                  r.evidence.shared_count ? `shares ${r.evidence.shared_count} registered member${r.evidence.shared_count > 1 ? 's' : ''} (partners, directors or signatories)` : null,
                  r.evidence.same_address ? 'same registered address' : null,
                  `name similarity ${r.evidence.name_similarity}%`,
                ].filter(Boolean).join('; ')}{' '}
                <SourceLink id={r.source_document_id} sources={sources} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}

export default function TrustPage() {
  const { id = '' } = useParams()
  const [data, setData] = useState<ProjectPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getProject(id).then(setData).catch((e: Error) => setError(e.message))
  }, [id])

  if (error) return <p>{error}. <Link className="text-(--color-accent) underline" to="/">Back to search</Link></p>
  if (!data) return <p className="text-(--color-ink-muted)">Loading…</p>
  return <TrustPageView data={data} />
}
