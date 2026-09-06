import { useState } from 'react'
import { MessageSquare, Send, LoaderCircle, AlertCircle, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { queryPortfolio } from '@/lib/api'

const SUGGESTIONS = [
  'What are we obligated to pay?',
  'What contracts renew in the next 90 days?',
  'Which contracts require action?',
  'Are there any potential conflicts?',
  'Which contracts cap our liability below S$50k?',
  'What are the termination rights across all contracts?',
  'Which contracts have exclusivity clauses?',
  'What is the governing law for each contract?',
]

interface QA {
  question: string
  answer: string
  isError: boolean
}

export default function AskPage() {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<QA[]>([])

  async function handleAsk(question?: string) {
    const q = (question || prompt).trim()
    if (!q || loading) return

    setPrompt('')
    setLoading(true)

    try {
      const result = await queryPortfolio(q)
      setHistory(prev => [...prev, { question: q, answer: result.answer, isError: result.isError }])
    } catch {
      setHistory(prev => [...prev, { question: q, answer: "Sorry, I can't reply to this question.", isError: true }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAsk()
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <div className="mb-2 flex items-center gap-2">
        <MessageSquare className="size-6 text-primary" />
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Ask AITHENA</h1>
      </div>
      <p className="mb-8 text-muted-foreground">
        Ask questions about your uploaded contracts. AITHENA will look through the extracted data and answer based on verified findings.
      </p>

      {/* Conversation history */}
      {history.length > 0 && (
        <div className="mb-6 space-y-4">
          {history.map((qa, i) => (
            <div key={i} className="space-y-3">
              {/* User question */}
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-3 text-sm text-primary-foreground">
                  {qa.question}
                </div>
              </div>
              {/* AI answer */}
              <div className="flex justify-start">
                <div className={cn(
                  'max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 text-sm',
                  qa.isError
                    ? 'border border-danger/30 bg-danger-muted text-danger'
                    : 'border border-border bg-card text-foreground shadow-sm'
                )}>
                  <div className="mb-1 flex items-center gap-1.5">
                    {qa.isError
                      ? <AlertCircle className="size-3.5" />
                      : <Sparkles className="size-3.5 text-primary" />
                    }
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">AITHENA</span>
                  </div>
                  <div className="whitespace-pre-wrap leading-relaxed">{qa.answer}</div>
                </div>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3 text-sm text-muted-foreground shadow-sm">
                <LoaderCircle className="size-4 animate-spin text-primary" />
                Analysing your contracts...
              </div>
            </div>
          )}
        </div>
      )}

      {/* Input area */}
      <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="p-5 sm:p-6">
          <div className="rounded-xl border border-border bg-background focus-within:border-primary focus-within:ring-3 focus-within:ring-ring/20">
            <textarea
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your contracts..."
              rows={3}
              disabled={loading}
              className="w-full resize-none bg-transparent px-3.5 py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-50"
            />
            <div className="flex items-center justify-between gap-3 px-3.5 pb-3">
              <p className="text-xs text-muted-foreground">
                Answers are based on extracted and verified contract data.
              </p>
              <button
                type="button"
                onClick={() => handleAsk()}
                disabled={!prompt.trim() || loading}
                className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
                aria-label="Send question"
              >
                {loading ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
              </button>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                type="button"
                onClick={() => handleAsk(s)}
                disabled={loading}
                className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
