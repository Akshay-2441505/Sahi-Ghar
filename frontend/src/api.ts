export type Source = { url: string; origin: string; fetched_at: string }

export type Score = {
  overall: number | null
  schedule: {
    available: boolean
    reason: string | null
    score: number | null
    extended: number
    not_extended: number
    within_registration: number
    unknown: number
    median_months_extended: number | null
  }
  complaints: {
    available: boolean
    reason: string | null
    score: number | null
    total: number
    pending: number
    order_issued: number
    order_not_executed: number
    unresolved: number
    project_count: number
  }
  declared: {
    available: boolean
    reason: string | null
    score: number | null
    total: number
    on_or_before: number
    later: number
    median_months_later: number | null
  }
  progress: { available: boolean; reason: string | null; score: number | null }
}

export type DeclaredItem = {
  name: string
  project_type: string | null
  original_proposed_date: string
  actual_completion_date: string
  source_document_id: number
}

export type ScheduleItem = {
  project_id: number
  name: string
  rera_reg_no: string
  registration_end_date: string | null
  extended_end_date: string | null
  outcome: 'extended' | 'not_extended' | 'within_registration' | 'unknown'
  months_extended: number | null
  source_document_id: number
}

export type ComplaintItem = {
  complaint_ref: string
  status: string
  stage: 'order_issued' | 'pending' | 'other'
  non_execution_applied: boolean
  filed_year: number | null
  filed_month: number | null
  order_url: string | null
  source_document_id: number
}

export type RelatedItem = {
  promoter_id: number
  name: string
  evidence: { shared_count: number; same_address: boolean; name_similarity: number }
  source_document_id: number
}

export type ProjectPayload = {
  project: {
    id: number
    name: string
    rera_reg_no: string
    city: string | null
    locality: string | null
    registration_end_date: string | null
    extended_end_date: string | null
    promoter_name: string
    source_document_id: number
  }
  data_as_of: string | null
  score_computed_at: string | null
  score: Score | null
  group_promoters: { promoter_id: number; name: string; source_document_id: number }[]
  group_basis: string | null
  schedule: ScheduleItem[]
  complaints: ComplaintItem[]
  declared_history: DeclaredItem[]
  possibly_related: RelatedItem[]
  sources: Record<string, Source>
}

export type SearchResult = {
  id: number
  name: string
  rera_reg_no: string
  city: string | null
  promoter_name: string
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  if (!response.ok) throw new Error(response.status === 404 ? 'Not found' : `Request failed (${response.status})`)
  return response.json()
}

export const searchProjects = (q: string) =>
  get<{ projects: SearchResult[] }>(`/search?q=${encodeURIComponent(q)}`).then((r) => r.projects)

export const getProject = (id: string) => get<ProjectPayload>(`/projects/${encodeURIComponent(id)}`)
