import type {
  BackendContract,
  BackendField,
  BackendConflict,
  BackendCalendarEvent,
  BackendHandoff,
  BackendPortfolioStats,
  BackendConfidence,
  Contract,
  ExtractedField,
  Conflict,
  ContractEvent,
  PortfolioStat,
  UIConfidence,
  ContractStatus,
} from './types'

const API = '/api'

// ─── Confidence mapping ────────────────────────────────────────────

const FIELD_NAME_LABELS: Record<string, string> = {
  parties: 'Parties',
  contract_type: 'Contract Type',
  start_date: 'Start Date',
  end_date: 'End Date',
  renewal_type: 'Renewal & Notice',
  notice_period_days: 'Notice Period',
  termination_rights: 'Termination Rights',
  payment_obligations: 'Payment Obligations',
  liability_cap: 'Liability Cap',
  exclusivity: 'Exclusivity / Restrictive Covenants',
  restrictive_covenants: 'Restrictive Covenants',
  governing_law: 'Governing Law',
}

function mapConfidence(c: BackendConfidence): UIConfidence {
  switch (c) {
    case 'VERIFIED': return 'high'
    case 'INFERRED': return 'medium'
    case 'CONTESTED': return 'low'
    case 'UNGROUNDED': return 'low'
  }
}

function mapField(f: BackendField, contract: BackendContract): ExtractedField {
  const conf = mapConfidence(f.confidence)
  const isUngrounded = f.confidence === 'UNGROUNDED'
  const isContested = f.confidence === 'CONTESTED'
  const needsReview = isContested || f.confidence === 'INFERRED'
  const label = FIELD_NAME_LABELS[f.field_name] || f.field_name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  // Build action deadline for renewal notice
  let actionDeadline: string | undefined
  if (f.field_name === 'renewal_type' && contract.notice_deadline) {
    actionDeadline = contract.notice_deadline
  }

  return {
    id: f.field_name,
    category: label,
    label,
    finding: isUngrounded && !f.value ? 'Not identified' : (f.value || 'Not identified'),
    secondary: f.value_alt || undefined,
    confidence: conf,
    notFound: isUngrounded || !f.value,
    legalReview: needsReview,
    page: f.page !== null ? f.page + 1 : null,   // 0-indexed → 1-indexed for display
    clause: f.page !== null ? `§${f.page + 1}` : null,
    actionDeadline,
    clauseText: f.verbatim_quote || undefined,
    bbox: f.bbox || undefined,
  }
}

function deriveStatus(fields: ExtractedField[], contract: BackendContract): ContractStatus {
  const hasUngrounded = fields.some(f => f.notFound)
  const hasReview = fields.some(f => f.legalReview)
  const needsAction = contract.notice_deadline != null

  if (needsAction || hasUngrounded) return 'action-required'
  if (hasReview) return 'needs-review'
  return 'high-confidence'
}

function deriveOverallConfidence(fields: ExtractedField[]): UIConfidence {
  const lowCount = fields.filter(f => f.confidence === 'low').length
  const medCount = fields.filter(f => f.confidence === 'medium').length
  if (lowCount > 0) return 'low'
  if (medCount > fields.length * 0.3) return 'medium'
  return 'high'
}

function deriveAlert(contract: BackendContract, fields: ExtractedField[]): Contract['alert'] | undefined {
  // Check for upcoming notice deadlines
  if (contract.notice_deadline) {
    const deadline = new Date(contract.notice_deadline)
    const now = new Date()
    const daysAway = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
    if (daysAway <= 30) return { level: 'urgent', label: 'Renewal approaching' }
  }
  const reviewCount = fields.filter(f => f.legalReview).length
  if (reviewCount > 0) return { level: 'review', label: `${reviewCount} fields require review` }
  return undefined
}

function fileExtension(filename: string): 'pdf' | 'docx' | 'pptx' {
  const ext = filename.split('.').pop()?.toLowerCase()
  if (ext === 'docx' || ext === 'doc') return 'docx'
  if (ext === 'pptx' || ext === 'ppt') return 'pptx'
  return 'pdf'
}

function mapContract(bc: BackendContract): Contract {
  const fields = (bc.fields || []).map(f => mapField(f, bc))
  const status = deriveStatus(fields, bc)
  const confidence = deriveOverallConfidence(fields)
  const extracted = fields.filter(f => !f.notFound).length

  return {
    id: bc.id,
    slug: bc.filename.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase(),
    name: bc.filename,
    fileType: fileExtension(bc.filename),
    parties: bc.parties || 'Unknown parties',
    status,
    confidence,
    fieldsExtracted: extracted,
    fieldsTotal: fields.length,
    fieldsNeedReview: fields.filter(f => f.legalReview).length,
    clausesTotal: bc.clauses_total,
    clausesCovered: bc.clauses_covered,
    isScanned: bc.is_scanned,
    alert: deriveAlert(bc, fields),
    lastAnalysed: new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }),
    fields,
    renewalType: bc.renewal_type || undefined,
    noticeDeadline: bc.notice_deadline || undefined,
    startDate: bc.start_date || undefined,
    endDate: bc.end_date || undefined,
  }
}

// ─── Event type mapping ────────────────────────────────────────────

function mapEventType(t: string): ContractEvent['type'] {
  switch ((t || '').toLowerCase()) {
    case 'renewal': return 'Renewal'
    case 'expiry': return 'Expiry'
    case 'notice_deadline': return 'Notice deadline'
    case 'payment': return 'Payment obligation'
    default: return 'Renewal'
  }
}

function mapCalendarEvent(e: BackendCalendarEvent): ContractEvent {
  const d = new Date(e.date)
  return {
    id: `evt-${e.contract_id}-${e.event_type}`,
    contractId: e.contract_id,
    contract: e.contract_filename,
    type: mapEventType(e.event_type),
    date: d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }),
    daysAway: e.days_away,
    priority: (e.priority as 'urgent' | 'upcoming' | 'clear') || 'clear',
  }
}

function mapConflict(c: BackendConflict): Conflict {
  return {
    id: `conflict-${c.id}`,
    title: `${c.kind.replace(/_/g, ' ').replace(/\b\w/g, x => x.toUpperCase())} detected`,
    summary: c.description,
    contractA: { id: c.contract_a_id, name: c.contract_a_filename },
    contractB: { id: c.contract_b_id, name: c.contract_b_filename },
    severity: (c.severity as 'high' | 'medium') || 'medium',
  }
}

// ─── API calls ─────────────────────────────────────────────────────

export async function uploadContracts(files: File[]): Promise<Contract[]> {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  const res = await fetch(`${API}/upload`, { method: 'POST', body: formData })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  const data: any[] = await res.json()
  return data.filter(d => !d.error && d.fields).map(mapContract)
}

export async function getContracts(): Promise<Contract[]> {
  const res = await fetch(`${API}/contracts`)
  if (!res.ok) throw new Error(`Failed to fetch contracts: ${res.status}`)
  const data: any[] = await res.json()
  return data.filter(d => !d.error).map(mapContract)
}

export async function getContract(id: number): Promise<Contract | null> {
  const res = await fetch(`${API}/contracts/${id}`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`Failed to fetch contract: ${res.status}`)
  const data: BackendContract = await res.json()
  return mapContract(data)
}

export async function getCalendarEvents(): Promise<ContractEvent[]> {
  const res = await fetch(`${API}/calendar`)
  if (!res.ok) throw new Error(`Failed to fetch calendar: ${res.status}`)
  const data: BackendCalendarEvent[] = await res.json()
  return data.map(mapCalendarEvent)
}

export async function getConflicts(): Promise<Conflict[]> {
  const res = await fetch(`${API}/conflicts`)
  if (!res.ok) throw new Error(`Failed to fetch conflicts: ${res.status}`)
  const data: BackendConflict[] = await res.json()
  return data.map(mapConflict)
}

export async function getHandoff(contractId: number): Promise<BackendHandoff | null> {
  const res = await fetch(`${API}/contracts/${contractId}/handoff`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`Failed to fetch handoff: ${res.status}`)
  return res.json()
}

export async function getPortfolioStats(): Promise<PortfolioStat[]> {
  const res = await fetch(`${API}/stats`)
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`)
  const data: BackendPortfolioStats = await res.json()
  return [
    { id: 'actions', label: 'Actions Required', value: data.actions_required, tone: 'danger', icon: 'alert', hint: 'Deadlines that need a decision' },
    { id: 'renewals', label: 'Renewals — Next 90 Days', value: data.renewals_90_days, tone: 'warning', icon: 'refresh', hint: 'Auto-renewals approaching' },
    { id: 'conflicts', label: 'Potential Conflicts', value: data.potential_conflicts, tone: 'primary', icon: 'shuffle', hint: 'Flagged for legal review' },
    { id: 'legal', label: 'Legal Review Needed', value: data.legal_review_needed, tone: 'muted', icon: 'scale', hint: 'Ambiguous or medium-confidence terms' },
  ]
}

export function getPageImageUrl(contractId: number, pageNum: number): string {
  return `${API}/pages/${contractId}/${pageNum}/image`
}

export function getExportUrl(type: 'results' | 'coverage'): string {
  return `${API}/export/${type}`
}

// ─── Portfolio query (Ask page) ───────────────────────────────────

export async function queryPortfolio(question: string): Promise<{ answer: string; isError: boolean }> {
  try {
    const res = await fetch(`${API}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    if (!res.ok) {
      return { answer: "Sorry, I can't reply to this question.", isError: true }
    }
    const data = await res.json()
    if (data.error) {
      return { answer: "Sorry, I can't reply to this question.", isError: true }
    }
    return { answer: data.answer || "Sorry, I can't reply to this question.", isError: false }
  } catch {
    return { answer: "Sorry, I can't reply to this question.", isError: true }
  }
}

// ─── Portfolio Risk & Gaps ─────────────────────────────────────────

export interface RiskFinding {
  id: number
  contract_id: number
  field_name: string
  assertion: string
  severity: 'high' | 'medium' | 'low'
  basis: string
  evidence: string
  requires_lawyer: number
}

export interface RiskContract {
  contract_id: number
  filename: string
  sme_role: string
  findings: RiskFinding[]
}

export interface PortfolioRisk {
  summary: {
    total_findings: number
    by_severity: { high: number; medium: number; low: number }
    flagged_contracts: { filename: string; contract_id: number; finding_count: number; highest_severity: string }[]
    disclaimer: string
  }
  contracts: RiskContract[]
}

export interface Gap {
  id: number
  source_filename: string
  kind: string
  reference_text: string | null
  resolution: 'resolved' | 'ambiguous' | 'unresolved'
  candidates: { filename: string; score: number; rejected_because: string | null }[]
  language_note: string
}

export interface GapsResponse {
  gaps: Gap[]
  total: number
  note: string
}

export async function getPortfolioRisk(): Promise<PortfolioRisk | null> {
  try {
    const res = await fetch(`${API}/risk`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function getGaps(): Promise<GapsResponse | null> {
  try {
    const res = await fetch(`${API}/gaps`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}
