import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, Chip, Spinner, Tabs } from '@heroui/react'
import {
  ArrowLeft,
  Check,
  Copy,
  Database,
  FileSearch,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import { api } from '../lib/api'
import type { Evidence, RunDetail } from '../types'
import { ActionChip } from '../components/ActionChip'
import { ChatPanel } from '../components/ChatPanel'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { TraceList } from '../components/TraceList'
import {
  formatDate,
  formatLatency,
  formatPrice,
  qualityTone,
} from '../lib/format'

function EvidenceButton({
  id,
  evidence,
  onOpen,
}: {
  id: string
  evidence?: Evidence
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex max-w-full items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[8px] text-muted transition-colors hover:border-[#3a3a3d] hover:text-foreground"
    >
      <Database size={8} strokeWidth={1.5} />
      <span className="truncate">{evidence?.label ?? id}</span>
      <span className="num shrink-0 text-[#57575c]">{id}</span>
    </button>
  )
}

export function RunPage() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [chatError, setChatError] = useState('')
  const [selected, setSelected] = useState<Evidence | null>(null)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [rerunning, setRerunning] = useState(false)
  const [tab, setTab] = useState('decision')

  const load = async () => {
    if (!runId) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.getRun(runId))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [runId])

  const report = detail?.report ?? null
  const evidenceMap = useMemo(() => {
    const map = new Map<string, Evidence>()
    report?.evidence.forEach((item) => map.set(item.id, item))
    return map
  }, [report])

  const openEvidence = (id: string) => {
    const item = evidenceMap.get(id)
    if (!item) return
    setSelected(item)
    setEvidenceOpen(true)
  }

  const sendChat = async (message: string) => {
    if (!detail) return
    setChatError('')
    try {
      const result = await api.chat(detail.run.id, message)
      setDetail({ ...detail, chat: result.messages })
    } catch (err) {
      setChatError(err instanceof Error ? err.message : '追问失败')
    }
  }

  const copyMarkdown = async () => {
    if (!report?.markdown) return
    try {
      await navigator.clipboard.writeText(report.markdown)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setError('复制失败，请检查浏览器权限。')
    }
  }

  const rerun = async () => {
    if (!report || rerunning) return
    setRerunning(true)
    setError('')
    try {
      const next = await api.analyze(report.symbol)
      navigate(`/runs/${next.run.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败')
    } finally {
      setRerunning(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-muted">
        <Spinner size="sm" color="current" />
        <span className="ml-2">加载复盘</span>
      </div>
    )
  }

  if (error && !detail) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <Alert status="danger" className="w-[360px]">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title className="text-[11px]">{error}</Alert.Title>
          </Alert.Content>
        </Alert>
        <Button size="sm" variant="secondary" onPress={() => navigate('/')}>
          返回自选股
        </Button>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-muted">
        这次运行没有生成报告。
      </div>
    )
  }

  const plan = report.plan
  const run = detail!.run

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 px-5">
        <div className="flex min-w-0 items-center gap-3">
          <Button
            isIconOnly
            size="sm"
            variant="ghost"
            aria-label="返回"
            className="size-7 min-w-7 text-muted"
            onPress={() => navigate('/')}
          >
            <ArrowLeft size={15} strokeWidth={1.5} />
          </Button>
          <div className="flex min-w-0 items-baseline gap-2">
            <h1 className="truncate text-[15px] font-normal tracking-[-0.02em]">{report.name}</h1>
            <span className="num text-[10px] text-muted">{report.symbol}</span>
          </div>
          <ActionChip action={report.action} />
          <span className="num text-[13px] text-foreground">{report.score}</span>
          <Chip size="sm" variant="soft" className="h-5 px-1.5 text-[8px] text-muted">
            置信度 {(report.confidence * 100).toFixed(0)}%
          </Chip>
          <Chip size="sm" variant="soft" className="h-5 px-1.5 text-[8px] text-muted">
            {report.data_quality}
          </Chip>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2 text-[10px] font-light text-muted"
            onPress={() =>
              navigate(
                `/research?symbol=${encodeURIComponent(report.symbol)}&name=${encodeURIComponent(report.name)}`,
              )
            }
          >
            <FileSearch size={12} strokeWidth={1.5} />
            研究
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2 text-[10px] font-light text-muted"
            onPress={copyMarkdown}
          >
            {copied ? <Check size={12} strokeWidth={1.5} /> : <Copy size={12} strokeWidth={1.5} />}
            {copied ? '已复制' : '复制'}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            className="h-8 border border-border bg-transparent px-3 text-[10px] font-light"
            onPress={rerun}
            isDisabled={rerunning}
          >
            {rerunning ? <Spinner size="sm" color="current" /> : <RefreshCw size={12} strokeWidth={1.5} />}
            重新分析
          </Button>
        </div>
      </header>

      {error ? (
        <div className="border-b border-border/60 px-5 py-2">
          <Alert status="danger" className="py-1.5">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title className="text-[10px]">{error}</Alert.Title>
            </Alert.Content>
          </Alert>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="shrink-0 border-b border-border/60 px-5 py-4">
            <div className="flex items-start justify-between gap-5">
              <p className="max-w-[760px] text-[12px] leading-6 text-[#d7d7da]">{report.summary}</p>
              <div className="shrink-0 text-right">
                <p className="num text-[10px] text-muted">{formatDate(report.as_of)}</p>
                <p className="mt-1 text-[9px] text-[#5f5f64]">{formatLatency(run.latency_ms)}</p>
              </div>
            </div>
            {report.validation_notes?.length ? (
              <div className="mt-3 flex items-start gap-2 rounded-md border border-[#3a3020] bg-[#17130c] px-2.5 py-1.5 text-[9px] leading-4 text-[var(--warning)]">
                <ShieldAlert size={12} strokeWidth={1.5} className="mt-0.5 shrink-0" />
                <span>{report.validation_notes.join('；')}</span>
              </div>
            ) : null}
          </div>

          <Tabs
            selectedKey={tab}
            onSelectionChange={(key) => setTab(String(key))}
            className="report-tabs flex min-h-0 flex-1 flex-col"
          >
            <Tabs.ListContainer className="border-b border-border/60 px-5">
              <Tabs.List aria-label="报告视图" className="gap-5">
                <Tabs.Tab id="decision" className="h-9 px-0 text-[11px]">
                  决策
                  <Tabs.Indicator />
                </Tabs.Tab>
                <Tabs.Tab id="evidence" className="h-9 px-0 text-[11px]">
                  证据
                  <Tabs.Indicator />
                </Tabs.Tab>
                <Tabs.Tab id="trace" className="h-9 px-0 text-[11px]">
                  执行
                  <Tabs.Indicator />
                </Tabs.Tab>
              </Tabs.List>
            </Tabs.ListContainer>

            <Tabs.Panel id="decision" className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <div className="grid grid-cols-4 gap-2">
                <div className="rounded-md border border-border p-3">
                  <p className="text-[9px] text-muted">入场区间</p>
                  <p className="num mt-1 text-[13px] text-[#9db9ff]">
                    {formatPrice(plan.entry_low)} – {formatPrice(plan.entry_high)}
                  </p>
                  <p className="mt-1 text-[8px] text-[#5f5f64]">回踩企稳再执行</p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="text-[9px] text-muted">止损</p>
                  <p className="num mt-1 text-[13px] text-[var(--danger)]">
                    {formatPrice(plan.stop_loss)}
                  </p>
                  <p className="mt-1 text-[8px] text-[#5f5f64]">收盘跌破失效</p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="text-[9px] text-muted">目标</p>
                  <p className="num mt-1 text-[13px] text-[var(--success)]">
                    {formatPrice(plan.target_price)}
                  </p>
                  <p className="mt-1 text-[8px] text-[#5f5f64]">压力位参照</p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="text-[9px] text-muted">建议仓位</p>
                  <p className="num mt-1 text-[13px] text-[var(--warning)]">
                    {plan.position_pct ?? 0}%
                  </p>
                  <p className="mt-1 text-[8px] text-[#5f5f64]">单票上限</p>
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-[11px] text-foreground">核心论点</h2>
                  <span className="text-[9px] text-muted">点击证据查看原始数据</span>
                </div>
                <div className="divide-y divide-border/60">
                  {report.thesis.map((item, index) => (
                    <div key={`${item.text}-${index}`} className="flex gap-3 py-3">
                      <span className="num w-5 shrink-0 text-[9px] text-[#5f5f64]">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <div className="min-w-0">
                        <p className="text-[11px] leading-5 text-[#c9c9cd]">{item.text}</p>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {item.evidence_ids.map((id) => (
                            <EvidenceButton
                              key={id}
                              id={id}
                              evidence={evidenceMap.get(id)}
                              onOpen={() => openEvidence(id)}
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5">
                <h2 className="mb-2 text-[11px] text-foreground">风险与失效条件</h2>
                <div className="space-y-1.5">
                  {report.risks.map((risk, index) => (
                    <div
                      key={`${risk.text}-${index}`}
                      className="flex items-start gap-2 rounded-md border border-border px-2.5 py-2"
                    >
                      <Chip
                        size="sm"
                        variant="soft"
                        color={
                          risk.severity === 'high'
                            ? 'danger'
                            : risk.severity === 'medium'
                              ? 'warning'
                              : 'default'
                        }
                        className="mt-0.5 h-4 px-1 text-[7px] uppercase"
                      >
                        {risk.severity}
                      </Chip>
                      <div className="min-w-0">
                        <p className="text-[10px] leading-5 text-[#bcbcc1]">{risk.text}</p>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {risk.evidence_ids.map((id) => (
                            <EvidenceButton
                              key={id}
                              id={id}
                              evidence={evidenceMap.get(id)}
                              onOpen={() => openEvidence(id)}
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Tabs.Panel>

            <Tabs.Panel id="evidence" className="min-h-0 flex-1 overflow-y-auto px-5 py-2">
              <div className="divide-y divide-border/60">
                {report.evidence.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setSelected(item)
                      setEvidenceOpen(true)
                    }}
                    className="flex w-full items-start gap-3 py-3 text-left"
                  >
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded border border-border text-muted">
                      <Database size={10} strokeWidth={1.5} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="text-[10px] text-foreground">{item.label}</span>
                        <span className="text-[8px] uppercase tracking-[0.08em] text-[#5f5f64]">
                          {item.kind}
                        </span>
                        <span className="num ml-auto text-[8px] text-[#5f5f64]">
                          {item.as_of}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted">
                        {item.summary}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </Tabs.Panel>

            <Tabs.Panel id="trace" className="min-h-0 flex-1 overflow-y-auto px-5 py-2">
              <TraceList steps={detail!.trace} />
            </Tabs.Panel>
          </Tabs>
        </section>

        <aside className="hidden w-[330px] shrink-0 flex-col border-l border-border/60 lg:flex">
          <div className="min-h-0 flex-1">
            <ChatPanel messages={detail!.chat ?? []} onSend={sendChat} />
          </div>
          {chatError ? (
            <p className="border-t border-border/60 px-3 py-2 text-[9px] text-danger">{chatError}</p>
          ) : null}
          <div className="shrink-0 border-t border-border/60 px-4 py-3">
            <div className="grid grid-cols-2 gap-y-1.5 text-[9px] text-muted">
              <span>模型</span>
              <span className="num truncate text-right text-[#a8a8ad]">{run.model}</span>
              <span>数据</span>
              <span
                className={`text-right ${
                  qualityTone(report.data_quality) === 'positive'
                    ? 'text-[var(--success)]'
                    : 'text-[var(--warning)]'
                }`}
              >
                {report.data_quality}
              </span>
              <span>Tokens</span>
              <span className="num text-right text-[#a8a8ad]">
                {run.prompt_tokens + run.completion_tokens}
              </span>
              <span>成本</span>
              <span className="num text-right text-[#a8a8ad]">
                {run.cost_usd > 0 ? `$${run.cost_usd.toFixed(4)}` : '—'}
              </span>
            </div>
          </div>
        </aside>
      </div>

      <EvidenceDrawer evidence={selected} open={evidenceOpen} onOpenChange={setEvidenceOpen} />
    </div>
  )
}
