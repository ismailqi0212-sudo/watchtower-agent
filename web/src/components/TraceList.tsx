import { Chip } from '@heroui/react'
import { CircleCheck, CircleX, Sparkles, TriangleAlert, Wrench } from 'lucide-react'
import type { TraceStep } from '../types'
import { formatLatency } from '../lib/format'

const TOOL_LABELS: Record<string, string> = {
  get_quote: '行情',
  get_history: '日线',
  compute_indicators: '指标',
  search_news: '资讯',
  get_fundamentals: '基本面',
  get_benchmark: '基准',
}

function StepIcon({ step }: { step: TraceStep }) {
  if (step.kind === 'plan') return <Sparkles size={12} strokeWidth={1.5} />
  if (step.kind === 'warning') return <TriangleAlert size={12} strokeWidth={1.5} />
  if (step.kind === 'final') return <CircleCheck size={12} strokeWidth={1.5} />
  if (!step.ok) return <CircleX size={12} strokeWidth={1.5} />
  return <Wrench size={12} strokeWidth={1.5} />
}

export function TraceList({ steps }: { steps: TraceStep[] }) {
  if (!steps.length) return <p className="text-[11px] text-muted">暂无执行记录。</p>
  return (
    <div className="divide-y divide-border/60">
      {steps.map((step) => {
        const ids = Array.isArray(step.result?.evidence_ids)
          ? (step.result.evidence_ids as string[])
          : []
        return (
          <details key={`${step.id}-${step.step}`} className="group py-2.5">
            <summary className="flex cursor-pointer list-none items-center gap-2.5">
              <span
                className={`flex size-5 shrink-0 items-center justify-center rounded-full border ${
                  step.ok ? 'border-border text-muted' : 'border-[#4a2027] text-[var(--danger)]'
                }`}
              >
                <StepIcon step={step} />
              </span>
              <span className="w-12 shrink-0 text-[10px] text-foreground">
                {step.tool ? TOOL_LABELS[step.tool] ?? step.tool : step.kind}
              </span>
              <span className="min-w-0 flex-1 truncate text-[10px] text-muted">
                {step.summary || step.error || '—'}
              </span>
              {step.latency_ms ? (
                <Chip size="sm" variant="soft" className="h-4 px-1 text-[8px] text-muted">
                  {formatLatency(step.latency_ms)}
                </Chip>
              ) : null}
            </summary>
            <div className="ml-[30px] mt-2 space-y-2">
              {ids.length ? (
                <div className="flex flex-wrap gap-1">
                  {ids.map((id) => (
                    <span
                      key={id}
                      className="rounded border border-border px-1 py-0.5 text-[8px] text-muted"
                    >
                      {id}
                    </span>
                  ))}
                </div>
              ) : null}
              <pre className="max-h-44 overflow-auto rounded border border-border bg-[#080809] p-2 text-[8px] leading-4 text-[#8f8f94]">
                {JSON.stringify(step.result, null, 2)}
              </pre>
            </div>
          </details>
        )
      })}
    </div>
  )
}
