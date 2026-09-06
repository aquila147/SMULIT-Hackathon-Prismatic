import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AnalysisQuality } from './analysis-quality'
import { FieldCard } from './field-card'
import { SourceViewer } from './source-viewer'
import { LegalHandoff } from './legal-handoff'
import type { Contract, ExtractedField } from '@/lib/types'

export function ContractDetail({ contract }: { contract: Contract }) {
  const [activeField, setActiveField] = useState<ExtractedField | null>(null)

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <Link to="/contracts" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="size-4" /> Back to Contract Library
      </Link>
      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{contract.name}</h1>
          <p className="mt-1 text-muted-foreground">{contract.parties}</p>
          {contract.startDate && contract.endDate && (
            <p className="mt-0.5 text-sm text-muted-foreground">{contract.startDate} → {contract.endDate}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => window.open(`/api/contracts/${contract.id}/pdf`, '_blank')}>
            <Download className="size-4" /> View Original
          </Button>
        </div>
      </div>
      <div className="mt-6"><AnalysisQuality contract={contract} /></div>
      <section className="mt-8">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">Extracted Terms</h2>
        <p className="text-sm text-muted-foreground">
          Each finding shows what was found, how confident the analysis is, and exactly where it came from.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          {contract.fields.map(field => (
            <FieldCard key={field.id} field={field} onViewSource={setActiveField} />
          ))}
        </div>
      </section>
      <div className="mt-8"><LegalHandoff contract={contract} /></div>
      {activeField && (
        <SourceViewer contract={contract} field={activeField} onClose={() => setActiveField(null)} />
      )}
    </main>
  )
}
