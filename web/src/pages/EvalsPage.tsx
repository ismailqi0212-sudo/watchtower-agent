import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Chip, Spinner } from '@heroui/react'
import { Activity, CheckCircle2, FlaskConical, Play, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import type { BacktestSummary, EvalSummary } from '../types'
import { ActionChip } from '../components/ActionChip'
import { formatPct, percent } from '../lib/format'

function Metric({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: string
  hint: string
  tone?: 'default' | 'success' | 'danger'
}) {
  return (
    <div className="min-w-0 border-r border-border/60 px-4 py-3 last:border-r-0">
      <p className="text-[9px] text-muted">{label}</p>
      <p
        className={`num mt-1 text-[18px] ${
          tone === 'success'
            ? 'text-[var(--success)]'
            : tone === 'danger'
              ? 'text-[var(--danger)]'
              : 'text-foreground'
        }`}
      >
        {value}
      </p>
      <p className="mt-0.5 truncate text-[8px] text-[#5f5f64]">{hint}</p>
    </div>
  )
}

function ComparisonBar({
  agent,
  baseline,
}: {
  agent: number
  baseline: number
}) {
  const max = Math.max(agent, baseline, 0.01)
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between text-[9px]">
        <span className="text-muted">Agent 方向命中</span>
        <span className="num text-[var(--success)]">{percent(agent)}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[#1b1b1d]">
        <div className="h-full rounded-full bg-[var(--success)]" style={{ width: `${(agent / max) * 100}%` }} />
      </div>
      <div className="mt-2 flex items-center justify-between text-[9px]">
        <span className="text-muted">永远做多基线</span>
        <span className="num text-[#a8a8ad]">{percent(baseline)}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[#1b1b1d]">
        <div className="h-full rounded-full bg-[#55555a]" style={{ width: `${(baseline / max) * 100}%` }} />
      </div>
      <p className="mt-2 text-[8px] leading-4 text-muted">
        基线 = 在同样的历史窗口里，每次都当作看多。Agent 的命中率高于基线，才说明方向判断有一点统计优势。
      </p>
    </div>
  )
}

export function EvalsPage() {
  const [evalData, setEvalData] = useState<EvalSummary | null>(null)
  const [backtest, setBacktest] = useState<BacktestSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const noticeTimer = useRef<number | null>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [evalRes, btRes] = await Promise.all([api.getEval(), api.getBacktest()])
      setEvalData(evalRes)
      setBacktest(btRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    return () => {
      if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    }
  }, [])

  const showNotice = (message: string) => {
    setNotice(message)
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    noticeTimer.current = window.setTimeout(() => setNotice(''), 4000)
  }

  const runGolden = async () => {
    setRunning('golden')
    setError('')
    try {
      const data = await api.runEval()
      setEvalData(data)
      showNotice(`已重新跑流程质检：${data.cases} 个固定场景，结果可复现`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '评测失败')
    } finally {
      setRunning('')
    }
  }

  const runBacktest = async () => {
    setRunning('backtest')
    setError('')
    try {
      const data = await api.runBacktest()
      setBacktest(data)
      showNotice(`已重新跑历史信号：${data.signals} 条固定样本，结果可复现`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '回测失败')
    } finally {
      setRunning('')
    }
  }

  const evalReady = evalData?.available !== false
  const btReady = backtest?.available !== false
  const agentRate = backtest?.direction_hit_rate ?? 0
  const baselineRate = backtest?.always_long_hit_rate ?? 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 px-6">
        <div className="flex items-baseline gap-2">
          <h1 className="text-[15px] font-normal tracking-[-0.02em]">质量评测</h1>
          <span className="text-[10px] text-muted">不是收益预测，是 Agent 的流程质检</span>
          <Chip size="sm" variant="soft" className="h-5 px-1.5 text-[8px] text-muted">
            固定 fixtures
          </Chip>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            className="h-8 gap-1.5 border border-border bg-transparent px-3 text-[10px] font-light"
            onPress={runGolden}
            isDisabled={!!running}
          >
            {running === 'golden' ? <Spinner size="sm" color="current" /> : <FlaskConical size={12} strokeWidth={1.5} />}
            重新跑流程质检
          </Button>
          <Button
            size="sm"
            className="h-8 gap-1.5 bg-foreground px-3 text-[10px] font-normal text-background"
            onPress={runBacktest}
            isDisabled={!!running}
          >
            {running === 'backtest' ? <Spinner size="sm" color="current" /> : <Activity size={12} strokeWidth={1.5} />}
            重新跑历史信号
          </Button>
        </div>
      </div>

      {error ? (
        <div className="border-b border-border/60 px-6 py-2">
          <Alert status="danger" className="py-1.5">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title className="text-[10px]">{error}</Alert.Title>
            </Alert.Content>
          </Alert>
        </div>
      ) : null}
      {notice ? (
        <div className="border-b border-border/60 px-6 py-2">
          <p className="flex items-center gap-1.5 text-[9px] text-[var(--success)]">
            <CheckCircle2 size={11} />
            {notice}
          </p>
        </div>
      ) : null}

      <div className="shrink-0 border-b border-border/60 px-6 py-3">
        <p className="max-w-[900px] text-[10px] leading-5 text-[#b8b8bd]">
          这页回答两个问题：<span className="text-foreground">Agent 有没有按规矩做事？</span>（取数、证据、格式）
          以及<span className="text-foreground">历史信号有没有一点统计优势？</span>（方向命中 vs 永远做多）。
          结果使用固定样本，所以每次运行都会一样；这是可复现性，不是 bug，也不代表未来收益。
        </p>
      </div>

      <div className="grid shrink-0 grid-cols-3 border-b border-border/60 xl:grid-cols-6">
        <Metric
          label="流程通过"
          value={evalReady ? percent(evalData?.pass_rate) : '—'}
          hint={`${evalData?.passed ?? 0} / ${evalData?.cases ?? 0} 个场景`}
          tone={evalReady && (evalData?.pass_rate ?? 0) >= 0.9 ? 'success' : 'default'}
        />
        <Metric
          label="取数完整"
          value={evalReady ? percent(evalData?.required_tool_coverage) : '—'}
          hint="该调的工具都调了吗"
        />
        <Metric
          label="结论有据"
          value={evalReady ? percent(evalData?.evidence_coverage) : '—'}
          hint="每条结论有 evidence 吗"
        />
        <Metric
          label="格式合规"
          value={evalReady ? percent(evalData?.schema_validity) : '—'}
          hint="输出契约是否合格"
        />
        <Metric
          label="5 日方向命中"
          value={btReady ? percent(agentRate) : '—'}
          hint={`${backtest?.signals ?? 0} 条信号 · 基线 ${percent(baselineRate)}`}
          tone={btReady && agentRate > baselineRate ? 'success' : 'default'}
        />
        <Metric
          label="平均超额"
          value={btReady ? formatPct(backtest?.avg_excess_return_pct) : '—'}
          hint="相对沪深300"
          tone={btReady && (backtest?.avg_excess_return_pct ?? 0) >= 0 ? 'success' : 'danger'}
        />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center text-[11px] text-muted">
          <Spinner size="sm" color="current" />
          <span className="ml-2">加载评测</span>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-2">
          <section className="flex min-h-0 flex-col border-b border-border/60 xl:border-b-0 xl:border-r">
            <div className="flex h-12 shrink-0 items-start justify-between border-b border-border/60 px-4 py-2">
              <div>
                <p className="text-[11px] text-foreground">流程质检</p>
                <p className="mt-0.5 text-[8px] text-muted">固定 8 个场景 · 看 Agent 是否按流程做事</p>
              </div>
              <span className="num text-[8px] text-muted">{evalData?.generated_at?.slice(0, 16) ?? '—'}</span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              <div className="mb-3 grid grid-cols-3 gap-2">
                {[
                  ['工具', '该调的工具都调了吗'],
                  ['证据', '每条结论有来源吗'],
                  ['格式', '输出字段是否完整'],
                ].map(([title, hint]) => (
                  <div key={title} className="rounded border border-border/60 px-2 py-1.5">
                    <p className="text-[9px] text-foreground">{title}</p>
                    <p className="mt-0.5 text-[8px] text-muted">{hint}</p>
                  </div>
                ))}
              </div>
              {!evalReady ? (
                <p className="px-2 py-6 text-[10px] text-muted">{evalData?.message ?? '还没有评测结果。'}</p>
              ) : (
                <div className="overflow-hidden rounded border border-border/60">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-border/60">
                        <th className="px-2.5 py-2 text-[8px] font-normal text-muted">场景</th>
                        <th className="w-[64px] px-2 py-2 text-[8px] font-normal text-muted">动作</th>
                        <th className="w-[58px] px-2 py-2 text-[8px] font-normal text-muted">证据</th>
                        <th className="w-[58px] px-2 py-2 text-[8px] font-normal text-muted">结果</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evalData?.results.map((item) => (
                        <tr key={item.id} className="border-b border-border/40 last:border-0">
                          <td className="px-2.5 py-2">
                            <p className="text-[9px] text-[#d6d6da]">{item.id}</p>
                            <p className="mt-0.5 truncate text-[8px] text-muted">{item.label}</p>
                          </td>
                          <td className="px-2 py-2"><ActionChip action={item.action} /></td>
                          <td className="num px-2 py-2 text-[9px] text-[#a8a8ad]">{percent(item.evidence_coverage)}</td>
                          <td className="px-2 py-2">
                            <span className={`text-[9px] ${item.passed ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>
                              {item.passed ? '通过' : '需复核'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>

          <section className="flex min-h-0 flex-col">
            <div className="flex h-12 shrink-0 items-start justify-between border-b border-border/60 px-4 py-2">
              <div>
                <p className="text-[11px] text-foreground">历史信号</p>
                <p className="mt-0.5 text-[8px] text-muted">固定 54 条样本 · 看方向判断有没有统计优势</p>
              </div>
              <span className="num text-[8px] text-muted">{backtest?.generated_at?.slice(0, 16) ?? '—'}</span>
            </div>
            {btReady ? (
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <ComparisonBar agent={agentRate} baseline={baselineRate} />
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="rounded border border-border/60 px-2 py-1.5">
                    <p className="text-[8px] text-muted">信号数</p>
                    <p className="num mt-1 text-[14px]">{backtest?.signals}</p>
                  </div>
                  <div className="rounded border border-border/60 px-2 py-1.5">
                    <p className="text-[8px] text-muted">买入后 5 日均值</p>
                    <p className="num mt-1 text-[14px] text-[var(--success)]">
                      {formatPct(backtest?.buy_signal_avg_forward_return_pct)}
                    </p>
                  </div>
                  <div className="rounded border border-border/60 px-2 py-1.5">
                    <p className="text-[8px] text-muted">中性区间准确</p>
                    <p className="num mt-1 text-[14px]">{percent(backtest?.neutral_band_accuracy)}</p>
                  </div>
                </div>
                <div className="mt-4 overflow-hidden rounded border border-border/60">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-border/60">
                        <th className="px-2.5 py-2 text-[8px] font-normal text-muted">日期</th>
                        <th className="px-2 py-2 text-[8px] font-normal text-muted">股票</th>
                        <th className="w-[62px] px-2 py-2 text-[8px] font-normal text-muted">动作</th>
                        <th className="w-[54px] px-2 py-2 text-[8px] font-normal text-muted">5 日</th>
                        <th className="w-[54px] px-2 py-2 text-[8px] font-normal text-muted">超额</th>
                        <th className="w-[48px] px-2 py-2 text-[8px] font-normal text-muted">结果</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtest?.results.slice(0, 12).map((row) => (
                        <tr key={`${row.date}-${row.symbol}`} className="border-b border-border/40 last:border-0">
                          <td className="num px-2.5 py-2 text-[8px] text-muted">{row.date}</td>
                          <td className="px-2 py-2 text-[9px] text-foreground">{row.name}</td>
                          <td className="px-2 py-2"><ActionChip action={row.action} /></td>
                          <td className={`num px-2 py-2 text-[9px] ${row.forward_return_pct >= 0 ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>
                            {formatPct(row.forward_return_pct)}
                          </td>
                          <td className={`num px-2 py-2 text-[9px] ${row.excess_return_pct >= 0 ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>
                            {formatPct(row.excess_return_pct)}
                          </td>
                          <td className={`px-2 py-2 text-[8px] ${row.outcome === 'hit' ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>
                            {row.outcome === 'hit' ? '命中' : '未命中'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[8px] leading-4 text-muted">
                  命中规则：buy/add 看未来 5 日上涨；reduce/sell 看下跌；hold/watch 看是否落在 ±2% 中性区间。
                </p>
              </div>
            ) : (
              <p className="px-4 py-6 text-[10px] text-muted">{backtest?.message ?? '还没有回测结果。'}</p>
            )}
          </section>
        </div>
      )}

      <div className="flex shrink-0 items-center justify-between border-t border-border/60 px-6 py-2 text-[8px] leading-4 text-[#5f5f64]">
        <span>{backtest?.methodology ?? '方向命中率只统计有方向的信号；hold/watch 单独按中性区间评估。'}</span>
        <button
          type="button"
          onClick={() => { void runGolden(); void runBacktest() }}
          disabled={!!running}
          className="flex items-center gap-1.5 text-[8px] text-muted hover:text-foreground disabled:opacity-30"
        >
          <RefreshCw size={10} />
          全部重跑
        </button>
      </div>
    </div>
  )
}
