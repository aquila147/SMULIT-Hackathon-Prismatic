import { Link } from 'react-router-dom'
import { ArrowUpRight, RefreshCw, Scale, Shuffle, TriangleAlert } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { PortfolioStat } from '@/lib/types'

const iconMap: Record<string, React.ElementType> = { alert: TriangleAlert, refresh: RefreshCw, shuffle: Shuffle, scale: Scale }
const hrefMap: Record<string, string> = { actions: '/report#attention', renewals: '/report#events', conflicts: '/report#conflicts', legal: '/risks' }
const toneMap: Record<string, string> = { danger: 'bg-danger-muted text-danger', warning: 'bg-warning-muted text-warning-foreground', primary: 'bg-accent text-accent-foreground', muted: 'bg-muted text-muted-foreground' }

export function StatCards({ stats }: { stats: PortfolioStat[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map(stat => {
        const Icon = iconMap[stat.icon] || TriangleAlert
        return (
          <Link key={stat.id} to={hrefMap[stat.id] ?? '/report'} className="group rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <Card className="h-full p-5 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
              <div className="flex items-start justify-between">
                <span className={cn('flex size-10 items-center justify-center rounded-lg', toneMap[stat.tone])}>
                  <Icon className="size-5" />
                </span>
                <span className="text-3xl font-semibold tracking-tight text-foreground">{stat.value}</span>
              </div>
              <p className="mt-4 flex items-center gap-1 text-sm font-medium text-foreground">
                {stat.label}
                <ArrowUpRight className="size-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">{stat.hint}</p>
            </Card>
          </Link>
        )
      })}
    </div>
  )
}
