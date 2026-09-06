import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import { ContractLibrary } from '@/components/contract-library'
import { getContracts } from '@/lib/api'
import type { Contract } from '@/lib/types'

export default function ContractsPage() {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getContracts().then(setContracts).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-20 text-center">
        <LoaderCircle className="mx-auto size-8 animate-spin text-primary" />
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Contracts</h1>
        <p className="mt-1 text-muted-foreground">Search, filter, and open any contract in your portfolio.</p>
      </div>
      <ContractLibrary contracts={contracts} heading="All Contracts" description="Open a contract to see its evidence-grounded analysis." />
    </main>
  )
}
