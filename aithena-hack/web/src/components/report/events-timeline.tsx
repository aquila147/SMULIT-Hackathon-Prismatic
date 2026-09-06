import { Link } from 'react-router-dom'
import { ArrowRight, Calendar } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { ContractEvent } from '@/lib/types'

const dotStyles: Record<string, string> = { urgent: 'bg-danger', upcoming: 'bg-warning', clear: 'bg-success' }
const typeStyles: Record<string, string> = {
  Renewal: 'bg-accent text-accent-foreground',
  Expiry: 'bg-muted text-muted-foreground',
  'Notice deadline': 'bg-warning-muted text-warning-foreground',
  'Payment obligation': 'bg-secondary text-secondary-foreground',
}

export function EventsTimeline({ events }: { events: ContractEvent[] }) {
  const displayed = events.slice(0, 8)
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="size-5 text-primary" />
          <div>
            <CardTitle>Upcoming Contract Events</CardTitle>
            <p className="text-sm text-muted-foreground">Next 90 days</p>
          </div>
        </div>
        <Link to="/calendar" className="hidden items-center gap-1 text-sm font-medium text-primary hover:underline sm:inline-flex">
          View Full Calendar <ArrowRight className="size-3.5" />
        </Link>
      </CardHeader>
      <CardContent>
        {displayed.length > 0 ? (
          <ol className="relative space-y-1 border-l border-border pl-6">
            {displayed.map(event => (
              <li key={event.id} className="relative py-2.5">
                <span className={cn('absolute -left-[27px] top-4 size-3 rounded-full ring-4 ring-card', dotStyles[event.priority])} aria-hidden />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', typeStyles[event.type])}>{event.type}</span>
                      <Link to={`/contracts/${event.contractId}`} className="truncate text-sm font-medium text-foreground hover:underline">{event.contract}</Link>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-foreground">{event.date}</p>
                    <p className="text-xs text-muted-foreground">in {event.daysAway} days</p>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">No upcoming events in the next 90 days.</p>
        )}
        <Link to="/calendar" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline sm:hidden">
          View Full Calendar <ArrowRight className="size-3.5" />
        </Link>
      </CardContent>
    </Card>
  )
}
