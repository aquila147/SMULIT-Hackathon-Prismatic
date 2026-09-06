import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Contract, ContractStatus } from '@/lib/types'

type Filter = 'all' | ContractStatus
type Sort = 'urgent' | 'confidence' | 'name'

const filters: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'high-confidence', label: 'High Confidence' },
  { value: 'needs-review', label: 'Needs Review' },
  { value: 'action-required', label: 'Action Required' },
]
const sorts: { value: Sort; label: string }[] = [
  { value: 'urgent', label: 'Most urgent' },
  { value: 'confidence', label: 'Confidence' },
  { value: 'name', label: 'Contract name' },
]
const statusMeta: Record<ContractStatus, { dot: string; rank: number }> = {
  'action-required': { dot: 'bg-danger', rank: 0 },
  'needs-review': { dot: 'bg-warning', rank: 1 },
  'high-confidence': { dot: 'bg-success', rank: 2 },
}
const confidenceRank = { high: 0, medium: 1, low: 2 }

function ContractCard({ contract }: { contract: Contract }) {
  const fieldDot = contract.confidence === 'high' ? 'text-success' : contract.confidence === 'medium' ? 'text-warning-foreground' : 'text-danger'
  return (
    <div className="flex flex-col rounded-xl border border-border bg-card p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-foreground">{contract.name}</h3>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{contract.parties}</p>
        </div>
        <span className={cn('mt-1 size-2 shrink-0 rounded-full', statusMeta[contract.status].dot)} aria-hidden />
      </div>
      <div className="mt-3 space-y-1.5 text-xs">
        <p className={cn('flex items-center gap-1.5 font-medium', fieldDot)}>
          <span className="size-1.5 rounded-full bg-current" aria-hidden />
          {contract.fieldsExtracted}/{contract.fieldsTotal} fields confidently extracted
        </p>
        {contract.clausesTotal > 0 && (
          <p className="text-muted-foreground">{contract.clausesCovered} of {contract.clausesTotal} clauses accounted for</p>
        )}
        {contract.alert && (
          <p className={cn('flex items-center gap-1.5 font-medium', contract.alert.level === 'urgent' ? 'text-danger' : 'text-warning-foreground')}>
            <span className={cn('size-1.5 rounded-full', contract.alert.level === 'urgent' ? 'bg-danger' : 'bg-warning')} aria-hidden />
            {contract.alert.label}
          </p>
        )}
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
        <span className="text-[11px] text-muted-foreground">
          {contract.isScanned ? 'Scanned document' : contract.fileType.toUpperCase()}
        </span>
        <Link to={`/contracts/${contract.id}`} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
          Open Contract <ArrowRight className="size-3" />
        </Link>
      </div>
    </div>
  )
}

export function ContractLibrary({ contracts, heading = 'Contract Library', description = 'Find and open individual contracts.' }: {
  contracts: Contract[]
  heading?: string
  description?: string
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<Sort>('urgent')

  const visible = useMemo(() => {
    let list = contracts.filter(c => {
      const matchesQuery = !query || c.name.toLowerCase().includes(query.toLowerCase()) || c.parties.toLowerCase().includes(query.toLowerCase())
      const matchesFilter = filter === 'all' || c.status === filter
      return matchesQuery && matchesFilter
    })
    list = [...list].sort((a, b) => {
      switch (sort) {
        case 'urgent': return statusMeta[a.status].rank - statusMeta[b.status].rank
        case 'confidence': return confidenceRank[a.confidence] - confidenceRank[b.confidence]
        case 'name': return a.name.localeCompare(b.name)
        default: return 0
      }
    })
    return list
  }, [contracts, query, filter, sort])

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">{heading}</h2>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <span className="rounded-full border border-border bg-card px-3 py-1 text-sm font-medium text-muted-foreground">
          {contracts.length} contracts
        </span>
      </div>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full lg:max-w-xs">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search contracts..."
            className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-3 focus:ring-ring/20" />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-card p-1">
            {filters.map(f => (
              <button key={f.value} type="button" onClick={() => setFilter(f.value)}
                className={cn('rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                  filter === f.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>
                {f.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="hidden sm:inline">Sort</span>
            <select value={sort} onChange={e => setSort(e.target.value as Sort)}
              className="rounded-lg border border-border bg-card px-2.5 py-2 text-xs font-medium text-foreground outline-none focus:border-primary">
              {sorts.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </label>
        </div>
      </div>
      {visible.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map(c => <ContractCard key={c.id} contract={c} />)}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No contracts match your search.
        </div>
      )}
      <p className="mt-4 text-center text-xs text-muted-foreground">
        Showing {visible.length} of {contracts.length} analysed contracts
      </p>
    </section>
  )
}
