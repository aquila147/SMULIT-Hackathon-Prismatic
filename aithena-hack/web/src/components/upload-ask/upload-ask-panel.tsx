import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, CircleCheck, Circle, FileText, LoaderCircle, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { uploadContracts } from '@/lib/api'

const ANALYSIS_STEPS = [
  'Uploading contracts...',
  'Extracting text from documents',
  'Processing scanned documents via OCR',
  'Running dual-extractor analysis...',
  'Verifying with span matching',
  'Checking upcoming renewals',
  'Detecting potential conflicts',
  'Building handoff briefs',
]

type StepState = 'done' | 'active' | 'todo'

export function UploadAskPanel() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [analysing, setAnalysing] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const hasFiles = files.length > 0

  function addFiles(newFiles: File[]) {
    const valid = newFiles.filter(f => {
      const ext = f.name.split('.').pop()?.toLowerCase()
      return ['pdf', 'docx', 'doc', 'pptx', 'ppt'].includes(ext || '')
    })
    if (valid.length < newFiles.length) {
      setError('Some files were skipped — only PDF, DOCX, and PPTX are supported.')
    }
    setFiles(prev => [...prev, ...valid])
  }

  function handleBrowseInput(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? [])
    if (selected.length) addFiles(selected)
    e.target.value = ''
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = Array.from(e.dataTransfer.files ?? [])
    if (dropped.length) addFiles(dropped)
  }

  function removeFile(index: number) {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  async function runAnalysis() {
    if (!hasFiles) return
    setAnalysing(true)
    setCurrentStep(0)
    setError(null)

    // Simulate step progression while the actual upload happens
    let step = 0
    const timer = setInterval(() => {
      step += 1
      if (step < ANALYSIS_STEPS.length - 1) {
        setCurrentStep(step)
      }
    }, 1200)

    try {
      await uploadContracts(files)
      clearInterval(timer)
      // Complete all steps
      setCurrentStep(ANALYSIS_STEPS.length)
      setTimeout(() => navigate('/report'), 800)
    } catch (err) {
      clearInterval(timer)
      setAnalysing(false)
      setError(err instanceof Error ? err.message : 'Upload failed. Please try again.')
    }
  }

  if (analysing) {
    return <AnalysisLoading currentStep={currentStep} fileCount={files.length} />
  }

  const displayFiles = files.slice(0, 5)
  const remaining = files.length - displayFiles.length

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger">
          {error}
          <button type="button" onClick={() => setError(null)} className="ml-2 font-medium underline">Dismiss</button>
        </div>
      )}
      <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
        <div className="p-5 sm:p-6">
          {!hasFiles ? (
            <button type="button" onClick={() => inputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              className={cn('flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors',
                dragging ? 'border-primary bg-accent' : 'border-border bg-muted/40 hover:border-primary/50 hover:bg-accent/50')}>
              <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Upload className="size-6" />
              </span>
              <span className="text-base font-semibold text-foreground">Drop your contract files here</span>
              <span className="text-sm text-muted-foreground">or click to browse</span>
              <span className="mt-1 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <span className="rounded-full border border-border bg-card px-2 py-0.5">PDF</span>
                <span className="rounded-full border border-border bg-card px-2 py-0.5">DOCX</span>
                <span className="rounded-full border border-border bg-card px-2 py-0.5">Scanned documents</span>
              </span>
              <span className="text-xs font-medium text-primary">Multiple files supported</span>
            </button>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Contracts</p>
                  <p className="text-sm font-semibold text-foreground">{files.length} files selected</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
                    <Upload className="size-3.5" /> Add more
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setFiles([])}>Clear</Button>
                </div>
              </div>
              <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                {displayFiles.map((file, i) => (
                  <li key={`${file.name}-${i}`} className="flex items-center gap-3 bg-card px-3 py-2.5">
                    <FileText className="size-4 shrink-0 text-primary" />
                    <span className="flex-1 truncate text-sm text-foreground">{file.name}</span>
                    <span className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(0)} KB</span>
                    <button type="button" onClick={() => removeFile(i)} className="flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-danger" aria-label={`Remove ${file.name}`}>
                      <X className="size-4" />
                    </button>
                  </li>
                ))}
                {remaining > 0 && (
                  <li className="bg-muted/40 px-3 py-2 text-center text-xs font-medium text-muted-foreground">+ {remaining} more</li>
                )}
              </ul>
              <div className="flex items-center gap-2 rounded-lg bg-success-muted px-3 py-2 text-xs font-medium text-success">
                <CircleCheck className="size-4" />
                {files.length} contracts ready for analysis
              </div>
            </div>
          )}
        </div>
      </div>
      <Button size="lg" disabled={!hasFiles} onClick={runAnalysis} className="h-11 w-full text-sm sm:w-auto">
        Analyse Contracts <ArrowRight className="size-4" />
      </Button>
      <input ref={inputRef} type="file" multiple accept=".pdf,.docx,.doc,.pptx,.ppt" onChange={handleBrowseInput} className="hidden" />
    </div>
  )
}

function AnalysisLoading({ currentStep, fileCount }: { currentStep: number; fileCount: number }) {
  const pct = Math.min(100, Math.round((currentStep / ANALYSIS_STEPS.length) * 100))
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
          <LoaderCircle className="size-5 animate-spin" />
        </span>
        <div>
          <h2 className="text-lg font-semibold text-foreground">Analysing your contracts...</h2>
          <p className="text-sm text-muted-foreground">Processing {fileCount} contracts. This may take a few minutes.</p>
        </div>
      </div>
      <div className="mt-6 h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
      </div>
      <ul className="mt-6 space-y-3">
        {ANALYSIS_STEPS.map((label, i) => {
          const state: StepState = i < currentStep ? 'done' : i === currentStep ? 'active' : 'todo'
          return (
            <li key={label} className="flex items-center gap-3 text-sm">
              {state === 'done' && <CircleCheck className="size-5 text-success" />}
              {state === 'active' && <LoaderCircle className="size-5 animate-spin text-primary" />}
              {state === 'todo' && <Circle className="size-5 text-muted-foreground/40" />}
              <span className={cn(state === 'done' && 'text-foreground', state === 'active' && 'font-medium text-foreground', state === 'todo' && 'text-muted-foreground')}>
                {label}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
