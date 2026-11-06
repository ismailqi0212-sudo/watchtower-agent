import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Alert, Button, Chip, Spinner } from '@heroui/react'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Library,
  MessageSquare,
  Plus,
  Search,
  Send,
  Table2,
  X,
  NotebookText,
  Upload,
} from 'lucide-react'
import { api } from '../lib/api'
import { useWorkspace } from '../lib/workspace'
import { MetricChart } from '../components/MetricChart'
import type {
  ResearchCitation,
  ResearchMessage,
  ResearchCandidateGroup,
  ResearchMetric,
  ResearchReport,
  ResearchReportVersion,
  ResearchSession,
  ResearchSessionSummary,
  ResearchSnippet,
} from '../types'

type SelectedCell = {
  documentId: string
  page: number
  quote: string
  label: string
  period: string
  metricKey?: string
}

function formatCell(value: number | null, unit: string) {
  if (value === null) return '—'
  if (unit === '%') return `${value.toFixed(1)}%`
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
  }
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function downloadCsv(session: ResearchSession) {
  const rows = [
    ['指标', '单位', ...session.periods],
    ...session.metrics.map((metric) => [
      metric.label,
      metric.unit,
      ...session.periods.map((period) => {
        const cell = metric.cells[period]
        return cell?.value === null || cell?.value === undefined ? '' : cell.value
      }),
    ]),
  ]
  const csv = rows
    .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(','))
    .join('\r\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${session.name}-${session.symbol}-经营数据.csv`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function MetricTable({
  metrics,
  periods,
  selected,
  onCell,
  compact = false,
}: {
  metrics: ResearchMetric[]
  periods: string[]
  selected: SelectedCell | null
  onCell: (metric: ResearchMetric, period: string) => void
  compact?: boolean
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-border/60">
      <table className={`w-full border-collapse text-left ${compact ? 'min-w-[500px]' : 'min-w-[560px]'}`}>
        <thead>
          <tr className="border-b border-border/60">
            <th className="px-3 py-2 text-[9px] font-normal tracking-[0.1em] text-muted">指标</th>
            <th className="w-[48px] px-2 py-2 text-[9px] font-normal text-muted">单位</th>
            {periods.map((period) => (
              <th key={period} className="w-[72px] px-2 py-2 text-right text-[9px] font-normal text-muted">
                {period}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => (
            <tr key={metric.key} className="border-b border-border/40 last:border-0 hover:bg-[#101012]">
              <td className="px-3 py-2 text-[10px] text-[#d6d6da]">{metric.label}</td>
              <td className="px-2 py-2 text-[9px] text-muted">{metric.unit}</td>
              {periods.map((period) => {
                const cell = metric.cells[period]
                const missing = cell?.value === null || cell?.value === undefined
                const active = selected?.metricKey === metric.key && selected?.period === period
                return (
                  <td key={period} className="px-1 py-1 text-right">
                    <button
                      type="button"
                      disabled={missing}
                      onClick={() => onCell(metric, period)}
                      className={`num w-full rounded px-1.5 py-1 text-[10px] transition-colors ${
                        missing
                          ? 'cursor-default text-[#4f4f54]'
                          : active
                            ? 'bg-[#1d1d20] text-foreground'
                            : 'text-[#d6d6da] hover:bg-[#18181a] hover:text-foreground'
                      }`}
                    >
                      {formatCell(cell?.value ?? null, metric.unit)}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SourceViewer({
  session,
  selected,
  citation,
  citationList,
  onPickCitation,
  onPage,
  onClearCitation,
}: {
  session: ResearchSession
  selected: SelectedCell | null
  citation: ResearchCitation | null
  citationList: ResearchCitation[] | null
  onPickCitation: (citation: ResearchCitation) => void
  onPage: (page: number) => void
  onClearCitation: () => void
}) {
  if (citationList) {
    return (
      <aside className="hidden w-[320px] shrink-0 flex-col border-l border-border/60 xl:flex">
        <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
          <div>
            <p className="text-[9px] tracking-[0.12em] text-muted">数据来源</p>
            <p className="mt-1 text-[11px] text-foreground">{citationList.length} 条</p>
          </div>
          <button type="button" onClick={() => onClearCitation()} className="text-[9px] text-muted hover:text-foreground">
            关闭
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
          {citationList.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onPickCitation(item)}
              className="flex w-full items-start gap-2 rounded-md border border-transparent px-2.5 py-2 text-left hover:border-border/60 hover:bg-[#101012]"
            >
              <span className="mt-0.5 rounded border border-border/60 px-1 py-0.5 text-[7px] uppercase text-muted">
                {item.kind || 'data'}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[9px] text-[#d6d6da]">{item.label}</span>
                <span className="mt-0.5 line-clamp-2 block text-[8px] leading-4 text-muted">{item.summary}</span>
              </span>
            </button>
          ))}
        </div>
      </aside>
    )
  }

  if (citation) {
    const payload = citation.payload || {}
    const sourceUrl = [payload.source_url, payload.url].find(
      (value) => typeof value === 'string' && /^https?:\/\//i.test(value),
    ) as string | undefined
    const sourceName = [payload.source_name, payload.source].find(
      (value) => typeof value === 'string' && value.trim(),
    ) as string | undefined
    return (
      <aside className="hidden w-[320px] shrink-0 flex-col border-l border-border/60 xl:flex">
        <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
          <div>
            <p className="text-[9px] tracking-[0.12em] text-muted">数据来源</p>
            <p className="mt-1 text-[11px] text-foreground">{citation.label}</p>
          </div>
          <button type="button" onClick={onClearCitation} className="text-muted hover:text-foreground">
            ×
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <p className="text-[9px] uppercase tracking-[0.12em] text-muted">{citation.kind}</p>
          <p className="mt-2 text-[11px] leading-5 text-[#d6d6da]">{citation.summary || citation.label}</p>
          <p className="mt-3 text-[9px] text-muted">时间：{citation.as_of || '—'}</p>
          {sourceName && !sourceUrl ? (
            <p className="mt-2 text-[9px] text-muted">数据源：{sourceName}</p>
          ) : null}
          {sourceUrl ? (
            <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-3 block text-[9px] text-[#9db9ff] hover:underline">
              打开数据源
            </a>
          ) : null}
          <div className="mt-4 rounded border border-border/60 bg-[#0b0b0c] p-2">
            <p className="text-[8px] text-muted">原始字段</p>
            <pre className="mt-1 whitespace-pre-wrap break-all text-[8px] leading-4 text-[#9a9aa0]">
              {JSON.stringify(payload, null, 2).slice(0, 1600)}
            </pre>
          </div>
          <p className="mt-3 text-[8px] leading-4 text-muted">
            这是在线数据来源，没有 PDF 物理页。PDF 材料才会显示侧边原文阅读器。
          </p>
        </div>
      </aside>
    )
  }

  const source = session.sources.find((item) => item.id === selected?.documentId)
  if (!selected || !source) {
    return (
      <aside className="hidden w-[320px] shrink-0 flex-col border-l border-border/60 xl:flex">
        <div className="flex h-full flex-col items-center justify-center px-6 text-center">
          <FileText size={18} strokeWidth={1.2} className="text-muted" />
          <p className="mt-3 text-[11px] leading-5 text-muted">
            {session.sources.length
              ? '点击对话中的引用，查看数据来源或 PDF 原文页。'
              : '点击对话中的引用，在这里查看在线数据来源。'}
          </p>
        </div>
      </aside>
    )
  }

  const pageCount = source.page_count || 0
  return (
    <aside className="hidden w-[320px] shrink-0 flex-col border-l border-border/60 xl:flex">
      <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
        <div className="min-w-0">
          <p className="text-[9px] tracking-[0.12em] text-muted">原文与依据</p>
          <p className="mt-1 truncate text-[11px] text-foreground">{source.name}</p>
        </div>
        <a
          href={source.file_url}
          target="_blank"
          rel="noreferrer"
          className="text-[9px] text-muted transition-colors hover:text-foreground"
        >
          打开 PDF
        </a>
      </div>

      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2">
        <button
          type="button"
          disabled={selected.page <= 1}
          onClick={() => onPage(selected.page - 1)}
          className="flex items-center gap-1 text-[10px] text-muted transition-colors hover:text-foreground disabled:opacity-30"
        >
          <ChevronLeft size={12} /> 上一页
        </button>
        <span className="num text-[9px] text-muted">
          {selected.page} / {pageCount}
        </span>
        <button
          type="button"
          disabled={selected.page >= pageCount}
          onClick={() => onPage(selected.page + 1)}
          className="flex items-center gap-1 text-[10px] text-muted transition-colors hover:text-foreground disabled:opacity-30"
        >
          下一页 <ChevronRight size={12} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-[#151517] p-3">
        <div className="overflow-hidden rounded-sm bg-white shadow-[0_8px_30px_rgba(0,0,0,0.35)]">
          <img
            key={`${source.id}-${selected.page}`}
            src={`/api/documents/${source.id}/pages/${selected.page}.png`}
            alt={`${source.name} 第 ${selected.page} 页`}
            className="block h-auto w-full"
          />
        </div>
      </div>

      <div className="border-t border-border/60 p-4">
        <p className="text-[9px] tracking-[0.12em] text-muted">
          {selected.label}
          {selected.period ? ` · ${selected.period}` : ''}
        </p>
        <p className="mt-2 line-clamp-5 text-[10px] leading-5 text-[#c5c5ca]">
          {selected.quote || '该页未返回可引用原文。'}
        </p>
      </div>
    </aside>
  )
}

function ArtifactTable({
  session,
  metricKeys,
  onCell,
}: {
  session: ResearchSession
  metricKeys?: string[]
  onCell: (metric: ResearchMetric, period: string) => void
}) {
  const metrics = metricKeys?.length
    ? session.metrics.filter((metric) => metricKeys.includes(metric.key) && metric.available > 0)
    : session.metrics.slice(0, 5)
  if (!metrics.length) return null
  return (
    <div className="mt-3">
      <MetricTable metrics={metrics} periods={session.periods} selected={null} onCell={onCell} compact />
    </div>
  )
}

function CitationText({
  text,
  citations,
  onCitation,
}: {
  text: string
  citations: ResearchCitation[]
  onCitation: (citation: ResearchCitation) => void
}) {
  const parts = text.split(/(\[\[\d+\]\])/g)
  return (
    <>
      {parts.map((part, index) => {
        const match = part.match(/^\[\[(\d+)\]\]$/)
        if (!match) return <span key={index}>{part}</span>
        const citation = citations[Number(match[1]) - 1]
        if (!citation) return <span key={index}>{part}</span>
        return (
          <button
            key={index}
            type="button"
            onClick={() => onCitation(citation)}
            className="mx-0.5 inline-flex items-center rounded border border-border/60 px-1 align-baseline text-[8px] text-muted hover:text-foreground"
            title={citation.label}
          >
            [{match[1]}]
          </button>
        )
      })}
    </>
  )
}

function MarketSnapshot({ citations, onAdd, onCitation }: { citations: ResearchCitation[]; onAdd: (body: string) => void; onCitation: (citation: ResearchCitation) => void }) {
  const quote = citations.find((item) => item.kind === 'quote')
  const indicator = citations.find((item) => item.kind === 'indicator')
  const fundamental = citations.find((item) => item.kind === 'fundamental')
  const q = (quote?.payload || {}) as Record<string, any>
  const ind = ((indicator?.payload?.snapshot || indicator?.payload || {}) as Record<string, any>)
  const fp = ((fundamental?.payload?.data || fundamental?.payload || {}) as Record<string, any>)
  const items = ([ 
    ['收盘', q.price ? Number(q.price).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : null, q.change_pct != null ? `${Number(q.change_pct) >= 0 ? '+' : ''}${Number(q.change_pct).toFixed(2)}%` : '', quote],
    ['MA20', ind.ma20 ? Number(ind.ma20).toFixed(2) : null, '技术指标', indicator],
    ['RSI14', ind.rsi14 != null ? Number(ind.rsi14).toFixed(1) : null, '技术指标', indicator],
    ['PE', fp.pe != null ? Number(fp.pe).toFixed(2) : null, '基本面', fundamental],
    ['PB', fp.pb != null ? Number(fp.pb).toFixed(2) : null, '基本面', fundamental],
  ] as [string, string | null, string, ResearchCitation | undefined][]).filter((item) => item[1] !== null)
  if (!items.length) return null
  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[8px] tracking-[0.1em] text-muted">市场快照</span>
        <button
          type="button"
          onClick={() => onAdd(items.map(([label, value, hint]) => `${label} ${value}${hint ? `（${hint}）` : ''}`).join('；'))}
          className="rounded border border-border/60 px-1.5 py-0.5 text-[8px] text-muted hover:text-foreground"
        >
          加入研报
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {items.map(([label, value, hint, source]) => (
          <button
            key={String(label)}
            type="button"
            onClick={() => source && onCitation(source)}
            className="rounded border border-border/60 bg-[#0b0b0c] px-2.5 py-2 text-left transition-colors hover:border-[#3a3a3e]"
          >
            <p className="text-[8px] text-muted">{label}</p>
            <p className="num mt-1 text-[12px] text-[#e4e4e8]">{value}</p>
            <p className="mt-0.5 text-[7px] text-[#5f5f64]">{hint}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

function ChatMessage({
  message,
  session,
  onSelectText,
  onAddMetric,
  onAddMarket,
  onShowSources,
  onCitation,
  onCell,
}: {
  message: ResearchMessage
  session: ResearchSession
  onSelectText: (text: string, citations: ResearchCitation[], rect: { x: number; y: number }) => void
  onAddMetric: (title: string, keys: string[], citations: ResearchCitation[]) => void
  onAddMarket: (body: string, citations: ResearchCitation[]) => void
  onShowSources: (citations: ResearchCitation[]) => void
  onCitation: (citation: ResearchCitation) => void
  onCell: (metric: ResearchMetric, period: string) => void
}) {
  const isUser = message.role === 'user'
  const data = message.data || {}
  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : ''}`}>
      {!isUser ? (
        <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-[#111112] text-[9px] text-muted">
          研
        </span>
      ) : null}
      <div className={`max-w-[86%] ${isUser ? 'text-right' : ''}`}>
        <div className="mb-1 flex items-center gap-2 text-[9px] tracking-[0.1em] text-muted">
          <span>{isUser ? '你' : 'Research Agent'}</span>
          {!isUser && data.citations?.length ? (
            <button type="button" onClick={() => onShowSources(data.citations || [])} className="text-[8px] text-muted hover:text-foreground">
              来源 {data.citations.length}
            </button>
          ) : null}
        </div>
        <div
          onMouseUp={(event) => {
            if (isUser) return
            const selection = window.getSelection()
            const text = selection?.toString().trim() || ''
            if (!text || !selection || selection.rangeCount === 0) return
            const rect = selection.getRangeAt(0).getBoundingClientRect()
            onSelectText(text, data.citations || [], {
              x: Math.min(rect.left + rect.width / 2, window.innerWidth - 90),
              y: Math.max(rect.top - 34, 8),
            })
          }}
          className={`whitespace-pre-wrap rounded-md px-3 py-2 text-[11px] leading-5 ${
            isUser
              ? 'bg-[#1a1a1c] text-[#ececef]'
              : 'border border-border/60 bg-[#0c0c0d] text-[#d6d6da]'
          }`}
        >
          <CitationText
            text={message.content}
            citations={data.citations || []}
            onCitation={onCitation}
          />
        </div>

        {!isUser ? (
          <MarketSnapshot
            citations={data.citations || []}
            onAdd={(body) => onAddMarket(body, data.citations || [])}
            onCitation={onCitation}
          />
        ) : null}

        {!isUser && data.gaps?.length ? (
          <div className="mt-2 space-y-1">
            {data.gaps.map((gap) => (
              <p key={gap} className="text-[9px] leading-4 text-[var(--warning)]">
                待核实：{gap}
              </p>
            ))}
          </div>
        ) : null}

        {!isUser && data.artifacts?.length
          ? data.artifacts.map((artifact) => {
              const valid =
                artifact.kind !== 'metric_table' ||
                (artifact.metric_keys || []).some((key) =>
                  session.metrics.some((metric) => metric.key === key && metric.available > 0),
                )
              if (!valid) return null
              return (
              <div key={`${artifact.kind}-${artifact.title}`} className="mt-3">
                <div className="flex items-center justify-between gap-2 text-[9px] text-muted">
                  <span className="flex items-center gap-1.5">
                    <Table2 size={11} strokeWidth={1.5} />
                    {artifact.title}
                  </span>
                  {artifact.kind === 'metric_table' && artifact.metric_keys?.length ? (
                    <button
                      type="button"
                      onClick={() => onAddMetric(artifact.title, artifact.metric_keys || [], data.citations || [])}
                      className="rounded border border-border/60 px-1.5 py-0.5 text-[8px] text-muted hover:text-foreground"
                    >
                      加入研报
                    </button>
                  ) : null}
                </div>
                {artifact.kind === 'metric_table' ? (
                  <ArtifactTable session={session} metricKeys={artifact.metric_keys} onCell={onCell} />
                ) : null}
              </div>
              )
            })
          : null}
      </div>
    </div>
  )
}

function CandidatePanel({
  groups,
  selected,
  expanded,
  confirming,
  onToggle,
  onToggleGroup,
  onExpand,
  onConfirm,
}: {
  groups: ResearchCandidateGroup[]
  selected: Set<string>
  expanded: boolean
  confirming: boolean
  onToggle: (id: string) => void
  onToggleGroup: (group: ResearchCandidateGroup) => void
  onExpand: () => void
  onConfirm: () => void
}) {
  const visible = expanded ? groups : groups.slice(0, 6)
  return (
    <div className="mb-5 rounded-md border border-[#3a3220] bg-[#12100b]">
      <div className="flex items-center justify-between border-b border-[#2d281b] px-3 py-2.5">
        <div>
          <p className="text-[10px] text-[var(--warning)]">待确认指标</p>
          <p className="mt-1 text-[9px] text-muted">
            从年报表格识别，确认后才会写入底稿；不会自动覆盖已有数据。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="num text-[9px] text-muted">已选 {selected.size}</span>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirming || selected.size === 0}
            className="rounded bg-foreground px-2.5 py-1 text-[9px] text-background disabled:opacity-30"
          >
            {confirming ? '写入中' : '加入底稿'}
          </button>
        </div>
      </div>
      <div className="divide-y divide-[#282317]">
        {visible.map((group) => {
          const ids = Object.values(group.cells).map((cell) => cell.candidate_id)
          const all = ids.length > 0 && ids.every((id) => selected.has(id))
          return (
            <label key={group.metric_key} className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-[#16130d]">
              <input
                type="checkbox"
                checked={all}
                onChange={() => onToggleGroup(group)}
                className="size-3 accent-[var(--warning)]"
              />
              <span className="w-[150px] shrink-0 truncate text-[10px] text-[#d6d6da]">{group.label}</span>
              <span className="w-[52px] shrink-0 text-[9px] text-muted">{group.unit}</span>
              <span className="flex flex-1 flex-wrap gap-x-3 gap-y-1">
                {Object.entries(group.cells)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([period, cell]) => (
                    <span key={period} className="num text-[9px] text-[#a9a9ae]">
                      {period} <span className="text-[#e4e4e8]">{formatCell(cell.value, group.unit)}</span>
                    </span>
                  ))}
              </span>
              <span className="text-[8px] text-muted">p{Object.values(group.cells)[0]?.page}</span>
            </label>
          )
        })}
      </div>
      {groups.length > 6 ? (
        <div className="border-t border-[#2d281b] px-3 py-1.5">
          <button type="button" onClick={onExpand} className="text-[9px] text-muted hover:text-foreground">
            {expanded ? '收起' : `展开全部 ${groups.length} 组`}
          </button>
        </div>
      ) : null}
    </div>
  )
}

function ReportView({
  session,
  report,
  title,
  template,
  snippets,
  generating,
  onTitle,
  onTemplate,
  onRemoveSnippet,
  onGenerate,
  onExport,
  onReset,
  onShowSources,
  onCitation,
  onReportChange,
}: {
  session: ResearchSession
  report: ResearchReport | null
  title: string
  template: 'brief' | 'full'
  snippets: ResearchSnippet[]
  generating: boolean
  onTitle: (value: string) => void
  onTemplate: (value: 'brief' | 'full') => void
  onRemoveSnippet: (id: string) => void
  onGenerate: () => void
  onExport: () => void
  onReset: () => void
  onShowSources: (citations: ResearchCitation[]) => void
  onCitation: (citation: ResearchCitation) => void
  onReportChange: (report: ResearchReport) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(report?.title ?? '')
  const [draftSections, setDraftSections] = useState<ResearchReport['sections']>(report?.sections ?? [])
  const [versions, setVersions] = useState<ResearchReportVersion[]>([])
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    setDraftTitle(report?.title ?? '')
    setDraftSections(report?.sections ?? [])
    setEditing(false)
    setActionError('')
    if (report) {
      api
        .listResearchReportVersions(report.id)
        .then((data) => setVersions(data.items))
        .catch(() => setVersions([]))
    } else {
      setVersions([])
    }
  }, [report?.id, report?.version])

  const refreshVersions = async (reportId: string) => {
    const data = await api.listResearchReportVersions(reportId)
    setVersions(data.items)
  }

  const saveEdits = async () => {
    if (!report) return
    setBusy('save')
    setActionError('')
    try {
      const updated = await api.updateResearchReport(report.id, {
        title: draftTitle,
        sections: draftSections,
        note: '人工编辑',
      })
      onReportChange(updated)
      setEditing(false)
      await refreshVersions(report.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBusy('')
    }
  }

  const polish = async () => {
    if (!report) return
    setBusy('polish')
    setActionError('')
    try {
      const updated = await api.polishResearchReport(report.id)
      onReportChange(updated)
      await refreshVersions(report.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '润色失败')
    } finally {
      setBusy('')
    }
  }

  const restoreVersion = async (version: number) => {
    if (!report) return
    setBusy(`restore-${version}`)
    setActionError('')
    try {
      const updated = await api.restoreResearchReportVersion(report.id, version)
      onReportChange(updated)
      await refreshVersions(report.id)
      setVersionsOpen(false)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '恢复失败')
    } finally {
      setBusy('')
    }
  }

  const updateDraftSection = (index: number, patch: Partial<ResearchReport['sections'][number]>) => {
    setDraftSections((prev) => prev.map((section, item) => (item === index ? { ...section, ...patch } : section)))
  }

  if (!report) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-[820px]">
          <h2 className="text-[15px] font-normal">编成研报</h2>
          <p className="mt-1 text-[10px] leading-5 text-muted">
            选择要写进报告的片段。报告只使用你选中的内容，不重新查询数据。
          </p>

          <label className="mt-5 block text-[9px] tracking-[0.1em] text-muted">
            标题
            <input
              value={title}
              onChange={(event) => onTitle(event.target.value)}
              className="mt-1.5 h-8 w-full rounded-md border border-border bg-[#0b0b0c] px-3 text-[11px] text-foreground outline-none"
            />
          </label>

          <div className="mt-4 flex items-center gap-2">
            <span className="text-[9px] tracking-[0.1em] text-muted">模板</span>
            {([
              ['brief', '财报点评简报'],
              ['full', '公司研究完整稿'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => onTemplate(value)}
                className={`rounded border px-2.5 py-1 text-[9px] transition-colors ${
                  template === value
                    ? 'border-[#3a3a3e] bg-[#1d1d20] text-foreground'
                    : 'border-border/70 text-muted hover:text-foreground'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mt-5 rounded-md border border-border/60">
            <div className="flex items-center justify-between border-b border-border/60 px-3 py-2">
              <span className="text-[9px] tracking-[0.1em] text-muted">已选片段 · {snippets.length}</span>
              <span className="text-[8px] text-muted">不分类，按选择顺序组装</span>
            </div>
            <div className="max-h-[300px] overflow-y-auto p-2">
              {snippets.length === 0 ? (
                <div className="px-2 py-5 text-[9px] leading-5 text-muted">
                  先回到“对话”：选中文字会浮出“加入研报”；表格或市场快照右上角也有“加入研报”按钮。
                </div>
              ) : (
                snippets.map((snippet, index) => (
                  <div key={snippet.id} className="flex items-start gap-2 rounded px-2 py-1.5 hover:bg-[#101012]">
                    <span className="num mt-0.5 w-4 text-[8px] text-muted">{index + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[9px] text-[#d6d6da]">
                        {snippet.kind === 'metric_table' ? '数据表 · ' : snippet.kind === 'market_snapshot' ? '快照 · ' : '摘录 · '}
                        {snippet.title}
                      </p>
                      <p className="mt-0.5 line-clamp-2 text-[8px] leading-4 text-muted">
                        {snippet.body || snippet.metric_keys?.join(' / ')}
                      </p>
                    </div>
                    <button type="button" onClick={() => onRemoveSnippet(snippet.id)} className="text-[8px] text-muted hover:text-danger">
                      移除
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button
              type="button"
              onClick={onGenerate}
              disabled={generating || snippets.length === 0}
              className="rounded bg-foreground px-3 py-2 text-[10px] text-background disabled:opacity-30"
            >
              {generating ? '生成中…' : '生成研报'}
            </button>
            <span className="text-[9px] text-muted">生成后仍可返回调整选择。</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <div className="mx-auto max-w-[820px]">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[9px] tracking-[0.14em] text-muted">
              研报预览 · v{report.version}
              {report.review.polished ? ' · AI 润色' : ''}
            </p>
            {editing ? (
              <input
                aria-label="研报标题"
                value={draftTitle}
                onChange={(event) => setDraftTitle(event.target.value)}
                className="mt-1.5 h-9 w-full rounded-md border border-border bg-[#0b0b0c] px-2 text-[18px] text-foreground outline-none"
              />
            ) : (
              <h2 className="mt-1.5 text-[19px] font-normal tracking-[-0.02em]">{report.title}</h2>
            )}
            <p className="mt-1 text-[9px] text-muted">
              {report.review.sections} 节 · {report.review.sources} 个来源 · {report.review.citations} 处引用
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            {editing ? (
              <>
                <button type="button" onClick={() => { setEditing(false); setDraftTitle(report.title); setDraftSections(report.sections) }} className="rounded-md border border-border px-2.5 py-1.5 text-[9px] text-muted hover:text-foreground">
                  取消
                </button>
                <button type="button" onClick={saveEdits} disabled={busy === 'save'} className="rounded-md bg-foreground px-2.5 py-1.5 text-[9px] text-background disabled:opacity-30">
                  {busy === 'save' ? '保存中' : '保存新版本'}
                </button>
              </>
            ) : (
              <>
                <button type="button" onClick={() => { setEditing(true); setDraftTitle(report.title); setDraftSections(report.sections) }} className="rounded-md border border-border px-2.5 py-1.5 text-[9px] text-muted hover:text-foreground">
                  编辑
                </button>
                {report.sections.some((section) => section.id === 'observations') ? (
                  <button type="button" onClick={polish} disabled={Boolean(busy)} className="rounded-md border border-border px-2.5 py-1.5 text-[9px] text-muted hover:text-foreground disabled:opacity-30">
                    {busy === 'polish' ? '润色中' : 'AI 润色'}
                  </button>
                ) : null}
                <button type="button" onClick={() => setVersionsOpen((value) => !value)} className="rounded-md border border-border px-2.5 py-1.5 text-[9px] text-muted hover:text-foreground">
                  历史 v{report.version}
                </button>
                <button type="button" onClick={onReset} className="rounded-md border border-border px-2.5 py-1.5 text-[9px] text-muted hover:text-foreground">
                  调整选择
                </button>
                <button type="button" onClick={onExport} className="rounded-md bg-foreground px-2.5 py-1.5 text-[9px] text-background">
                  导出 Markdown
                </button>
              </>
            )}
          </div>
        </div>

        {versionsOpen && !editing ? (
          <div className="mt-3 rounded-md border border-border/60 bg-[#0b0b0c]">
            <div className="border-b border-border/60 px-3 py-2 text-[9px] text-muted">版本历史</div>
            <div className="max-h-[160px] overflow-y-auto p-1">
              {versions.map((version) => (
                <div key={version.version} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-[#101012]">
                  <span className="num w-7 text-[9px] text-muted">v{version.version}</span>
                  <span className="min-w-0 flex-1 truncate text-[9px] text-[#c5c5ca]">{version.note || '版本'}</span>
                  <span className="text-[8px] text-muted">{new Date(version.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
                  <button type="button" onClick={() => restoreVersion(version.version)} disabled={Boolean(busy)} className="text-[8px] text-muted hover:text-foreground disabled:opacity-30">
                    恢复
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {actionError ? <p className="mt-2 text-[9px] text-danger">{actionError}</p> : null}

        <div className="mt-4 flex flex-wrap gap-1.5">
          {report.review.checks.map((check) => (
            <span key={check} className="rounded border border-border/60 px-2 py-1 text-[8px] text-muted">
              {check}
            </span>
          ))}
        </div>

        <div className="mt-6 space-y-7">
          {(editing ? draftSections : report.sections).map((section, index) => (
            <section key={section.id}>
              <h3 className="text-[13px] font-normal">
                {index + 1}. {section.title}
              </h3>
              {section.kind === 'text' ? (
                editing ? (
                  <textarea
                    value={section.body ?? ''}
                    onChange={(event) => updateDraftSection(index, { body: event.target.value })}
                    rows={Math.max(4, Math.ceil((section.body ?? '').length / 80))}
                    className="mt-2 w-full resize-y rounded-md border border-border bg-[#0b0b0c] px-2.5 py-2 text-[11px] leading-6 text-[#c5c5ca] outline-none"
                  />
                ) : (
                  <p className="mt-2 whitespace-pre-wrap text-[11px] leading-6 text-[#c5c5ca]">
                    <CitationText text={section.body || ''} citations={section.citations || []} onCitation={onCitation} />
                  </p>
                )
              ) : null}
              {section.kind === 'metric_table' ? (
                <div className="mt-3 overflow-x-auto rounded-md border border-border/60">
                  <table className="w-full min-w-[560px] border-collapse text-left">
                    <thead>
                      <tr className="border-b border-border/60">
                        <th className="px-3 py-2 text-[9px] font-normal text-muted">指标</th>
                        <th className="px-2 py-2 text-[9px] font-normal text-muted">单位</th>
                        {(section.periods ?? []).map((period) => (
                          <th key={period} className="px-2 py-2 text-right text-[9px] font-normal text-muted">{period}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(section.rows ?? []).map((row) => (
                        <tr key={row.key} className="border-b border-border/40 last:border-0">
                          <td className="px-3 py-2 text-[10px] text-[#d6d6da]">{row.label}</td>
                          <td className="px-2 py-2 text-[9px] text-muted">{row.unit}</td>
                          {(section.periods ?? []).map((period) => {
                            const source = row.sources?.[period]
                            return (
                              <td key={period} className="px-1 py-1 text-right">
                                <button
                                  type="button"
                                  disabled={!source}
                                  onClick={() => source && onCitation(source)}
                                  className={`num w-full rounded px-1.5 py-1 text-[10px] ${
                                    source
                                      ? 'text-[#d6d6da] hover:bg-[#18181a] hover:text-foreground'
                                      : 'cursor-default text-[#4f4f54]'
                                  }`}
                                >
                                  {row.values[period] === null || row.values[period] === undefined
                                    ? '—'
                                    : formatCell(row.values[period] ?? null, row.unit)}
                                </button>
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {section.kind === 'list' ? (
                editing ? (
                  <textarea
                    value={(section.items ?? []).map((item) => String(item)).join('\n')}
                    onChange={(event) =>
                      updateDraftSection(index, {
                        items: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean),
                      })
                    }
                    rows={Math.max(3, (section.items ?? []).length + 1)}
                    className="mt-2 w-full resize-y rounded-md border border-border bg-[#0b0b0c] px-2.5 py-2 text-[10px] leading-5 text-[#c5c5ca] outline-none"
                  />
                ) : (
                  <ul className="mt-2 space-y-1.5">
                    {(section.items ?? []).map((item) => (
                      <li key={String(item)} className="text-[10px] leading-5 text-[#c5c5ca]">
                        · {String(item)}
                      </li>
                    ))}
                  </ul>
                )
              ) : null}
              {section.kind === 'sources' ? (
                <ul className="mt-2 space-y-1.5">
                  {(section.items ?? []).map((item) => {
                    if (typeof item === 'string') return <li key={item} className="text-[10px] text-[#c5c5ca]">{item}</li>
                    return (
                      <li key={item.name} className="flex items-center justify-between text-[10px] text-[#c5c5ca]">
                        <span>{item.name}</span>
                        <a href={item.file_url} target="_blank" rel="noreferrer" className="text-[9px] text-muted hover:text-foreground">
                          打开 PDF
                        </a>
                      </li>
                    )
                  })}
                </ul>
              ) : null}

            </section>
          ))}
        </div>

        <p className="mt-8 border-t border-border/50 pt-3 text-[9px] leading-4 text-muted">
          研报由已确认指标和已保存研究回答确定性组装；引用可查看在线来源或 PDF 原文页。不构成投资建议。
        </p>
      </div>
    </div>
  )
}

export function ResearchPage() {
  const { stocks } = useWorkspace()
  const [params] = useSearchParams()
  const urlSymbol = (params.get('symbol') || '').trim()
  const urlName = (params.get('name') || '').trim()
  const [session, setSession] = useState<ResearchSession | null>(null)
  const [sessions, setSessions] = useState<ResearchSessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [view, setView] = useState<'chat' | 'data' | 'report'>('chat')
  const [activeMetric, setActiveMetric] = useState('revenue')
  const [activePeriod, setActivePeriod] = useState('2024')
  const [selected, setSelected] = useState<SelectedCell | null>(null)
  const [selectedCitation, setSelectedCitation] = useState<ResearchCitation | null>(null)
  const [citationList, setCitationList] = useState<ResearchCitation[] | null>(null)
  const [messages, setMessages] = useState<ResearchMessage[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')
  const [materialsOpen, setMaterialsOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [candidateExpanded, setCandidateExpanded] = useState(false)
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set())
  const [report, setReport] = useState<ResearchReport | null>(null)
  const [reportTitle, setReportTitle] = useState('')
  const [reportTemplate, setReportTemplate] = useState<'brief' | 'full'>('brief')
  const [reportSnippets, setReportSnippets] = useState<ResearchSnippet[]>([])
  const [generating, setGenerating] = useState(false)
  const [selectionToolbar, setSelectionToolbar] = useState<{ x: number; y: number; text: string; citations: ResearchCitation[] } | null>(null)
  const chatEndRef = useRef<HTMLDivElement | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const applySession = (data: ResearchSession) => {
    setSession(data)
    setMessages(data.messages ?? [])
    setReport(null)
    setReportTitle(`${data.name}（${data.symbol}）经营数据研究`)
    setReportSnippets([])
    const groups = data.candidates ?? []
    setSelectedCandidates(
      new Set(
        groups
          .slice(0, 6)
          .flatMap((group) => Object.values(group.cells).map((cell) => cell.candidate_id)),
      ),
    )
    const defaultMetric = data.metrics.find((item) => item.key === 'revenue') ?? data.metrics[0]
    const defaultPeriod = [...data.periods].reverse().find((period) => {
      const cell = defaultMetric?.cells[period]
      return cell?.value !== null && cell?.value !== undefined
    })
    if (defaultMetric && defaultPeriod) {
      const cell = defaultMetric.cells[defaultPeriod]
      setActiveMetric(defaultMetric.key)
      setActivePeriod(defaultPeriod)
      if (cell?.document_id && cell?.page) {
        setSelected({
          documentId: cell.document_id,
          page: cell.page,
          quote: cell.quote,
          label: defaultMetric.label,
          period: defaultPeriod,
          metricKey: defaultMetric.key,
        })
      }
    } else {
      setSelected(null)
    }
  }

  useEffect(() => {
    let live = true
    setLoading(true)
    setError('')
    const request = urlSymbol
      ? api.ensureResearchSession(urlSymbol, urlName || urlSymbol)
      : api.bootstrapResearch()
    request
      .then(async (data) => {
        if (!live) return
        applySession(data)
        const list = await api.listResearchSessions()
        if (live) setSessions(list.items)
        if (live) await loadLatestReport(data.id)
      })
      .catch((err) => {
        if (live) setError(err instanceof Error ? err.message : '读取研报失败')
      })
      .finally(() => {
        if (live) setLoading(false)
      })
    return () => {
      live = false
    }
  }, [urlSymbol, urlName])

  const createSession = async () => {
    const symbol = newSymbol.trim()
    if (!symbol) {
      setError('请输入股票代码')
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await api.ensureResearchSession(symbol, newName.trim() || symbol)
      applySession(data)
      setMessages(data.messages ?? [])
      setNewOpen(false)
      setNewSymbol('')
      setNewName('')
      setView('chat')
      const list = await api.listResearchSessions()
      setSessions(list.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建研究失败')
    } finally {
      setLoading(false)
    }
  }

  const loadLatestReport = async (sessionId: string) => {
    try {
      const reports = await api.listResearchReports(sessionId)
      if (reports.items.length) {
        setReport(await api.getResearchReport(reports.items[0].id))
      }
    } catch {
      // a session may not have a report yet
    }
  }

  const loadSession = async (sessionId: string) => {
    if (sessionId === session?.id) return
    setLoading(true)
    setError('')
    try {
      const data = await api.getResearchSession(sessionId)
      applySession(data)
      await loadLatestReport(data.id)
      setView('chat')
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取研究失败')
    } finally {
      setLoading(false)
    }
  }

  const uploadDocument = async (file: File) => {
    if (!session || uploading) return
    setUploading(true)
    setError('')
    try {
      const data = await api.uploadResearchDocument(session.id, file)
      applySession(data)
      setView(data.candidates?.length ? 'data' : 'chat')
      const list = await api.listResearchSessions()
      setSessions(list.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传年报失败')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const toggleCandidate = (id: string) => {
    setSelectedCandidates((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleCandidateGroup = (group: ResearchCandidateGroup) => {
    const ids = Object.values(group.cells).map((cell) => cell.candidate_id)
    setSelectedCandidates((prev) => {
      const next = new Set(prev)
      const all = ids.every((id) => next.has(id))
      ids.forEach((id) => (all ? next.delete(id) : next.add(id)))
      return next
    })
  }

  const confirmCandidates = async () => {
    if (!session || !selectedCandidates.size || confirming) return
    setConfirming(true)
    setError('')
    try {
      const data = await api.confirmResearchCandidates(session.id, [...selectedCandidates])
      applySession(data)
      setView('data')
    } catch (err) {
      setError(err instanceof Error ? err.message : '写入底稿失败')
    } finally {
      setConfirming(false)
    }
  }

  const addSnippet = (snippet: Omit<ResearchSnippet, 'id'>) => {
    setReportSnippets((prev) => [
      ...prev,
      { ...snippet, id: `snippet-${Date.now()}-${prev.length}` },
    ])
  }

  const addTextSnippet = (text: string, citations: ResearchCitation[]) => {
    const body = text.trim()
    if (!body) return
    addSnippet({ kind: 'text', title: '研究摘录', body, citations })
    setSelectionToolbar(null)
    window.getSelection()?.removeAllRanges()
  }

  const removeSnippet = (id: string) => {
    setReportSnippets((prev) => prev.filter((item) => item.id !== id))
  }

  const generateReport = async () => {
    if (!session || generating) return
    if (!reportSnippets.length) {
      setError('先在对话中选中文字，或点击表格/卡片的“加入研报”。')
      return
    }
    setGenerating(true)
    setError('')
    try {
      const data = await api.createResearchReport(session.id, {
        template: reportTemplate,
        metric_keys: [],
        message_ids: [],
        snippets: reportSnippets,
        title: reportTitle,
      })
      setReport(data)
      setView('report')
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成研报失败')
    } finally {
      setGenerating(false)
    }
  }

  const exportReport = async () => {
    if (!report) return
    try {
      await api.downloadResearchReport(report.id, report.title)
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出失败')
    }
  }

  useEffect(() => {
    if (view === 'chat') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, asking, view])

  const currentMetric = useMemo(
    () => session?.metrics.find((metric) => metric.key === activeMetric) ?? null,
    [session, activeMetric],
  )

  const openCell = (metric: ResearchMetric, period: string) => {
    const cell = metric.cells[period]
    if (!cell || cell.value === null || cell.value === undefined || !cell.document_id || !cell.page) {
      return
    }
    setActiveMetric(metric.key)
    setActivePeriod(period)
    setSelectedCitation(null)
    setSelected({
      documentId: cell.document_id,
      page: cell.page,
      quote: cell.quote,
      label: metric.label,
      period,
      metricKey: metric.key,
    })
  }

  const showSources = (citations: ResearchCitation[]) => {
    setCitationList(citations)
    setSelected(null)
    setSelectedCitation(null)
  }

  const openCitation = (citation: ResearchCitation) => {
    setCitationList(null)
    const payload = citation.payload || {}
    const documentId = payload.document_id || citation.document_id
    const page = payload.page || citation.page
    if (documentId && page) {
      setSelectedCitation(null)
      setSelected({
        documentId,
        page,
        quote: payload.quote || citation.quote || '',
        label: citation.label,
        period: payload.period || '',
        metricKey: payload.metric_key || '',
      })
      return
    }
    setSelected(null)
    setSelectedCitation(citation)
  }

  const openSourcePage = (page: number) => {
    if (!selected) return
    const source = session?.sources.find((item) => item.id === selected.documentId)
    if (!source) return
    setSelected({ ...selected, page: Math.min(Math.max(page, 1), source.page_count || page) })
  }

  const ask = async (text?: string) => {
    if (!session || asking) return
    const value = (text ?? question).trim()
    if (!value) return
    const optimistic: ResearchMessage = {
      id: -Date.now(),
      session_id: session.id,
      role: 'user',
      content: value,
      data: {},
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimistic])
    setQuestion('')
    setAsking(true)
    setError('')
    try {
      const result = await api.askResearch(session.id, value)
      setMessages((prev) => [...prev, result.message])
    } catch (err) {
      setError(err instanceof Error ? err.message : '研究 Agent 调用失败')
    } finally {
      setAsking(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-[11px] text-muted">
          <Spinner size="sm" />
          正在读取四份年报，整理逐年指标
        </div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="mx-auto max-w-lg px-6 py-10">
        <Alert status="danger" title="读取失败">
          <p className="text-[11px] leading-5">{error || '研究数据不可用'}</p>
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-[176px] shrink-0 flex-col border-r border-border/60 bg-[#080809] lg:flex">
        <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
          <span className="text-[9px] tracking-[0.14em] text-muted">对话</span>
          <div className="flex items-center gap-2">
            <span className="num text-[9px] text-muted">{sessions.length || 1}</span>
            <button
              type="button"
              onClick={() => setNewOpen(true)}
              className="flex size-5 items-center justify-center rounded border border-border/70 text-muted transition-colors hover:text-foreground"
              aria-label="新建研究"
            >
              <Plus size={11} />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
          {(sessions.length ? sessions : [{ id: session.id, name: session.name, symbol: session.symbol, question: session.question } as ResearchSessionSummary]).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => loadSession(item.id)}
              className={`w-full rounded-md border px-3 py-2.5 text-left ${
                item.id === session.id
                  ? 'border-border/70 bg-[#111112]'
                  : 'border-transparent hover:bg-[#101012]'
              }`}
            >
              <p className="truncate text-[11px] text-foreground">{item.name}</p>
              <p className="mt-1 flex items-center gap-1.5 text-[9px] text-muted">
                <span className="num">{item.symbol}</span>
                <span>·</span>
                <span>{item.id === session.id ? `${session.sources.length} 份材料` : '历史研究'}</span>
              </p>
              <p className="mt-1 line-clamp-2 text-[9px] leading-4 text-muted">{item.question}</p>
            </button>
          ))}
        </div>

      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="border-b border-border/60 px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[9px] tracking-[0.14em] text-muted">
                研究 · {view === 'chat' ? '对话' : view === 'data' ? '数据底稿' : '研报'}
              </p>
              <h1 className="mt-1.5 flex items-baseline gap-2 text-[20px] font-normal tracking-[-0.03em]">
                {session.name}
                <span className="num text-[11px] font-light text-muted">{session.symbol}</span>
              </h1>
              <p className="mt-1 text-[10px] text-muted">
                {session.sources.length
                  ? `基于 ${session.sources.length} 份材料 · 每个数字可回到来源`
                  : '可以直接问行情、估值、新闻；所有数字都带来源'}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Chip size="sm" variant="soft" className="h-6 border border-border/70 bg-transparent px-2 text-[9px] text-muted">
                {session.sources.length === 0
                  ? '在线数据'
                  : session.metrics.length
                    ? `${session.quality.available_cells}/${session.quality.expected_cells} 已核实`
                    : '未提取指标'}
              </Chip>
              {session.sources.length ? (
                <button
                  type="button"
                  onClick={() => setMaterialsOpen(true)}
                  className="rounded-md border border-border/70 px-2 py-1 text-[9px] text-muted transition-colors hover:text-foreground"
                >
                  材料 {session.sources.length}
                </button>
              ) : null}
              <div className="flex rounded-md border border-border/70 p-0.5">
                <button
                  type="button"
                  onClick={() => setView('chat')}
                  className={`flex h-6 items-center gap-1 rounded px-2 text-[9px] transition-colors ${
                    view === 'chat' ? 'bg-[#1d1d20] text-foreground' : 'text-muted hover:text-foreground'
                  }`}
                >
                  <MessageSquare size={10} /> 对话
                </button>
                <button
                  type="button"
                  onClick={() => setView('data')}
                  className={`flex h-6 items-center gap-1 rounded px-2 text-[9px] transition-colors ${
                    view === 'data' ? 'bg-[#1d1d20] text-foreground' : 'text-muted hover:text-foreground'
                  }`}
                >
                  <Table2 size={10} /> 数据
                </button>
                <button
                  type="button"
                  onClick={() => setView('report')}
                  className={`flex h-6 items-center gap-1 rounded px-2 text-[9px] transition-colors ${
                    view === 'report' ? 'bg-[#1d1d20] text-foreground' : 'text-muted hover:text-foreground'
                  }`}
                >
                  <NotebookText size={10} /> 研报
                </button>
              </div>
              <Button
                size="sm"
                variant="secondary"
                className="h-7 gap-1.5 border border-border bg-transparent px-2.5 text-[10px] font-light"
                onPress={() => downloadCsv(session)}
              >
                <Download size={12} strokeWidth={1.5} />
                导出 CSV
              </Button>
            </div>
          </div>
        </header>

        {view === 'chat' ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              {messages.length === 0 ? (
                <div className="mx-auto max-w-[620px] py-10">
                  {session.candidates?.length ? (
                    <button
                      type="button"
                      onClick={() => setView('data')}
                      className="mb-5 flex w-full items-center justify-between rounded-md border border-[#3a3220] bg-[#12100b] px-3 py-2 text-left text-[10px] text-[var(--warning)]"
                    >
                      <span>发现 {session.candidates.length} 组候选指标，确认后进入底稿</span>
                      <span className="text-[9px] text-muted">去确认 →</span>
                    </button>
                  ) : null}
                  <div className="flex size-8 items-center justify-center rounded-md border border-border bg-[#111112]">
                    <MessageSquare size={14} strokeWidth={1.4} className="text-muted" />
                  </div>
                  {session.sources.length === 0 ? (
                    <>
                      <h2 className="mt-4 text-[16px] font-normal">可以直接开始研究</h2>
                      <p className="mt-2 max-w-[460px] text-[11px] leading-5 text-muted">
                        可以直接问行情、估值、新闻和趋势；所有数字都会带来源。导入年报后，还可以查看 PDF 原文、抽取财务指标。
                      </p>
                      <div className="mt-5 grid gap-2 sm:grid-cols-2">
                        {[
                          '这家公司最近走势怎么样？',
                          '估值贵不贵？',
                          '最近有什么新闻？',
                          '帮我梳理这家公司',
                        ].map((suggestion) => (
                          <button
                            key={suggestion}
                            type="button"
                            onClick={() => ask(suggestion)}
                            className="rounded-md border border-border/60 px-3 py-2 text-left text-[10px] text-[#c5c5ca] transition-colors hover:border-[#3a3a3e] hover:text-foreground"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={() => setMaterialsOpen(true)}
                        className="mt-4 flex items-center gap-1.5 text-[9px] text-muted hover:text-foreground"
                      >
                        <Upload size={11} />
                        导入年报，继续深挖
                      </button>
                    </>
                  ) : (
                    <>
                      <h2 className="mt-4 text-[16px] font-normal">从年报里找答案</h2>
                      <p className="mt-2 max-w-[460px] text-[11px] leading-5 text-muted">
                        问经营数据、趋势或原因。Agent 会调用指标底稿和原文检索，回答里每个数字都可以打开 PDF 核对。
                      </p>
                      <div className="mt-5 space-y-2">
                        {[
                          '2021–2024 付费用户和 ARPU 怎么变？',
                          '毛利率提升主要来自哪里？',
                          '2024 年为什么没有用户数据？',
                        ].map((suggestion) => (
                          <button
                            key={suggestion}
                            type="button"
                            onClick={() => ask(suggestion)}
                            className="block w-full rounded-md border border-border/60 px-3 py-2 text-left text-[10px] text-[#c5c5ca] transition-colors hover:border-[#3a3a3e] hover:text-foreground"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div className="mx-auto max-w-[760px] space-y-6">
                  {messages.map((message) => (
                    <ChatMessage
                      key={message.id}
                      message={message}
                      session={session}
                      onSelectText={(text, citations, rect) =>
                        setSelectionToolbar({ ...rect, text, citations })
                      }
                      onAddMetric={(title, keys, citations) =>
                        addSnippet({ kind: 'metric_table', title, metric_keys: keys, citations })
                      }
                      onAddMarket={(body, citations) =>
                        addSnippet({ kind: 'market_snapshot', title: '市场快照', body, citations })
                      }
                      onShowSources={showSources}
                      onCitation={openCitation}
                      onCell={openCell}
                    />
                  ))}
                  {asking ? (
                    <div className="flex items-center gap-2 text-[10px] text-muted">
                      <Spinner size="sm" />
                      正在查年报、核对页码
                    </div>
                  ) : null}
                  <div ref={chatEndRef} />
                </div>
              )}
            </div>
            <div className="border-t border-border/60 px-6 py-3">
              {error ? <p className="mb-2 text-[9px] text-danger">{error}</p> : null}
              <div className="mx-auto flex max-w-[760px] items-end gap-2 rounded-md border border-border/70 bg-[#0b0b0c] px-3 py-2">
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void ask()
                    }
                  }}
                  rows={1}
                  placeholder="问一个关于这家公司或年报的问题…"
                  className="max-h-24 min-h-6 flex-1 resize-none bg-transparent text-[11px] leading-5 text-foreground outline-none placeholder:text-[#5f5f63]"
                />
                <button
                  type="button"
                  disabled={asking || !question.trim()}
                  onClick={() => void ask()}
                  className="flex size-7 shrink-0 items-center justify-center rounded-md bg-foreground text-background transition-opacity disabled:opacity-30"
                  aria-label="发送"
                >
                  <Send size={13} strokeWidth={1.7} />
                </button>
              </div>
              <p className="mx-auto mt-2 max-w-[760px] text-[8px] text-muted">
                回答中的数字均带来源；PDF 材料仅用于原文核对。不构成投资建议。
              </p>
            </div>
          </div>
        ) : view === 'data' ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            {session.metrics.length === 0 ? (
              <p className="mb-4 rounded-md border border-border/60 px-3 py-2 text-[10px] leading-5 text-muted">
                尚未提取到结构化指标。先导入年报，再回到对话或数据视图。
              </p>
            ) : null}
            <div className="flex items-end justify-between">
              <div>
                <h2 className="text-[12px] font-normal">逐年经营数据</h2>
                <p className="mt-1 text-[9px] text-muted">
                  {session.symbol === '09899'
                    ? '金额单位：人民币百万元；用户单位见表；2024 年报未披露用户指标，保留为空。'
                    : '单位与口径来自候选表；只保留已确认的数据点，未披露项不会被补零。'}
                </p>
              </div>
              <span className="flex items-center gap-1.5 text-[9px] text-muted">
                <Search size={11} strokeWidth={1.5} />
                点击任意数值查看 PDF 原文
              </span>
            </div>

            {session.candidates?.length ? (
              <CandidatePanel
                groups={session.candidates}
                selected={selectedCandidates}
                expanded={candidateExpanded}
                confirming={confirming}
                onToggle={toggleCandidate}
                onToggleGroup={toggleCandidateGroup}
                onExpand={() => setCandidateExpanded((value) => !value)}
                onConfirm={confirmCandidates}
              />
            ) : null}

            {session.quality.available_cells > 0 ? (
              <>
                <div className="mt-4">
                  <MetricTable metrics={session.metrics} periods={session.periods} selected={selected} onCell={openCell} />
                </div>

                <div className="mt-7">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-[12px] font-normal">趋势</h2>
                  <p className="mt-1 text-[9px] text-muted">
                    {currentMetric?.label} · {currentMetric?.unit}
                  </p>
                </div>
                <select
                  value={activeMetric}
                  onChange={(event) => setActiveMetric(event.target.value)}
                  className="h-7 rounded-md border border-border bg-[#0b0b0c] px-2 text-[10px] text-[#d6d6da] outline-none"
                  aria-label="选择指标"
                >
                  {session.metrics.map((metric) => (
                    <option key={metric.key} value={metric.key}>
                      {metric.label}
                    </option>
                  ))}
                </select>
              </div>
              {currentMetric ? (
                <MetricChart
                  cells={currentMetric.cells}
                  periods={session.periods}
                  unit={currentMetric.unit}
                  activePeriod={activePeriod}
                  onSelect={(period) => openCell(currentMetric, period)}
                />
              ) : null}
                </div>
              </>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 border-t border-border/50 pt-4 text-[9px] leading-4 text-muted">
              <span className="flex items-center gap-1.5">
                <Library size={11} strokeWidth={1.5} />
                底稿来自 {session.sources.length} 份年报，不是手工录入
              </span>
              <span>每个数值绑定 document + physical page</span>
              <span>未披露不会被补零或推算</span>
            </div>
          </div>
        ) : (
          <ReportView
            session={session}
            report={report}
            title={reportTitle}
            template={reportTemplate}
            snippets={reportSnippets}
            generating={generating}
            onTitle={setReportTitle}
            onTemplate={setReportTemplate}
            onRemoveSnippet={removeSnippet}
            onGenerate={generateReport}
            onExport={exportReport}
            onReset={() => setReport(null)}
            onShowSources={showSources}
            onCitation={openCitation}
            onReportChange={setReport}
          />
        )}
      </section>

      <SourceViewer
        session={session}
        selected={selected}
        citation={selectedCitation}
        citationList={citationList}
        onPickCitation={openCitation}
        onPage={openSourcePage}
        onClearCitation={() => {
          setSelectedCitation(null)
          setCitationList(null)
        }}
      />

      {selectionToolbar ? (
        <div
          className="fixed z-[120] flex items-center gap-1 rounded-md border border-border bg-[#111112] px-1.5 py-1 shadow-xl"
          style={{ left: selectionToolbar.x, top: selectionToolbar.y }}
        >
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => addTextSnippet(selectionToolbar.text, selectionToolbar.citations)}
            className="flex items-center gap-1 rounded px-1.5 py-1 text-[9px] text-foreground hover:bg-[#1d1d20]"
          >
            <NotebookText size={10} /> 加入研报
          </button>
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setSelectionToolbar(null)}
            className="px-1 text-[10px] text-muted hover:text-foreground"
          >
            ×
          </button>
        </div>
      ) : null}

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void uploadDocument(file)
        }}
      />

      {newOpen ? (
        <div
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/70 px-4 pt-[12vh]"
          onClick={() => setNewOpen(false)}
        >
          <div
            className="w-full max-w-[460px] rounded-lg border border-border bg-[#0c0c0d] shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
              <div>
                <p className="text-[11px] text-foreground">新建研究</p>
                <p className="mt-1 text-[9px] text-muted">选一只自选股，或直接输入代码</p>
              </div>
              <button type="button" onClick={() => setNewOpen(false)} className="text-muted hover:text-foreground">
                <X size={14} />
              </button>
            </div>
            <div className="p-4">
              <label className="text-[9px] text-muted">
                股票代码
                <input
                  value={newSymbol}
                  onChange={(event) => setNewSymbol(event.target.value)}
                  placeholder="例如 AAPL / 600519 / 09899"
                  className="mt-1.5 h-8 w-full rounded-md border border-border bg-[#0b0b0c] px-2.5 text-[11px] outline-none"
                />
              </label>
              <label className="mt-3 block text-[9px] text-muted">
                名称（可选）
                <input
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  placeholder="例如 Apple Inc."
                  className="mt-1.5 h-8 w-full rounded-md border border-border bg-[#0b0b0c] px-2.5 text-[11px] outline-none"
                />
              </label>
              {stocks.length ? (
                <div className="mt-3">
                  <p className="text-[9px] text-muted">从自选股选择</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {stocks.map((stock) => (
                      <button
                        key={stock.symbol}
                        type="button"
                        onClick={() => {
                          setNewSymbol(stock.symbol)
                          setNewName(stock.name)
                        }}
                        className={`rounded border px-2 py-1 text-[9px] ${
                          newSymbol === stock.symbol
                            ? 'border-[#3a3a3e] bg-[#1d1d20] text-foreground'
                            : 'border-border/60 text-muted hover:text-foreground'
                        }`}
                      >
                        {stock.name}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <button
                type="button"
                onClick={createSession}
                disabled={!newSymbol.trim() || loading}
                className="mt-5 w-full rounded-md bg-foreground px-3 py-2 text-[10px] text-background disabled:opacity-30"
              >
                {loading ? '创建中…' : '开始研究'}
              </button>
              <p className="mt-2 text-[8px] leading-4 text-muted">
                没有年报也可以先问行情/估值/新闻；导入 PDF 后可以继续深挖财务原文。
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {materialsOpen ? (
        <div
          className="fixed inset-0 z-[100] bg-black/50"
          onClick={() => setMaterialsOpen(false)}
        >
          <div
            className="absolute right-4 top-16 w-[320px] rounded-lg border border-border bg-[#0c0c0d] shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border/60 px-3 py-2.5">
              <p className="text-[10px] text-foreground">本对话材料</p>
              <button type="button" onClick={() => setMaterialsOpen(false)} className="text-muted hover:text-foreground">
                <X size={13} />
              </button>
            </div>
            <div className="max-h-[320px] space-y-0.5 overflow-y-auto p-2">
              {session.sources.length === 0 ? (
                <p className="px-2 py-3 text-[9px] leading-4 text-muted">还没有材料。导入年报后可以抽取指标、查看原文。</p>
              ) : null}
              {session.sources.map((source) => (
                <button
                  key={source.id}
                  type="button"
                  onClick={() => {
                    setSelectedCitation(null)
                    setSelected({
                      documentId: source.id,
                      page: 1,
                      quote: '打开年报第一页，可查看目录与公司信息。',
                      label: '年报原文',
                      period: String(source.year ?? ''),
                      metricKey: '',
                    })
                    setMaterialsOpen(false)
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left hover:bg-[#101012]"
                >
                  <FileText size={12} strokeWidth={1.4} className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[10px] text-[#c5c5ca]">{source.name}</span>
                    <span className="mt-0.5 block text-[9px] text-muted">{source.page_count} 页 · {source.year}</span>
                  </span>
                </button>
              ))}
            </div>
            <div className="border-t border-border/60 p-2">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/70 px-2 py-1.5 text-[9px] text-muted hover:text-foreground disabled:opacity-40"
              >
                <Upload size={11} />
                {uploading ? '正在解析 PDF…' : '导入年报 PDF'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
