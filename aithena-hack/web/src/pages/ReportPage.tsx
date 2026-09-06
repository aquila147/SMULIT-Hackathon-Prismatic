import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Download, LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StatCards } from '@/components/report/stat-cards'
import { AttentionSection } from '@/components/report/attention-section'
import { EventsTimeline } from '@/components/report/events-timeline'
import { ConflictsSection } from '@/components/report/conflicts-section'
import { ContractLibrary } from '@/components/contract-library'
import { getContracts, getCalendarEvents, getConflicts, getPortfolioStats, getExportUrl } from '@/lib/api'
import type { Contract, ContractEvent, Conflict, PortfolioStat } from '@/lib/types'

export default function ReportPage() {
  const location = useLocation()
  const [contracts, setContracts] = useState<Contract[]>([])
  const [events, setEvents] = useState<ContractEvent[]>([])
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [stats, setStats] = useState<PortfolioStat[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const [c, e, cf, s] = await Promise.all([
          getContracts(),
          getCalendarEvents(),
          getConflicts(),
          getPortfolioStats(),
        ])
        setContracts(c)
        setEvents(e)
        setConflicts(cf)
        setStats(s)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // Scroll to the hash anchor once data has loaded
  useEffect(() => {
    if (!loading && location.hash) {
      const id = location.hash.replace('#', '')
      // Small delay to let the DOM render the sections
      const timer = setTimeout(() => {
        const el = document.getElementById(id)
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [loading, location.hash])

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-20 text-center">
        <LoaderCircle className="mx-auto size-8 animate-spin text-primary" />
        <p className="mt-4 text-muted-foreground">Loading portfolio data...</p>
      </main>
    )
  }

  if (error) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-20 text-center">
        <p className="text-danger">{error}</p>
        <p className="mt-2 text-sm text-muted-foreground">Upload contracts from the home page to get started.</p>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Contract Intelligence</h1>
          <p className="mt-1 text-muted-foreground">Your contracts at a glance</p>
          <p className="mt-1 text-sm text-muted-foreground">{contracts.length} contracts analysed</p>
        </div>
        <div className="flex gap-2 self-start sm:self-auto">
          <Button variant="outline" size="lg" className="h-10" onClick={() => window.open(getExportUrl('results'))}>
            <Download className="size-4" /> Download Results CSV
          </Button>
          <Button variant="outline" size="lg" className="h-10" onClick={() => window.open(getExportUrl('coverage'))}>
            <Download className="size-4" /> Coverage CSV
          </Button>
        </div>
      </div>

      <div className="mt-8 space-y-10">
        <StatCards stats={stats} />
        <div id="attention" className="scroll-mt-24"><AttentionSection contracts={contracts} /></div>
        <div id="events" className="scroll-mt-24"><EventsTimeline events={events} /></div>
        <div id="conflicts" className="scroll-mt-24"><ConflictsSection conflicts={conflicts} /></div>
      </div>

      <div className="my-10 h-px bg-border" />

      <ContractLibrary contracts={contracts} />
    </main>
  )
}
