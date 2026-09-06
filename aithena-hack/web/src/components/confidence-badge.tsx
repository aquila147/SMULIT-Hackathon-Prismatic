import { Scale } from 'lucide-react'
import { cn } from '@/lib/utils'
import { confidenceMeta, type UIConfidence } from '@/lib/types'

export function ConfidenceBadge({ level, className }: { level: UIConfidence; className?: string }) {
  const meta = confidenceMeta[level]
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium', meta.bg, meta.border, meta.text, className)}>
      <span className={cn('size-1.5 rounded-full', meta.dot)} aria-hidden />
      {meta.label}
    </span>
  )
}

export function LegalReviewBadge({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground', className)}>
      <Scale className="size-3" aria-hidden />
      Legal review recommended
    </span>
  )
}
