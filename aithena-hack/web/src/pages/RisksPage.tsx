import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, GitCompare, LoaderCircle, TriangleAlert, ShieldAlert, FileQuestion, Scale } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getContracts, getConflicts, getPortfolioRisk, getGaps } from '@/lib/api'
import type { Contract, Conflict } from '@/lib/types'
import type { PortfolioRisk, GapsResponse } from '@/lib/api'

const severityStyles: Record<string, string> = {
  high: 'bg-danger-muted text-danger',
  medium: 'bg-warning-muted text-warning-foreground',
  low: 'bg-muted text-muted-foreground',
}

function humanizeKind(kind: string): string {
  switch (kind) {
    case 'unresolved_parent': return 'References another agreement not in your folder'
    case 'unresolved_reference': return 'References a document not in your folder'
    case 'missing_schedule': return 'References a schedule/annex not attached'
    default: return kind.replace(/_/g, ' ')
  }
}

export default function RisksPage() {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [risk, setRisk] = useState<PortfolioRisk | null>(null)
  const [gaps, setGaps] = useState<GapsResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getContracts(), getConflicts(), getPortfolioRisk(), getGaps()])
      .then(([c, cf, r, g]) => { setContracts(c); setConflicts(cf); setRisk(r); setGaps(g) })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <main className="mx-auto max-w-4xl px-4 py-20 text-center"><LoaderCircle className="mx-auto size-8 animate-spin text-primary" /></main>

  const needsReview = contracts.filter(c => c.status === 'needs-review' || c.status === 'action-required')
  const bySeverity = risk?.summary?.by_severity
  const hasRisk = !!risk && risk.summary.total_findings > 0
  const hasGaps = !!gaps && gaps.gaps.length > 0

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Risks &amp; Conflicts</h1>
      <p className="mt-1 text-muted-foreground">Potential conflicts, risk flags, and unresolved references. These are indicators, not confirmed legal conclusions.</p>

      {/* Portfolio Risk */}
      <section className="mt-8">
        <h2 className="mb-1 text-lg font-semibold text-foreground">Portfolio Risk</h2>
        {hasRisk ? (
          <>
            <p className="mb-4 max-w-2xl text-xs text-muted-foreground">{risk!.summary.disclaimer}</p>
            <div className="mb-4 flex flex-wrap gap-2">
              {bySeverity && bySeverity.high > 0 && (
                <span className={cn('rounded-full px-3 py-1 text-xs font-medium', severityStyles.high)}>{bySeverity.high} high</span>
              )}
              {bySeverity && bySeverity.medium > 0 && (
                <span className={cn('rounded-full px-3 py-1 text-xs font-medium', severityStyles.medium)}>{bySeverity.medium} medium</span>
              )}
              {bySeverity && bySeverity.low > 0 && (
                <span className={cn('rounded-full px-3 py-1 text-xs font-medium', severityStyles.low)}>{bySeverity.low} low</span>
              )}
            </div>
            <div className="space-y-3">
              {risk!.contracts.map(rc => (
                <div key={rc.contract_id} className="rounded-xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex items-center gap-2">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground"><ShieldAlert className="size-4" /></span>
                    <Link to={`/contracts/${rc.contract_id}`} className="text-sm font-semibold text-foreground hover:underline">{rc.filename}</Link>
                    <span className="rounded-md border border-border bg-muted px-2 py-0.5 text-[11px] font-medium capitalize text-muted-foreground">{rc.sme_role}</span>
                  </div>
                  <div className="mt-3 space-y-3">
                    {rc.findings.map(f => (
                      <div key={f.id} className="border-l-2 border-border pl-3">
                        <div className="flex items-center gap-2">
                          <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium capitalize', severityStyles[f.severity])}>{f.severity}</span>
                          {f.requires_lawyer ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"><Scale className="size-3" />Legal review</span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-sm font-medium text-foreground">{f.assertion}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{f.evidence}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">No risk flags raised across your portfolio.</p>
        )}
      </section>

      {/* Unresolved References */}
      <section className="mt-10">
        <h2 className="mb-1 text-lg font-semibold text-foreground">Unresolved References</h2>
        {hasGaps ? (
          <>
            <p className="mb-4 max-w-2xl text-xs text-muted-foreground">{gaps!.note}</p>
            <div className="space-y-3">
              {gaps!.gaps.map(g => (
                <div key={g.id} className="rounded-xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex items-center gap-2">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground"><FileQuestion className="size-4" /></span>
                    <span className="text-sm font-semibold text-foreground">{g.source_filename}</span>
                    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium capitalize', g.resolution === 'ambiguous' ? severityStyles.medium : severityStyles.low)}>
                      {g.resolution}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{humanizeKind(g.kind)}</p>
                  {g.reference_text && (
                    <p className="mt-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm italic text-foreground">&ldquo;{g.reference_text}&rdquo;</p>
                  )}
                  {g.candidates && g.candidates.length > 0 && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      {g.candidates.map((cand, i) => (
                        <div key={i}>
                          Considered <span className="font-medium text-foreground">{cand.filename}</span>
                          {cand.rejected_because ? ` \u2014 ${cand.rejected_because}` : ''}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="mt-2 text-xs text-muted-foreground">{g.language_note}</p>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">No unresolved references found.</p>
        )}
      </section>

      {/* Potential Conflicts */}
      <section className="mt-10">
        <h2 className="mb-4 text-lg font-semibold text-foreground">Potential Conflicts</h2>
        {conflicts.length > 0 ? (
          <div className="space-y-3">
            {conflicts.map(conflict => (
              <div key={conflict.id} id={conflict.id} className="rounded-xl border border-border bg-card p-5 shadow-sm scroll-mt-24">
                <div className="flex items-center gap-2">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground"><GitCompare className="size-4" /></span>
                  <h3 className="text-sm font-semibold text-foreground">{conflict.title}</h3>
                  <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium capitalize', severityStyles[conflict.severity])}>
                    {conflict.severity} &middot; requires legal review
                  </span>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{conflict.summary}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded-md border border-border bg-muted px-2 py-1 font-medium text-foreground">{conflict.contractA.name}</span>
                  <span className="text-muted-foreground">may conflict with</span>
                  <span className="rounded-md border border-border bg-muted px-2 py-1 font-medium text-foreground">{conflict.contractB.name}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">No conflicts detected.</p>
        )}
      </section>

      {/* Contracts Requiring Review */}
      <section className="mt-10">
        <h2 className="mb-4 text-lg font-semibold text-foreground">Contracts Requiring Review</h2>
        {needsReview.length > 0 ? (
          <div className="space-y-2">
            {needsReview.map(c => (
              <Link key={c.id} to={`/contracts/${c.id}`} className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 shadow-sm transition-colors hover:bg-muted/40">
                <span className={cn('flex size-8 items-center justify-center rounded-lg', c.status === 'action-required' ? 'bg-danger-muted text-danger' : 'bg-warning-muted text-warning-foreground')}>
                  <TriangleAlert className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{c.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {c.fieldsNeedReview > 0 ? `${c.fieldsNeedReview} fields require review` : 'Action required'} &middot; {c.parties}
                  </p>
                </div>
                <ArrowRight className="size-4 shrink-0 text-primary" />
              </Link>
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">All contracts are high confidence.</p>
        )}
      </section>
    </main>
  )
}
