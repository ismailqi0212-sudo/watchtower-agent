import type { ReactNode } from 'react'
import { SearchX } from 'lucide-react'

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center gap-2 px-6 text-center">
      <span className="mb-1 flex size-10 items-center justify-center rounded-full border border-border text-muted">
        <SearchX size={17} strokeWidth={1.4} />
      </span>
      <p className="text-[13px] text-foreground">{title}</p>
      {description ? <p className="max-w-sm text-[11px] leading-5 text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}
