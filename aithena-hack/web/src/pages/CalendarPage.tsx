import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Calendar, ChevronLeft, ChevronRight, LoaderCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getCalendarEvents } from '@/lib/api'
import type { ContractEvent } from '@/lib/types'

const priorityStyles = {
  urgent: { dot: 'bg-danger', label: 'Urgent', chip: 'bg-danger-muted text-danger' },
  upcoming: { dot: 'bg-warning', label: 'Upcoming', chip: 'bg-warning-muted text-warning-foreground' },
  clear: { dot: 'bg-success', label: 'Scheduled', chip: 'bg-success-muted text-success' },
}
const typeChip: Record<string, string> = {
  Renewal: 'bg-accent text-accent-foreground',
  Expiry: 'bg-muted text-muted-foreground',
  'Notice deadline': 'bg-warning-muted text-warning-foreground',
  'Payment obligation': 'bg-secondary text-secondary-foreground',
}
const months = ['January','February','March','April','May','June','July','August','September','October','November','December']

function parseEventDate(dateStr: string): { month: number; year: number } | null {
  // Handle formats like "6 Sep 2026" or ISO "2026-09-06"
  const parts = dateStr.split(' ')
  if (parts.length >= 3) {
    const monthAbbr: Record<string, number> = { Jan:0,Feb:1,Mar:2,Apr:3,May:4,Jun:5,Jul:6,Aug:7,Sep:8,Oct:9,Nov:10,Dec:11 }
    const m = monthAbbr[parts[1]]
    const y = parseInt(parts[2], 10)
    if (m !== undefined && !isNaN(y)) return { month: m, year: y }
  }
  // Try ISO format
  const iso = new Date(dateStr)
  if (!isNaN(iso.getTime())) return { month: iso.getMonth(), year: iso.getFullYear() }
  return null
}

type MonthSummary = { urgent: number; upcoming: number; clear: number; events: ContractEvent[] }

export default function CalendarPage() {
  const [events, setEvents] = useState<ContractEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null)
  const [selectedYear, setSelectedYear] = useState<number>(new Date().getFullYear())

  useEffect(() => {
    getCalendarEvents().then(setEvents).finally(() => setLoading(false))
  }, [])

  // Collect all years present in events for the year picker
  const availableYears = useMemo<number[]>(() => {
    const years = new Set<number>()
    years.add(new Date().getFullYear())
    for (const event of events) {
      const parsed = parseEventDate(event.date)
      if (parsed) years.add(parsed.year)
    }
    return Array.from(years).sort()
  }, [events])

  const byMonth = useMemo<MonthSummary[]>(() => {
    const buckets: MonthSummary[] = months.map(() => ({ urgent: 0, upcoming: 0, clear: 0, events: [] }))
    for (const event of events) {
      const parsed = parseEventDate(event.date)
      if (!parsed || parsed.year !== selectedYear) continue
      buckets[parsed.month].events.push(event)
      buckets[parsed.month][event.priority] += 1
    }
    return buckets
  }, [events, selectedYear])

  const selectedEvents = selectedMonth !== null ? [...byMonth[selectedMonth].events].sort((a, b) => a.daysAway - b.daysAway) : []

  if (loading) {
    return <main className="mx-auto max-w-5xl px-4 py-20 text-center"><LoaderCircle className="mx-auto size-8 animate-spin text-primary" /></main>
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <div className="mb-2 flex items-center gap-2">
        <Calendar className="size-6 text-primary" />
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Calendar</h1>
      </div>
      <p className="mb-6 text-muted-foreground">
        {selectedMonth === null
          ? 'Select a month to see its renewals, expirations, notice deadlines and payment obligations.'
          : `Events scheduled in ${months[selectedMonth]} ${selectedYear}.`}
      </p>

      {/* Year selector */}
      <div className="mb-6 flex items-center gap-4">
        <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
          <button
            type="button"
            onClick={() => setSelectedYear(y => y - 1)}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Previous year"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="min-w-[4rem] text-center text-sm font-semibold text-foreground">{selectedYear}</span>
          <button
            type="button"
            onClick={() => setSelectedYear(y => y + 1)}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Next year"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
        {availableYears.length > 1 && (
          <div className="flex flex-wrap gap-1">
            {availableYears.map(y => (
              <button
                key={y}
                type="button"
                onClick={() => { setSelectedYear(y); setSelectedMonth(null) }}
                className={cn(
                  'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                  y === selectedYear
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                {y}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="mb-6 flex flex-wrap gap-4 text-xs text-muted-foreground">
        {Object.entries(priorityStyles).map(([key, s]) => (
          <span key={key} className="flex items-center gap-1.5"><span className={cn('size-2 rounded-full', s.dot)} aria-hidden />{s.label}</span>
        ))}
      </div>
      {selectedMonth === null ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {byMonth.map((summary, idx) => {
            const total = summary.events.length
            return (
              <button key={months[idx]} type="button" onClick={() => setSelectedMonth(idx)}
                className="flex flex-col rounded-xl border border-border bg-card p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
                <div className="flex items-center justify-between">
                  <span className="text-base font-semibold text-foreground">{months[idx]}</span>
                  <span className="text-xs text-muted-foreground">{total} {total === 1 ? 'event' : 'events'}</span>
                </div>
                <dl className="mt-4 space-y-1.5">
                  {[{k:'urgent',c:summary.urgent},{k:'upcoming',c:summary.upcoming},{k:'clear',c:summary.clear}].map(({k,c})=>(
                    <div key={k} className="flex items-center justify-between text-sm">
                      <dt className="flex items-center gap-1.5 text-muted-foreground"><span className={cn('size-2 rounded-full',priorityStyles[k as keyof typeof priorityStyles].dot)} aria-hidden/>{priorityStyles[k as keyof typeof priorityStyles].label}</dt>
                      <dd className="font-semibold text-foreground">{c}</dd>
                    </div>
                  ))}
                </dl>
              </button>
            )
          })}
        </div>
      ) : (
        <div>
          <button type="button" onClick={() => setSelectedMonth(null)} className="mb-6 inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted">
            <ArrowLeft className="size-3.5" /> All months
          </button>
          {selectedEvents.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center">
              <p className="text-sm font-medium text-foreground">No events scheduled in {months[selectedMonth]} {selectedYear}.</p>
            </div>
          ) : (
            <ol className="space-y-3">
              {selectedEvents.map(event => {
                const s = priorityStyles[event.priority]
                return (
                  <li key={event.id} className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm sm:flex-row sm:items-center">
                    <div className="flex w-full items-center gap-3 sm:w-40 sm:flex-col sm:items-start">
                      <span className="text-sm font-semibold text-foreground">{event.date}</span>
                      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', s.chip)}>in {event.daysAway} days</span>
                    </div>
                    <div className="flex-1">
                      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', typeChip[event.type])}>{event.type}</span>
                      <p className="mt-1 text-sm font-medium text-foreground">{event.contract}</p>
                    </div>
                    <Link to={`/contracts/${event.contractId}`} className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                      View Contract <ArrowRight className="size-3.5" />
                    </Link>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      )}
    </main>
  )
}
