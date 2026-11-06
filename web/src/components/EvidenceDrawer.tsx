import { Chip, Drawer } from '@heroui/react'
import { Database } from 'lucide-react'
import type { Evidence } from '../types'

export function EvidenceDrawer({
  evidence,
  open,
  onOpenChange,
}: {
  evidence: Evidence | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Drawer.Backdrop isOpen={open} onOpenChange={onOpenChange}>
      <Drawer.Content placement="right">
        <Drawer.Dialog className="w-full max-w-[440px]">
          <Drawer.CloseTrigger />
          <Drawer.Header>
            <div className="flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-md border border-border bg-[#111112] text-muted">
                <Database size={14} strokeWidth={1.5} />
              </span>
              <div>
                <Drawer.Heading className="text-[13px] font-normal">
                  {evidence?.label ?? '证据'}
                </Drawer.Heading>
                {evidence?.kind ? (
                  <Chip size="sm" variant="soft" className="mt-1 h-4 px-1.5 text-[8px] text-muted">
                    {evidence.kind}
                  </Chip>
                ) : null}
              </div>
            </div>
          </Drawer.Header>
          <Drawer.Body className="gap-4">
            <p className="text-[12px] leading-6 text-[#d5d5d8]">{evidence?.summary}</p>
            <div className="grid grid-cols-[52px_1fr] gap-x-3 gap-y-2 rounded-md border border-border p-3 text-[10px]">
              <span className="text-muted">ID</span>
              <span className="num break-all text-[#bdbdc1]">{evidence?.id}</span>
              <span className="text-muted">日期</span>
              <span className="num text-[#bdbdc1]">{evidence?.as_of || '—'}</span>
            </div>
            <div>
              <p className="mb-2 text-[9px] tracking-[0.14em] text-muted">原始数据</p>
              <pre className="max-h-[420px] overflow-auto rounded-md border border-border bg-[#080809] p-3 text-[9px] leading-5 text-[#9b9ba0]">
                {JSON.stringify(evidence?.payload ?? {}, null, 2)}
              </pre>
            </div>
          </Drawer.Body>
        </Drawer.Dialog>
      </Drawer.Content>
    </Drawer.Backdrop>
  )
}
