import { useMemo, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { Alert, Button, Chip, Spinner, Table } from '@heroui/react'
import {
  ArrowDownRight,
  ArrowUpRight,
  Plus,
  RefreshCw,
  Play,
} from 'lucide-react'
import { api } from '../lib/api'
import { useWorkspace } from '../lib/workspace'
import { ActionChip } from '../components/ActionChip'
import { EmptyState } from '../components/EmptyState'
import { Sparkline } from '../components/Sparkline'
import { formatDate, formatPct, formatPrice } from '../lib/format'
import type { Stock } from '../types'

type Filter = 'all' | 'bullish' | 'bearish' | 'watch' | 'pending'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'bullish', label: '偏多' },
  { key: 'bearish', label: '偏空' },
  { key: 'watch', label: '观望' },
  { key: 'pending', label: '未分析' },
]

function isBullish(stock: Stock) {
  return stock.latest_report?.action === 'buy' || stock.latest_report?.action === 'add'
}

function isBearish(stock: Stock) {
  return (
    stock.latest_report?.action === 'reduce' ||
    stock.latest_report?.action === 'sell' ||
    stock.latest_report?.action === 'avoid'
  )
}

function StockPreview({
  stock,
  analyzing,
  onOpen,
  onAnalyze,
}: {
  stock: Stock | null
  analyzing: string
  onOpen: () => void
  onAnalyze: () => void
}) {
  if (!stock) {
    return (
      <aside className="hidden w-[340px] shrink-0 border-l border-border/60 xl:flex xl:flex-col">
        <div className="flex h-full items-center justify-center px-8 text-center text-[11px] leading-5 text-muted">
          选择一只股票查看最新复盘
        </div>
      </aside>
    )
  }

  const report = stock.latest_report
  const change = stock.quote?.change_pct ?? 0

  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l border-border/60 xl:flex">
      <div className="border-b border-border/60 px-5 py-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[9px] tracking-[0.12em] text-muted">最新复盘</p>
            <h2 className="mt-1.5 text-[17px] font-normal tracking-[-0.02em]">{stock.name}</h2>
            <p className="num mt-0.5 text-[9px] text-muted">{stock.symbol}</p>
          </div>
          <ActionChip action={report?.action} />
        </div>
        <div className="mt-5 flex items-end justify-between">
          <span className="num text-[27px] leading-none text-foreground">
            {formatPrice(stock.quote?.price)}
          </span>
          <span
            className={`num flex items-center gap-0.5 pb-0.5 text-[10px] ${
              change >= 0 ? 'text-[var(--success)]' : 'text-[var(--danger)]'
            }`}
          >
            {change >= 0 ? (
              <ArrowUpRight size={11} strokeWidth={1.5} />
            ) : (
              <ArrowDownRight size={11} strokeWidth={1.5} />
            )}
            {formatPct(change, 2)}
          </span>
        </div>
        <div className="mt-4 h-11">
          <Sparkline
            values={stock.sparkline}
            positive={(stock.sparkline.at(-1) ?? 0) >= (stock.sparkline[0] ?? 0)}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {report ? (
          <>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <p className="text-[9px] text-muted">评分</p>
                <p className="num mt-1 text-[16px] text-foreground">{report.score}</p>
              </div>
              <div>
                <p className="text-[9px] text-muted">置信度</p>
                <p className="num mt-1 text-[16px] text-foreground">
                  {(report.confidence * 100).toFixed(0)}%
                </p>
              </div>
              <div>
                <p className="text-[9px] text-muted">更新</p>
                <p className="num mt-1 text-[11px] text-foreground">{formatDate(report.as_of)}</p>
              </div>
            </div>

            <p className="mt-4 line-clamp-4 text-[11px] leading-5 text-[#c5c5ca]">
              {report.summary}
            </p>

            <div className="mt-4 grid grid-cols-2 gap-2">
              <div className="rounded-md border border-border px-2.5 py-2">
                <p className="text-[8px] text-muted">入场</p>
                <p className="num mt-1 text-[10px] text-[#9db9ff]">
                  {formatPrice(report.plan?.entry_low)}
                </p>
              </div>
              <div className="rounded-md border border-border px-2.5 py-2">
                <p className="text-[8px] text-muted">止损</p>
                <p className="num mt-1 text-[10px] text-[var(--danger)]">
                  {formatPrice(report.plan?.stop_loss)}
                </p>
              </div>
              <div className="rounded-md border border-border px-2.5 py-2">
                <p className="text-[8px] text-muted">目标</p>
                <p className="num mt-1 text-[10px] text-[var(--success)]">
                  {formatPrice(report.plan?.target_price)}
                </p>
              </div>
              <div className="rounded-md border border-border px-2.5 py-2">
                <p className="text-[8px] text-muted">仓位</p>
                <p className="num mt-1 text-[10px] text-[var(--warning)]">
                  {report.plan?.position_pct ?? 0}%
                </p>
              </div>
            </div>
          </>
        ) : (
          <p className="text-[11px] leading-5 text-muted">
            还没有复盘。运行一次分析，生成结论、计划和证据。
          </p>
        )}
      </div>

      <div className="border-t border-border/60 p-4">
        <Button
          fullWidth
          className="h-9 bg-foreground text-[11px] font-normal text-background"
          onPress={report ? onOpen : onAnalyze}
          isDisabled={analyzing === stock.symbol}
        >
          {analyzing === stock.symbol ? (
            <Spinner size="sm" color="current" />
          ) : report ? null : (
            <Play size={12} strokeWidth={1.6} />
          )}
          {analyzing === stock.symbol ? '分析中' : report ? '打开完整复盘' : '开始分析'}
        </Button>
      </div>
    </aside>
  )
}

export function DashboardPage() {
  const navigate = useNavigate()
  const { openAdd } = useOutletContext<{ openAdd: () => void }>()
  const { stocks, loading, refreshing, refresh } = useWorkspace()
  const [filter, setFilter] = useState<Filter>('all')
  const [selectedSymbol, setSelectedSymbol] = useState('')
  const [analyzing, setAnalyzing] = useState('')
  const [bulk, setBulk] = useState(false)
  const [bulkDone, setBulkDone] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const counts = useMemo(
    () => ({
      all: stocks.length,
      bullish: stocks.filter(isBullish).length,
      bearish: stocks.filter(isBearish).length,
      watch: stocks.filter(
        (stock) =>
          stock.latest_report?.action === 'hold' ||
          stock.latest_report?.action === 'watch',
      ).length,
      pending: stocks.filter((stock) => !stock.latest_report).length,
    }),
    [stocks],
  )

  const filtered = useMemo(() => {
    if (filter === 'bullish') return stocks.filter(isBullish)
    if (filter === 'bearish') return stocks.filter(isBearish)
    if (filter === 'watch')
      return stocks.filter(
        (stock) =>
          stock.latest_report?.action === 'hold' ||
          stock.latest_report?.action === 'watch',
      )
    if (filter === 'pending') return stocks.filter((stock) => !stock.latest_report)
    return stocks
  }, [stocks, filter])

  const selectedStock =
    stocks.find((stock) => stock.symbol === selectedSymbol) ??
    filtered[0] ??
    stocks[0] ??
    null

  const runOne = async (symbol: string) => {
    if (analyzing || bulk) return
    setAnalyzing(symbol)
    setError('')
    setNotice('')
    try {
      const detail = await api.analyze(symbol)
      await refresh()
      navigate(`/runs/${detail.run.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败')
    } finally {
      setAnalyzing('')
    }
  }

  const runAll = async () => {
    if (bulk || analyzing || stocks.length === 0) return
    setBulk(true)
    setBulkDone(0)
    setError('')
    setNotice('')
    let done = 0
    try {
      for (const stock of stocks) {
        await api.analyze(stock.symbol)
        done += 1
        setBulkDone(done)
      }
      await refresh()
      setNotice(`已完成 ${done} 只自选股复盘`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '批量分析失败')
    } finally {
      setBulk(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 px-6">
        <div className="flex items-baseline gap-2">
          <h1 className="text-[15px] font-normal tracking-[-0.02em]">自选股</h1>
          <span className="num text-[10px] text-muted">{stocks.length}</span>
          {refreshing ? <span className="text-[10px] text-muted">更新中</span> : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            className="h-8 border border-border bg-transparent px-3 text-[11px] font-light"
            onPress={runAll}
            isDisabled={bulk || !!analyzing || stocks.length === 0}
          >
            {bulk ? <Spinner size="sm" color="current" /> : <RefreshCw size={13} strokeWidth={1.5} />}
            {bulk ? `${bulkDone}/${stocks.length}` : '全部复盘'}
          </Button>
          <Button
            size="sm"
            className="h-8 bg-foreground px-3 text-[11px] font-normal text-background"
            onPress={openAdd}
          >
            <Plus size={13} strokeWidth={1.6} />
            添加自选
          </Button>
        </div>
      </div>

      <div className="flex h-11 shrink-0 items-center gap-1 border-b border-border/60 px-6">
        {FILTERS.map((item) => {
          const active = filter === item.key
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setFilter(item.key)
                setSelectedSymbol('')
              }}
              className={`flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[10px] transition-colors ${
                active
                  ? 'bg-[#171718] text-foreground'
                  : 'text-muted hover:bg-[#101012] hover:text-foreground'
              }`}
            >
              {item.label}
              <span className="num text-[9px] text-[#5f5f64]">{counts[item.key]}</span>
            </button>
          )
        })}
        <span className="ml-auto text-[10px] text-muted">
          截至 {stocks[0]?.quote?.as_of ?? '—'}
        </span>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto px-6 py-3">
          {error ? (
            <Alert status="danger" className="mb-3 py-2">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title className="text-[11px]">{error}</Alert.Title>
              </Alert.Content>
            </Alert>
          ) : null}
          {notice ? (
            <div className="mb-3 flex items-center justify-between rounded-md border border-[#1e3327] bg-[#0d1711] px-3 py-2 text-[10px] text-[var(--success)]">
              {notice}
              <button type="button" className="text-[10px] text-muted" onClick={() => setNotice('')}>
                关闭
              </button>
            </div>
          ) : null}

          {loading ? (
            <div className="space-y-2">
              {[0, 1, 2, 3, 4, 5].map((item) => (
                <div key={item} className="h-12 animate-pulse rounded-md bg-[#101012]" />
              ))}
            </div>
          ) : stocks.length === 0 ? (
            <EmptyState
              title="还没有自选股"
              description="添加一只股票，生成第一张带证据的复盘卡片。"
              action={
                <Button
                  size="sm"
                  className="h-8 bg-foreground px-3 text-[11px] font-normal text-background"
                  onPress={openAdd}
                >
                  <Plus size={13} strokeWidth={1.6} />
                  添加自选
                </Button>
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState title="这个筛选下没有股票" description="切换到「全部」查看完整自选股。" />
          ) : (
            <Table className="stock-table">
              <Table.ScrollContainer>
                <Table.Content
                  aria-label="自选股列表"
                  className="min-w-[700px]"
                  onRowAction={(key) => setSelectedSymbol(String(key))}
                >
                  <Table.Header>
                    <Table.Column isRowHeader className="w-[210px]">
                      股票
                    </Table.Column>
                    <Table.Column className="w-[100px]">现价</Table.Column>
                    <Table.Column className="w-[80px]">涨跌</Table.Column>
                    <Table.Column className="w-[130px]">20 日走势</Table.Column>
                    <Table.Column className="w-[105px]">评分</Table.Column>
                    <Table.Column className="w-[75px]">动作</Table.Column>
                    <Table.Column className="w-[85px] text-right">操作</Table.Column>
                  </Table.Header>
                  <Table.Body>
                    {filtered.map((stock) => {
                      const report = stock.latest_report
                      const change = stock.quote?.change_pct ?? 0
                      const positive =
                        (stock.sparkline.at(-1) ?? 0) >= (stock.sparkline[0] ?? 0)
                      const selected = selectedStock?.symbol === stock.symbol
                      return (
                        <Table.Row
                          key={stock.symbol}
                          className={selected ? 'bg-[#101012]' : undefined}
                          onClick={() => setSelectedSymbol(stock.symbol)}
                        >
                          <Table.Cell>
                            <button
                              type="button"
                              onClick={() => setSelectedSymbol(stock.symbol)}
                              className="flex min-w-0 items-center gap-2.5 text-left"
                            >
                              <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-[#101012] text-[9px] text-muted">
                                {stock.name.slice(0, 1)}
                              </span>
                              <span className="min-w-0">
                                <span className="block truncate text-[12px] text-foreground">
                                  {stock.name}
                                </span>
                                <span className="mt-0.5 flex items-center gap-1.5">
                                  <span className="num text-[9px] text-muted">{stock.symbol}</span>
                                  <span className="text-[9px] text-[#55555a]">{stock.industry}</span>
                                </span>
                              </span>
                            </button>
                          </Table.Cell>
                          <Table.Cell>
                            <span className="num text-[13px] text-foreground">
                              {formatPrice(stock.quote?.price)}
                            </span>
                          </Table.Cell>
                          <Table.Cell>
                            <span
                              className={`num flex items-center gap-0.5 text-[10px] ${
                                change >= 0 ? 'text-[var(--success)]' : 'text-[var(--danger)]'
                              }`}
                            >
                              {change >= 0 ? (
                                <ArrowUpRight size={11} strokeWidth={1.5} />
                              ) : (
                                <ArrowDownRight size={11} strokeWidth={1.5} />
                              )}
                              {formatPct(change, 2)}
                            </span>
                          </Table.Cell>
                          <Table.Cell>
                            <div className="w-[112px] opacity-90">
                              <Sparkline values={stock.sparkline} positive={positive} />
                            </div>
                          </Table.Cell>
                          <Table.Cell>
                            {report ? (
                              <div className="flex items-center gap-2">
                                <span className="num w-5 text-[13px] text-foreground">
                                  {report.score}
                                </span>
                                <span className="h-1 w-10 overflow-hidden rounded-full bg-[#1c1c1f]">
                                  <span
                                    className="block h-full rounded-full bg-[#8f8f94]"
                                    style={{ width: `${report.score}%` }}
                                  />
                                </span>
                              </div>
                            ) : (
                              <span className="text-[10px] text-muted">—</span>
                            )}
                          </Table.Cell>
                          <Table.Cell>
                            <ActionChip action={report?.action} />
                          </Table.Cell>
                          <Table.Cell>
                            <div className="flex items-center justify-end">
                              {report ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-7 px-2 text-[10px] font-light text-muted hover:text-foreground"
                                  onPress={() => navigate(`/runs/${report.run_id}`)}
                                >
                                  查看
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  className="h-7 bg-foreground px-2.5 text-[10px] font-normal text-background"
                                  onPress={() => runOne(stock.symbol)}
                                  isDisabled={!!analyzing || bulk}
                                >
                                  {analyzing === stock.symbol ? (
                                    <Spinner size="sm" color="current" />
                                  ) : (
                                    <Play size={11} strokeWidth={1.6} />
                                  )}
                                  分析
                                </Button>
                              )}
                            </div>
                          </Table.Cell>
                        </Table.Row>
                      )
                    })}
                  </Table.Body>
                </Table.Content>
              </Table.ScrollContainer>
            </Table>
          )}
        </div>

        <StockPreview
          stock={selectedStock}
          analyzing={analyzing}
          onOpen={() => {
            if (selectedStock?.latest_report?.run_id) {
              navigate(`/runs/${selectedStock.latest_report.run_id}`)
            }
          }}
          onAnalyze={() => {
            if (selectedStock) void runOne(selectedStock.symbol)
          }}
        />
      </div>

      <div className="flex h-8 shrink-0 items-center justify-between border-t border-border/60 px-6 text-[9px] text-[#5c5c61]">
        <span>
          {filtered.length} 只 · 数据截至 {stocks[0]?.quote?.as_of ?? '—'}
        </span>
        <Chip size="sm" variant="soft" className="h-4 px-1.5 text-[8px] text-muted">
          {refreshing ? '同步中' : '已同步'}
        </Chip>
      </div>
    </div>
  )
}
