import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { label: 'Dashboard', href: '/report' },
  { label: 'Contracts', href: '/contracts' },
  { label: 'Calendar', href: '/calendar' },
  { label: 'Risks & Conflicts', href: '/risks' },
  { label: 'Ask', href: '/ask' },
  { label: 'Help', href: '/help' },
]

export function SiteHeader() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  const isActive = (href: string) =>
    href === '/report' ? pathname === '/report' : pathname.startsWith(href)

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-2.5">
            <span aria-hidden className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <svg viewBox="0 0 24 24" className="size-4" fill="none">
                <path d="M12 3 3 18h18L12 3Z" fill="currentColor" fillOpacity="0.9" />
                <path d="M12 3v15M12 18 3 18" stroke="var(--primary)" strokeWidth="1.2" />
              </svg>
            </span>
            <span className="text-lg font-semibold tracking-tight">AITHENA</span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {navItems.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                className={cn(
                  'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive(item.href)
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setOpen(v => !v)} className="flex size-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground md:hidden" aria-label="Toggle navigation menu">
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>
      {open && (
        <div className="border-t border-border bg-background md:hidden">
          <nav className="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-3 sm:px-6">
            {navItems.map((item) => (
              <Link key={item.href} to={item.href} onClick={() => setOpen(false)}
                className={cn('rounded-md px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive(item.href) ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}>
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </header>
  )
}
