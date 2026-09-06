// ─── Backend schema types (match app/schemas.py) ───────────────────

export type BackendConfidence = 'VERIFIED' | 'INFERRED' | 'CONTESTED' | 'UNGROUNDED'

export interface BackendField {
  field_name: string
  value: string | null
  value_alt: string | null
  verbatim_quote: string | null
  quote_match_score: number | null
  page: number | null        // 0-indexed
  bbox: string | null         // "x0,y0,x1,y1"
  confidence: BackendConfidence
  extractor_a_raw: string | null
  extractor_b_raw: string | null
  adversary_note: string | null
}

export interface BackendContract {
  id: number
  filename: string
  parties: string | null
  contract_type: string | null
  start_date: string | null
  end_date: string | null
  renewal_type: string | null   // auto | manual | none
  notice_period_days: number | null
  notice_deadline: string | null
  governing_law: string | null
  is_scanned: boolean
  clauses_total: number
  clauses_covered: number
  fields: BackendField[]
}

export interface BackendConflict {
  id: number
  contract_a_id: number
  contract_b_id: number
  contract_a_filename: string
  contract_b_filename: string
  kind: string
  description: string
  severity: string    // "high" | "medium"
  field_a: string | null
  field_b: string | null
}

export interface BackendCalendarEvent {
  contract_id: number
  contract_filename: string
  event_type: string    // "renewal" | "expiry" | "notice_deadline" | "payment"
  date: string          // ISO date string
  days_away: number
  priority: string      // "urgent" | "upcoming" | "clear"
}

export interface BackendHandoff {
  title: string
  issue_summary: string
  relevant_documents: string[]
  relevant_clauses: { filename: string; field_name: string; quote: string; page: number }[]
  what_the_tool_established: string
  specific_question_for_lawyer: string
  contested_or_ungrounded_fields: BackendField[]
}

export interface BackendPortfolioStats {
  total_contracts: number
  actions_required: number
  renewals_90_days: number
  potential_conflicts: number
  legal_review_needed: number
}

// ─── UI display types (used by components) ─────────────────────────

export type UIConfidence = 'high' | 'medium' | 'low'
export type ContractStatus = 'high-confidence' | 'needs-review' | 'action-required'

export interface ExtractedField {
  id: string
  category: string
  label: string
  finding: string
  secondary?: string
  confidence: UIConfidence
  notFound?: boolean
  legalReview?: boolean
  page: number | null       // 1-indexed for display
  clause: string | null
  actionDeadline?: string
  clauseText?: string
  bbox?: string
}

export interface ContractEvent {
  id: string
  contractId: number
  contract: string
  type: 'Renewal' | 'Expiry' | 'Notice deadline' | 'Payment obligation'
  date: string
  daysAway: number
  priority: 'urgent' | 'upcoming' | 'clear'
}

export interface Contract {
  id: number
  slug: string
  name: string
  fileType: 'pdf' | 'docx' | 'pptx'
  parties: string
  status: ContractStatus
  confidence: UIConfidence
  fieldsExtracted: number
  fieldsTotal: number
  fieldsNeedReview: number
  clausesTotal: number
  clausesCovered: number
  isScanned: boolean
  alert?: { level: 'urgent' | 'review'; label: string }
  lastAnalysed: string
  fields: ExtractedField[]
  renewalType?: string
  noticeDeadline?: string
  startDate?: string
  endDate?: string
}

export interface Conflict {
  id: string
  title: string
  summary: string
  contractA: { id: number; name: string }
  contractB: { id: number; name: string }
  severity: 'high' | 'medium'
}

export interface PortfolioStat {
  id: string
  label: string
  value: number
  tone: 'danger' | 'warning' | 'primary' | 'muted'
  icon: string
  hint: string
}

// ─── Confidence metadata for badges ────────────────────────────────

export const confidenceMeta: Record<
  UIConfidence,
  { label: string; dot: string; text: string; bg: string; border: string }
> = {
  high: {
    label: 'High confidence',
    dot: 'bg-success',
    text: 'text-success',
    bg: 'bg-success-muted',
    border: 'border-success/30',
  },
  medium: {
    label: 'Medium confidence',
    dot: 'bg-warning',
    text: 'text-warning-foreground',
    bg: 'bg-warning-muted',
    border: 'border-warning/40',
  },
  low: {
    label: 'Low confidence',
    dot: 'bg-danger',
    text: 'text-danger',
    bg: 'bg-danger-muted',
    border: 'border-danger/30',
  },
}
