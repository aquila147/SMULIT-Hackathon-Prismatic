import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { LoaderCircle } from 'lucide-react'
import { ContractDetail } from '@/components/contract/contract-detail'
import { getContract } from '@/lib/api'
import type { Contract } from '@/lib/types'

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [contract, setContract] = useState<Contract | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!id) return
    getContract(Number(id))
      .then(c => { if (c) setContract(c); else setNotFound(true) })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-20 text-center">
        <LoaderCircle className="mx-auto size-8 animate-spin text-primary" />
      </main>
    )
  }
  if (notFound || !contract) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-20 text-center">
        <h1 className="text-2xl font-semibold text-foreground">Contract not found</h1>
        <p className="mt-2 text-muted-foreground">This contract may have been removed or hasn't been analysed yet.</p>
      </main>
    )
  }
  return <ContractDetail contract={contract} />
}
