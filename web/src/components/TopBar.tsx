import { useLocation, useNavigate } from 'react-router-dom'
import { Chip, Tabs } from '@heroui/react'
import { BookOpen, Circle, Radar } from 'lucide-react'
import { useWorkspace } from '../lib/workspace'

export function TopBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { health } = useWorkspace()
  const selected = location.pathname.startsWith('/research')
    ? 'research'
    : location.pathname.startsWith('/evals')
      ? 'evals'
      : 'review'
  const providerLabel =
    health?.provider === 'multi'
      ? 'A 股 + 美股'
      : health?.provider === 'akshare'
        ? 'A 股 · AKShare'
        : health?.provider === 'nasdaq'
          ? '美股 · Nasdaq'
          : health?.provider === 'yfinance'
            ? '美股 · yfinance'
            : '演示数据'

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/70 px-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 md:hidden">
          <Radar size={15} strokeWidth={1.5} />
          <span className="text-[12px]">Watchtower</span>
        </div>
        <Tabs
          selectedKey={selected}
          onSelectionChange={(key) =>
            navigate(key === 'research' ? '/research' : key === 'evals' ? '/evals' : '/')
          }
          className="w-[248px]"
        >
          <Tabs.ListContainer className="border border-border/70 bg-[#0b0b0c] p-0.5">
            <Tabs.List aria-label="主导航" className="gap-0.5">
              <Tabs.Tab id="review" className="h-7 px-3 text-[11px]">
                复盘
                <Tabs.Indicator />
              </Tabs.Tab>
              <Tabs.Tab id="research" className="h-7 px-3 text-[11px]">
                研究
                <Tabs.Indicator />
              </Tabs.Tab>
              <Tabs.Tab id="evals" className="h-7 px-3 text-[11px]">
                评测
                <Tabs.Indicator />
              </Tabs.Tab>
            </Tabs.List>
          </Tabs.ListContainer>
        </Tabs>
      </div>

      <div className="flex items-center gap-2">
        <Chip
          size="sm"
          variant="soft"
          className="h-6 gap-1.5 border border-border/70 bg-transparent px-2 text-[9px] text-muted"
        >
          <Circle size={5} fill="var(--success)" strokeWidth={0} />
          {providerLabel}
        </Chip>
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="flex h-7 items-center gap-1.5 rounded-md px-2 text-[10px] text-muted transition-colors hover:bg-[#111112] hover:text-foreground"
        >
          <BookOpen size={12} strokeWidth={1.5} />
          API
        </a>
      </div>
    </header>
  )
}
