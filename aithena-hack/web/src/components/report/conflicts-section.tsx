import { Link } from 'react-router-dom'
import { ArrowRight, GitCompare } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Conflict } from '@/lib/types'

const severityStyles: Record<string, string> = { high: 'bg-danger-muted text-danger', medium: 'bg-warning-muted text-warning-foreground' }

export function ConflictsSection({ conflicts }: { conflicts: Conflict[] }) {
  if (conflicts.length === 0) return null
  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">Potential Conflicts</h2>
        <p className="text-sm text-muted-foreground">Flagged for review. These are not confirmed legal conclusions.</p>
      </div>
      <div className="space-y-3">
        {conflicts.map(conflict => (
          <div key={conflict.id} className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                  <GitCompare className="size-4" />
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-foreground">{conflict.title}</h3>
                    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium capitalize', severityStyles[conflict.severity])}>
                      {conflict.severity} · requires legal review
                    </span>
                  </div>
                  <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{conflict.summary}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-md border border-border bg-muted px-2 py-1 font-medium text-foreground">{conflict.contractA.name}</span>
                    <span className="text-muted-foreground">may conflict with</span>
                    <span className="rounded-md border border-border bg-muted px-2 py-1 font-medium text-foreground">{conflict.contractB.name}</span>
                  </div>
                </div>
              </div>
              <Link to={`/risks#${conflict.id}`} className="inline-flex shrink-0 items-center justify-center gap-1 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted">
                Investigate <ArrowRight className="size-3.5" />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
