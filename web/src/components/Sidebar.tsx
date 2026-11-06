import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, Chip, Input, Skeleton } from '@heroui/react'
import {
  BookOpen,
  ChevronRight,
  LayoutGrid,
  Plus,
  Radar,
  Search,
} from 'lucide-react'
import { api } from '../lib/api'
import { useWorkspace } from '../lib/workspace'
import type { Stock } from '../types'

export function Sidebar({ onAdd }: { onAdd: () => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { stocks, health, loading, refresh } = useWorkspace()
  const [query, setQuery] = useState('')
  const [analyzing, setAnalyzing] = useState('')
  const [error, setError] = useState('')

  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return stocks
    return stocks.filter(
      (stock) =>
        stock.symbol.toLowerCase().includes(value) ||
        stock.name.toLowerCase().includes(value),
    )
  }, [stocks, query])

  const openStock = async (stock: Stock) => {
    if (analyzing) return
    setError('')
    if (stock.latest_report?.run_id) {
      navigate(`/runs/${stock.latest_report.run_id}`)
      return
    }
    setAnalyzing(stock.symbol)
    try {
      const detail = await api.analyze(stock.symbol)
      await refresh()
      navigate(`/runs/${detail.run.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败')
    } finally {
      setAnalyzing('')
    }
  }

  const activeRunId = location.pathname.startsWith('/runs/')
    ? location.pathname.split('/runs/')[1]
    : ''

  return (
    <aside className="hidden h-full w-[148px] shrink-0 flex-col border-r border-border/70 bg-[#080809] md:flex">
      <div className="flex h-14 items-center gap-2.5 px-5">
        <span className="flex size-7 items-center justify-center rounded-md border border-border bg-[#111112] text-foreground">
          <Radar size={15} strokeWidth={1.5} />
        </span>
        <div className="leading-none">
          <p className="text-[11px] font-medium tracking-[-0.02em]">Watchtower</p>
        </div>
      </div>

      <div className="px-3">
        <Button
          fullWidth
          variant="secondary"
          className="h-9 justify-start gap-2 border border-border bg-transparent px-3 text-[12px] font-light text-foreground hover:bg-[#111112]"
          onPress={onAdd}
        >
          <Plus size={14} strokeWidth={1.5} />
          新建
        </Button>
      </div>

      <div className="px-3 pt-4">
        <div className="relative">
          <Search
            size={13}
            strokeWidth={1.5}
            className="pointer-events-none absolute left-2.5 top-1/2 z-10 -translate-y-1/2 text-muted"
          />
          <Input
            aria-label="搜索自选股"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索"
            className="h-8 min-h-8 w-full min-w-0 border-border/70 bg-[#0b0b0c] pl-8 text-[11px] placeholder:text-[#5f5f63]"
          />
        </div>
      </div>

      <button
        type="button"
        onClick={() => navigate('/')}
        className={`mx-2 mt-4 flex items-center gap-2 rounded-md px-3 py-2 text-left transition-colors ${
          location.pathname === '/' ? 'bg-[#151517]' : 'hover:bg-[#101012]'
        }`}
        aria-current={location.pathname === '/' ? 'page' : undefined}
      >
        <LayoutGrid size={12} strokeWidth={1.5} className="text-muted" />
        <span className="flex-1 text-[10px] tracking-[0.08em] text-muted">总览</span>
        <span className="num text-[9px] text-muted">{stocks.length}</span>
        <ChevronRight size={11} strokeWidth={1.5} className="text-[#55555a]" />
      </button>
      <div className="mt-3 px-5 pb-2 text-[9px] tracking-[0.16em] text-muted">自选股</div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        {loading ? (
          <div className="space-y-1.5 px-2">
            {[0, 1, 2, 3, 4].map((item) => (
              <Skeleton key={item} className="h-9 w-full rounded-md" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-3 py-6 text-[11px] leading-5 text-muted">没有匹配的自选股。</p>
        ) : (
          <div className="space-y-0.5">
            {filtered.map((stock) => {
              const isActive = stock.latest_report?.run_id === activeRunId
              return (
                <button
                  key={stock.symbol}
                  type="button"
                  onClick={() => openStock(stock)}
                  className={`group flex w-full items-center gap-2 rounded-md px-3 py-2 text-left transition-colors ${
                    isActive ? 'bg-[#151517]' : 'hover:bg-[#101012]'
                  }`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-[12px] font-normal text-foreground">
                        {stock.name}
                      </span>
                      {analyzing === stock.symbol ? (
                        <span className="text-[9px] text-muted">分析中</span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5">
                      <span className="num text-[9px] text-muted">{stock.symbol}</span>
                      {stock.latest_report ? (
                        <span className="flex items-center gap-1 text-[9px] text-muted">
                          <span
                            className="size-1 rounded-full"
                            style={{
                              background:
                                stock.latest_report.action === 'buy' ||
                                stock.latest_report.action === 'add'
                                  ? 'var(--success)'
                                  : stock.latest_report.action === 'reduce' ||
                                      stock.latest_report.action === 'sell'
                                    ? 'var(--danger)'
                                    : 'var(--warning)',
                            }}
                          />
                          {stock.latest_report.score}
                        </span>
                      ) : (
                        <span className="text-[9px] text-[#5b5b60]">未分析</span>
                      )}
                    </span>
                  </span>
                  <ChevronRight
                    size={12}
                    strokeWidth={1.5}
                    className="text-transparent transition-colors group-hover:text-muted"
                  />
                </button>
              )
            })}
          </div>
        )}
        {error ? <p className="px-3 pt-3 text-[10px] text-danger">{error}</p> : null}
      </div>

      <div className="border-t border-border/70 p-3">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="flex items-center gap-1.5 text-[10px] text-muted">
            <span
              className={`size-1.5 rounded-full ${
                health ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'
              }`}
            />
            {health ? '已连接' : '连接失败'}
          </span>
          <Chip size="sm" variant="soft" className="h-5 px-2 text-[9px] text-muted">
            {health?.mode === 'llm' ? 'LLM' : '演示'}
          </Chip>
        </div>
        <div className="mt-1 space-y-0.5">
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[10px] text-muted transition-colors hover:bg-[#101012] hover:text-foreground"
          >
            <BookOpen size={12} strokeWidth={1.5} />
            API 文档
          </a>
        </div>
      </div>
    </aside>
  )
}
