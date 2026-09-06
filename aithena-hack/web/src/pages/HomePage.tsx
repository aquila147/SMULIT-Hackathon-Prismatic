import { ShieldCheck } from 'lucide-react'
import { UploadAskPanel } from '@/components/upload-ask/upload-ask-panel'

export default function HomePage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16 lg:py-20">
      <div className="mb-8 text-center sm:mb-10">
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
          <ShieldCheck className="size-3.5 text-primary" />
          Evidence-grounded contract intelligence
        </span>
        <h1 className="mt-5 text-balance text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          Understand what you&apos;re on the hook for.
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">
          Upload your contracts and ask AITHENA about obligations, deadlines, renewals, risks, and conflicts.
        </p>
      </div>
      <UploadAskPanel />
    </main>
  )
}
