import { ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { confidenceMeta, type Contract } from '@/lib/types'

export function AnalysisQuality({ contract }: { contract: Contract }) {
  const high = contract.fields.filter(f => f.confidence === 'high' && !f.notFound).length
  const medium = contract.fields.filter(f => f.confidence === 'medium').length
  const low = contract.fields.filter(f => f.confidence === 'low' || f.notFound).length
  const total = contract.fields.length
  const meta = confidenceMeta[contract.confidence]
  const overallLabel = contract.confidence === 'high' ? 'High Confidence' : contract.confidence === 'medium' ? 'Medium Confidence' : 'Low Confidence'
  const breakdown = [
    { label: 'High confidence', count: high, dot: 'bg-success' },
    { label: 'Medium confidence', count: medium, dot: 'bg-warning' },
    { label: 'Needs review', count: low, dot: 'bg-danger' },
  ].filter(b => b.count > 0)

  return (
    <div className={cn('rounded-xl border p-5 shadow-sm', meta.border, meta.bg)}>
      <div className="flex items-start gap-4">
        <span className={cn('flex size-11 shrink-0 items-center justify-center rounded-xl bg-card', meta.text)}>
          <ShieldCheck className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Analysis Quality</p>
          <div className="mt-1 flex items-center gap-2">
            <span className={cn('size-2.5 rounded-full', meta.dot)} aria-hidden />
            <h2 className={cn('text-lg font-semibold', meta.text)}>{overallLabel}</h2>
          </div>
          <p className="mt-1 text-sm text-foreground/80">
            {total} fields analysed · {high} high confidence
            {medium > 0 && ` · ${medium} medium confidence`}
            {low > 0 && ` · ${low} need review`}
          </p>
          {contract.clausesTotal > 0 && (
            <p className="mt-1 text-sm text-foreground/80">
              {contract.clausesCovered} of {contract.clausesTotal} clauses accounted for
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
            {breakdown.map(b => (
              <div key={b.label} className="flex items-center gap-2 text-sm">
                <span className={cn('size-2 rounded-full', b.dot)} aria-hidden />
                <span className="font-medium text-foreground">{b.count}</span>
                <span className="text-muted-foreground">{b.label}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 rounded-lg bg-card/70 px-3 py-2 text-xs text-muted-foreground">
            Confidence is assigned by code — span matching, cross-extractor agreement, and schema checks — never by model self-assessment. Always confirm legal conclusions with a professional.
          </p>
        </div>
      </div>
    </div>
  )
}
