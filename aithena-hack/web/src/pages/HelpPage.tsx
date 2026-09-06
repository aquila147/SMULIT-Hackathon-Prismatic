import { FileText, Scale, ShieldCheck, TriangleAlert } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const confidenceLevels = [
  { dot: 'bg-success', title: 'VERIFIED — High confidence', body: 'Both extractors agree, the verbatim quote matches the source via span matching, and the field passes schema checks. You can rely on this finding.' },
  { dot: 'bg-warning', title: 'INFERRED — Medium confidence', body: 'The finding is derived from a definition chain or computed date, or the extractors agree but the match score is below the verified threshold. A quick human check is recommended.' },
  { dot: 'bg-danger', title: 'CONTESTED or UNGROUNDED — Low confidence / Needs review', body: 'Either the extractors disagree (CONTESTED), or no verbatim span was found in the source (UNGROUNDED). AITHENA will not present this as fact — it routes to the handoff brief instead.' },
]
const principles = [
  { icon: ShieldCheck, title: 'Grounded in the source', body: 'Every extracted term links back to the exact page and clause. Confidence is assigned by code — span matching and cross-extractor agreement — never by model self-assessment.' },
  { icon: FileText, title: 'Portfolio vs. document view', body: 'The Dashboard shows what needs attention across all contracts. An individual contract page shows exactly what AITHENA found in that specific document, with clause-level citations.' },
  { icon: Scale, title: 'Not legal advice', body: 'AITHENA surfaces potential issues and organises information. It does not replace a lawyer. Use "Generate Legal Handoff" to brief a professional quickly.' },
  { icon: TriangleAlert, title: 'Uncertainty is visible', body: 'When evidence is ambiguous, AITHENA flags it for review instead of presenting a confident answer. A confidently wrong answer is worse than no answer — this is by design.' },
]

export default function HelpPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">How AITHENA works</h1>
      <p className="mt-1 text-muted-foreground">Understanding confidence levels, grounding, and the limits of automated contract analysis.</p>
      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Confidence levels</CardTitle>
          <p className="text-sm text-muted-foreground">Confidence is assigned per field by code, not by the model. Every field carries a tier based on span matching and cross-extractor agreement.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {confidenceLevels.map(level => (
            <div key={level.title} className="flex gap-3">
              <span className={cn('mt-1.5 size-2.5 shrink-0 rounded-full', level.dot)} aria-hidden />
              <div>
                <p className="text-sm font-semibold text-foreground">{level.title}</p>
                <p className="text-sm text-muted-foreground">{level.body}</p>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {principles.map(p => (
          <Card key={p.title} className="p-5">
            <span className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground"><p.icon className="size-4" /></span>
            <h3 className="mt-3 text-sm font-semibold text-foreground">{p.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{p.body}</p>
          </Card>
        ))}
      </div>
      <div className="mt-6 rounded-xl border border-border bg-muted/40 p-5 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">A note on trust</p>
        <p className="mt-1">
          AITHENA is designed for SME owners and teams, not lawyers. It never presents an uncertain interpretation as definitive legal advice. Findings are meant to help you ask better questions and act on deadlines with confidence. The handoff brief is a first-class deliverable — it's how AITHENA connects you to professional legal help.
        </p>
      </div>
    </main>
  )
}
