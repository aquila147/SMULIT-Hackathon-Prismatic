import { useState, useRef } from 'react'
import { Download, FileSearch, Scale, LoaderCircle, X, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getHandoff } from '@/lib/api'
import type { Contract, BackendHandoff } from '@/lib/types'

export function LegalHandoff({ contract }: { contract: Contract }) {
  const [handoff, setHandoff] = useState<BackendHandoff | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [showClauses, setShowClauses] = useState(false)
  const clausesRef = useRef<HTMLDivElement>(null)

  async function handleGenerate() {
    setOpen(true)
    setLoading(true)
    try {
      const data = await getHandoff(contract.id)
      setHandoff(data)
    } catch (err) {
      console.error('Failed to fetch handoff:', err)
    } finally {
      setLoading(false)
    }
  }

  function handleViewClauses() {
    setShowClauses(true)
    // Scroll to the clauses section after a small render delay
    setTimeout(() => {
      clausesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
  }

  function handleExportHandoff() {
    if (!handoff) return

    const lines: string[] = [
      '═══════════════════════════════════════════════════════',
      'AITHENA — Legal Handoff Brief',
      '═══════════════════════════════════════════════════════',
      '',
      `Title: ${handoff.title}`,
      `Generated: ${new Date().toLocaleString('en-SG', { dateStyle: 'long', timeStyle: 'short' })}`,
      '',
      '───────────────────────────────────────────────────────',
      'ISSUE SUMMARY',
      '───────────────────────────────────────────────────────',
      handoff.issue_summary,
      '',
      '───────────────────────────────────────────────────────',
      'RELEVANT DOCUMENTS',
      '───────────────────────────────────────────────────────',
      ...handoff.relevant_documents.map(d => `  • ${d}`),
      '',
      '───────────────────────────────────────────────────────',
      'WHAT THE TOOL ESTABLISHED',
      '───────────────────────────────────────────────────────',
      handoff.what_the_tool_established,
      '',
      '───────────────────────────────────────────────────────',
      'QUESTION FOR LEGAL REVIEW',
      '───────────────────────────────────────────────────────',
      handoff.specific_question_for_lawyer,
      '',
    ]

    if (handoff.relevant_clauses.length > 0) {
      lines.push(
        '───────────────────────────────────────────────────────',
        'SUPPORTING CLAUSES',
        '───────────────────────────────────────────────────────',
      )
      handoff.relevant_clauses.forEach((c, i) => {
        lines.push(
          '',
          `[${i + 1}] ${c.filename} — Page ${c.page + 1} — ${c.field_name}`,
          c.quote ? `    "${c.quote}"` : '    (no verbatim quote available)',
        )
      })
      lines.push('')
    }

    if (handoff.contested_or_ungrounded_fields.length > 0) {
      lines.push(
        '───────────────────────────────────────────────────────',
        'CONTESTED / UNGROUNDED FIELDS',
        '───────────────────────────────────────────────────────',
      )
      handoff.contested_or_ungrounded_fields.forEach(f => {
        lines.push(`  • ${f.field_name}: ${f.value || 'Not identified'} [${f.confidence}]`)
      })
      lines.push('')
    }

    lines.push(
      '═══════════════════════════════════════════════════════',
      'End of Handoff Brief — AITHENA Contract Analyser',
      '═══════════════════════════════════════════════════════',
    )

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aithena_handoff_${contract.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9]+/g, '_')}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <Scale className="size-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Generate Legal Handoff</h2>
            <p className="text-sm text-muted-foreground">Produce a concise, evidence-backed summary to send to a lawyer.</p>
          </div>
        </div>
        {!open && (
          <Button size="lg" className="h-10 shrink-0" onClick={handleGenerate}>Generate Legal Handoff</Button>
        )}
      </div>

      {open && (
        <div className="mt-6 rounded-xl border border-border bg-muted/40 p-5">
          {loading ? (
            <div className="flex items-center gap-3 py-8 justify-center text-muted-foreground">
              <LoaderCircle className="size-5 animate-spin" />
              <span className="text-sm">Generating handoff brief...</span>
            </div>
          ) : handoff ? (
            <>
              <div className="grid gap-5 sm:grid-cols-2">
                <HandoffField label="Issue">{handoff.issue_summary}</HandoffField>
                <HandoffField label="Documents">
                  <ul className="space-y-1">{handoff.relevant_documents.map((d, i) => <li key={i}>{d}</li>)}</ul>
                </HandoffField>
                <HandoffField label="What the tool established" className="sm:col-span-2">
                  {handoff.what_the_tool_established}
                </HandoffField>
                <HandoffField label="Question for legal review" className="sm:col-span-2">
                  {handoff.specific_question_for_lawyer}
                </HandoffField>
              </div>

              {/* Supporting clauses panel — shown on demand */}
              {showClauses && handoff.relevant_clauses.length > 0 && (
                <div ref={clausesRef} className="mt-5 border-t border-border pt-5">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Supporting Clauses</p>
                    <button type="button" onClick={() => setShowClauses(false)} className="flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="Close clauses">
                      <X className="size-4" />
                    </button>
                  </div>
                  <ul className="space-y-2">
                    {handoff.relevant_clauses.map((c, i) => (
                      <li key={i} className="rounded-lg border border-border bg-card p-4 shadow-sm">
                        <div className="flex items-center gap-2 text-sm">
                          <FileText className="size-4 text-primary shrink-0" />
                          <span className="font-medium text-foreground">{c.filename}</span>
                          <span className="text-muted-foreground">·</span>
                          <span className="text-muted-foreground">Page {c.page + 1}</span>
                          <span className="text-muted-foreground">·</span>
                          <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">{c.field_name.replace(/_/g, ' ')}</span>
                        </div>
                        {c.quote && (
                          <div className="mt-2 rounded-md bg-warning-muted p-3 ring-1 ring-warning/30">
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-warning-foreground">Verbatim Quote</p>
                            <p className="text-sm italic text-foreground leading-relaxed">"{c.quote}"</p>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-5 flex flex-wrap gap-2 border-t border-border pt-4">
                {handoff.relevant_clauses.length > 0 && (
                  <Button variant="outline" onClick={handleViewClauses}>
                    <FileSearch className="size-4" /> {showClauses ? 'Clauses shown above' : 'View Supporting Clauses'}
                  </Button>
                )}
                <Button onClick={handleExportHandoff}>
                  <Download className="size-4" /> Export Handoff
                </Button>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No handoff brief available. This contract may not have contested or ungrounded fields requiring escalation.
            </p>
          )}
        </div>
      )}
    </section>
  )
}

function HandoffField({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-1.5 text-sm text-foreground">{children}</div>
    </div>
  )
}
