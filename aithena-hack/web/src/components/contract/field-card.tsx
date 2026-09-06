import { ArrowRight, FileText, TriangleAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ConfidenceBadge, LegalReviewBadge } from '@/components/confidence-badge'
import type { ExtractedField } from '@/lib/types'

export function FieldCard({ field, onViewSource }: { field: ExtractedField; onViewSource: (f: ExtractedField) => void }) {
  const hasSource = field.page !== null && field.clauseText

  return (
    <div className={cn('flex h-full flex-col rounded-xl border bg-card p-5 shadow-sm', field.notFound ? 'border-dashed border-warning/50' : 'border-border')}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{field.label}</p>
        <ConfidenceBadge level={field.confidence} />
      </div>
      <div className="mt-2 flex-1">
        <p className={cn('text-base font-medium', field.notFound ? 'text-muted-foreground' : 'text-foreground')}>{field.finding}</p>
        {field.secondary && <p className="mt-1 text-sm text-muted-foreground">{field.secondary}</p>}
      </div>
      {field.actionDeadline && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-danger-muted px-3 py-2 text-xs font-semibold text-danger">
          <TriangleAlert className="size-4" />
          <span className="uppercase tracking-wide">Action deadline</span>
          <span className="ml-auto">{field.actionDeadline}</span>
        </div>
      )}
      {field.legalReview && <div className="mt-3"><LegalReviewBadge /></div>}
      <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
        {hasSource ? (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <FileText className="size-3.5" /> Page {field.page}
          </span>
        ) : (
          <span className="text-xs italic text-muted-foreground">No source located</span>
        )}
        {hasSource && (
          <button type="button" onClick={() => onViewSource(field)} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            View Source <ArrowRight className="size-3" />
          </button>
        )}
      </div>
    </div>
  )
}
