import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProject, type ProjectPayload } from '../api'
import { ScoreBreakdown } from '../components/ScoreBreakdown'
import { SourceLink } from '../components/SourceLink'
import { formatDate, formatMonthYear, noticeText, outcomeText } from '../format'

export function TrustPageView({ data }: { data: ProjectPayload }) {
  const { project, sources } = data
  return (
    <article className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-stone-900">{project.name}</h1>
        <p className="mt-1 text-sm text-stone-700">
          RERA registration <span className="font-mono">{project.rera_reg_no}</span> · Promoter: {project.promoter_name}
          {project.city ? ` · ${project.city}` : ''}
        </p>
        <p className="mt-2 text-sm text-stone-600">
          Data as of {formatDate(data.data_as_of)}. RERA filings are updated quarterly, not live. This page mirrors public
          records; it is not an independent verdict.
        </p>
      </header>

      {data.score ? <ScoreBreakdown score={data.score} state={project.state} /> : <p>No score has been computed for this promoter yet.</p>}

      <section aria-label="Registration schedule">
        <h2 className="text-lg font-semibold text-stone-900">Registration schedule</h2>
        <p className="text-sm text-stone-600">
          Projects registered by {data.group_promoters.map((p) => p.name).join(', ')}
          {data.group_basis ? ` (grouped as one because the filings show the ${data.group_basis})` : ''}. Dates are the end of each
          registration, taken from the registration and extension certificates. An extension is not necessarily the
          promoter's fault, and a project past its end date may already be complete: these are dates, not a verdict.
        </p>
        <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="text-stone-600">
            <tr><th>Project</th><th>Registered until</th><th>Extended to</th><th>Outcome</th><th>Source</th></tr>
          </thead>
          <tbody>
            {data.schedule.map((h) => (
              <tr key={h.project_id} className="border-t border-stone-200 align-top">
                <td>{h.name} <span className="font-mono text-xs text-stone-500">{h.rera_reg_no}</span></td>
                <td>{formatDate(h.registration_end_date)}</td>
                <td>{formatDate(h.extended_end_date)}</td>
                <td>{outcomeText(h)}</td>
                <td><SourceLink id={h.source_document_id} sources={sources} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section>

      <section aria-label="Complaints">
        <h2 className="text-lg font-semibold text-stone-900">Complaints</h2>
        {data.complaints.length === 0 ? (
          <p className="text-sm text-stone-600">
            {data.score?.complaints.reason === 'not_collected'
              ? 'Complaints have not been collected for this data set, so nothing can be said about them. This is not the same as having none.'
              : 'No complaints on record for this promoter.'}
          </p>
        ) : (
          <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="text-stone-600">
              <tr><th>Reference</th><th>Status as published</th><th>Filed</th><th>Enforcement requested</th><th>Order</th><th>Source</th></tr>
            </thead>
            <tbody>
              {data.complaints.map((c) => (
                <tr key={c.complaint_ref} className="border-t border-stone-200 align-top">
                  <td className="font-mono">{c.complaint_ref}</td>
                  <td>{c.status}</td>
                  <td>{formatMonthYear(c.filed_year, c.filed_month)}</td>
                  <td>{project.state !== 'MH' ? 'Not tracked for this state' : c.non_execution_applied ? 'Yes, order not complied with' : 'No'}</td>
                  <td>
                    {c.order_url ? (
                      <a className="text-blue-800 underline" href={c.order_url} target="_blank" rel="noopener noreferrer">
                        Original order
                      </a>
                    ) : '—'}
                  </td>
                  <td><SourceLink id={c.source_document_id} sources={sources} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      <section aria-label={project.state === 'MH' ? 'MahaRERA notices' : 'Regulator notices'}>
        <h2 className="text-lg font-semibold text-stone-900">{project.state === 'MH' ? 'MahaRERA notices' : 'Regulator notices'}</h2>
        {data.status_notices.length > 0 ? (
          <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="text-stone-600"><tr><th>Project</th><th>Notice, as published by MahaRERA</th><th>Source</th></tr></thead>
            <tbody>
              {data.status_notices.map((n) => (
                <tr key={`${n.rera_reg_no}|${n.kind}`} className="border-t border-stone-200 align-top">
                  <td>{n.project_name} <span className="font-mono text-xs text-stone-500">{n.rera_reg_no}</span></td>
                  <td>
                    {noticeText(n)}
                    {!n.in_our_project_list && (
                      <span className="mt-1 block text-xs text-stone-500">
                        Not among the projects returned by MahaRERA’s project search; matched to this builder by name only.
                      </span>
                    )}
                  </td>
                  <td><SourceLink id={n.source_document_id} sources={sources} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        ) : (
          <p className="text-sm text-stone-600">
            {project.state !== 'MH'
              ? 'Regulator notice lists (projects kept in abeyance, revoked or otherwise flagged) are not yet read for this state.'
              : data.status_lists_as_of
                ? `None of these projects appears on the two MahaRERA notice lists checked (projects kept in abeyance, and NCLT projects), as of ${formatDate(data.status_lists_as_of)}.`
                : 'MahaRERA’s notice lists (projects kept in abeyance, NCLT projects) have not been collected for this data set, so nothing can be said here. This is not the same as having none.'}
          </p>
        )}
      </section>

      <section aria-label="Declared delivery record">
        <h2 className="text-lg font-semibold text-stone-900">Declared delivery record</h2>
        <p className="text-sm text-stone-600">
          Completed projects the promoter listed in its registration applications, with the completion date it first proposed and
          the date it reports finishing: declared by the promoter, not verified. Extensions, including blanket ones granted for
          reasons outside the promoter’s control, are not separated out.
        </p>
        {data.declared_history.length === 0 ? (
          <p className="mt-2 text-sm text-stone-600">No completed projects were declared in the applications collected so far.</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="text-stone-600">
              <tr><th>Project</th><th>Proposed completion</th><th>Reported completion</th><th>Source</th></tr>
            </thead>
            <tbody>
              {data.declared_history.map((d) => (
                <tr key={`${d.name}|${d.original_proposed_date}`} className="border-t border-stone-200 align-top">
                  <td>{d.name}{d.project_type ? <span className="text-xs text-stone-500"> ({d.project_type})</span> : null}</td>
                  <td>{formatDate(d.original_proposed_date)}</td>
                  <td>{formatDate(d.actual_completion_date)}</td>
                  <td><SourceLink id={d.source_document_id} sources={sources} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      {data.possibly_related.length > 0 && (
        <section aria-label="Possibly related entities" className="rounded border border-dashed border-stone-400 p-4">
          <h2 className="text-lg font-semibold text-stone-900">Possibly related entities</h2>
          <p className="text-sm text-stone-600">
            Records of possibly related entities (not counted in this score). They are matched on details such as a shared
            registered address, similar name, or overlapping partners or directors; the filings do not confirm a link.
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {data.possibly_related.map((r) => (
              <li key={r.promoter_id}>
                {r.name}:{' '}
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

  if (error) return <p>{error}. <Link className="underline" to="/">Back to search</Link></p>
  if (!data) return <p>Loading…</p>
  return <TrustPageView data={data} />
}
