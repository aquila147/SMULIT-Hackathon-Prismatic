import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Contract } from '@/lib/types'

const priorityStyles = {
  urgent: { bar: 'bg-danger', tag: 'bg-danger-muted text-danger', ring: 'border-danger/30' },
  review: { bar: 'bg-warning', tag: 'bg-warning-muted text-warning-foreground', ring: 'border-warning/40' },
}

export function AttentionSection({ contracts }: { contracts: Contract[] }) {
  // Show contracts that need action — those with alerts
  const items = contracts
    .filter(c => c.alert)
    .sort((a, b) => (a.alert?.level === 'urgent' ? 0 : 1) - (b.alert?.level === 'urgent' ? 0 : 1))
    .slice(0, 6)

  if (items.length === 0) return null

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">What Needs Your Attention</h2>
        <p className="text-sm text-muted-foreground">The most time-sensitive events across your portfolio.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {items.map(item => {
          const s = priorityStyles[item.alert!.level === 'urgent' ? 'urgent' : 'review']
          return (
            <div key={item.id} className={cn('relative overflow-hidden rounded-xl border bg-card p-5 shadow-sm', s.ring)}>
              <span className={cn('absolute inset-y-0 left-0 w-1', s.bar)} aria-hidden />
              <span className={cn('inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide', s.tag)}>
                {item.alert!.level === 'urgent' ? 'Urgent' : 'Review'}
              </span>
              <h3 className="mt-3 text-base font-semibold text-foreground">{item.name}</h3>
              <p className="mt-1 text-sm font-medium text-foreground">{item.alert!.label}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{item.parties}</p>
              <Link to={`/contracts/${item.id}`} className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                View Contract <ArrowRight className="size-3.5" />
              </Link>
            </div>
          )
        })}
      </div>
    </section>
  )
}
