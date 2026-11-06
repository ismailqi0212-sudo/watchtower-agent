import { useState } from 'react'
import { Button, Drawer, Input } from '@heroui/react'
import { Plus } from 'lucide-react'
import { useWorkspace } from '../lib/workspace'

const QUICK = ['600519', '300750', '000001', '601318']

export function AddStockDrawer({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { addStock } = useWorkspace()
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    const symbol = value.trim()
    if (!symbol || saving) return
    setSaving(true)
    setError('')
    try {
      await addStock(symbol)
      setValue('')
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer.Backdrop isOpen={open} onOpenChange={onOpenChange}>
      <Drawer.Content placement="right">
        <Drawer.Dialog className="w-full max-w-[420px]">
          <Drawer.CloseTrigger />
          <Drawer.Header>
            <Drawer.Heading className="text-[15px] font-normal">添加自选股</Drawer.Heading>
          </Drawer.Header>
          <Drawer.Body className="gap-4">
            <p className="text-[11px] leading-5 text-muted">
              输入股票代码或名称。演示环境内置 6 只 A 股样本。
            </p>
            <Input
              autoFocus
              aria-label="股票代码或名称"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void submit()
              }}
              placeholder="例如 600519 或 贵州茅台"
              className="h-10 border-border bg-[#0b0b0c] text-[12px]"
            />
            <div>
              <p className="mb-2 text-[9px] tracking-[0.14em] text-muted">快速添加</p>
              <div className="flex flex-wrap gap-1.5">
                {QUICK.map((item) => (
                  <Button
                    key={item}
                    size="sm"
                    variant="secondary"
                    className="h-7 border border-border bg-transparent px-2.5 text-[10px] font-light"
                    onPress={() => setValue(item)}
                  >
                    {item}
                  </Button>
                ))}
              </div>
            </div>
            {error ? <p className="text-[10px] text-danger">{error}</p> : null}
          </Drawer.Body>
          <Drawer.Footer>
            <Button slot="close" variant="ghost" className="h-8 text-[11px]">
              取消
            </Button>
            <Button
              onPress={submit}
              isDisabled={saving || !value.trim()}
              className="h-8 bg-foreground px-4 text-[11px] font-normal text-background"
            >
              <Plus size={13} strokeWidth={1.6} />
              {saving ? '添加中' : '添加'}
            </Button>
          </Drawer.Footer>
        </Drawer.Dialog>
      </Drawer.Content>
    </Drawer.Backdrop>
  )
}
