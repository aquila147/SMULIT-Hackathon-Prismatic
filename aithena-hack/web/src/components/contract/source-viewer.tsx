import { useEffect } from 'react'
import { FileText, X } from 'lucide-react'
import { ConfidenceBadge, LegalReviewBadge } from '@/components/confidence-badge'
import { getPageImageUrl } from '@/lib/api'
import type { Contract, ExtractedField } from '@/lib/types'

export function SourceViewer({ contract, field, onClose }: {
  contract: Contract
  field: ExtractedField
  onClose: () => void
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', handler); document.body.style.overflow = '' }
  }, [onClose])

  // For scanned documents or when we have the page image from the backend
  const pageImageUrl = field.page !== null ? getPageImageUrl(contract.id, field.page - 1) : null

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-foreground/40 backdrop-blur-sm sm:items-center sm:justify-center sm:p-6"
      role="dialog" aria-modal="true" aria-label={`Source evidence for ${field.label}`} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="flex h-full w-full flex-col overflow-hidden bg-card shadow-2xl sm:h-[85vh] sm:max-w-5xl sm:rounded-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-accent text-accent-foreground"><FileText className="size-4" /></span>
            <div>
              <p className="text-sm font-semibold text-foreground">Source Evidence</p>
              <p className="text-xs text-muted-foreground">{contract.name}</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="Close source viewer">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
          {/* LEFT: extracted finding */}
          <div className="border-b border-border p-5 lg:w-2/5 lg:border-b-0 lg:border-r lg:overflow-y-auto">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Extracted Finding</p>
            <h3 className="mt-2 text-lg font-semibold text-foreground">{field.label}</h3>
            <p className="mt-2 text-base font-medium text-foreground">{field.finding}</p>
            {field.secondary && <p className="mt-1 text-sm text-muted-foreground">{field.secondary}</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              <ConfidenceBadge level={field.confidence} />
              {field.legalReview && <LegalReviewBadge />}
            </div>
            {field.page && (
              <div className="mt-4 rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                Located at Page {field.page}
              </div>
            )}
            <p className="mt-4 text-xs text-muted-foreground">
              Every extracted assertion is grounded in the original contract. The verbatim quote from the source is shown on the right.
            </p>
          </div>
          {/* RIGHT: source quote or page image */}
          <div className="flex-1 overflow-y-auto bg-muted/40 p-5">
            <div className="mx-auto max-w-xl rounded-lg border border-border bg-card p-8 shadow-sm">
              <div className="mb-6 flex items-center justify-between border-b border-border pb-3 text-xs text-muted-foreground">
                <span className="font-medium uppercase tracking-wide">{contract.name}</span>
                {field.page && <span>Page {field.page}</span>}
              </div>
              {field.clauseText ? (
                <div className="space-y-3 text-sm leading-relaxed text-muted-foreground">
                  <div className="rounded-md bg-warning-muted p-3 ring-2 ring-warning/50">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-warning-foreground">Verbatim Quote</p>
                    <p className="text-foreground">{field.clauseText}</p>
                  </div>
                </div>
              ) : contract.isScanned && pageImageUrl ? (
                <div>
                  <img src={pageImageUrl} alt={`Page ${field.page} of ${contract.name}`} className="w-full rounded" />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground italic">No source text available for this field.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
