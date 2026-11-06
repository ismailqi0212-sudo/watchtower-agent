import { useEffect, useRef, useState } from 'react'
import { Button, Chip, Input, Spinner } from '@heroui/react'
import { Send } from 'lucide-react'
import type { ChatMessage } from '../types'

const SUGGESTIONS = ['为什么是这个动作？', '止损位和失效条件？', '主要风险有哪些？']

export function ChatPanel({
  messages,
  onSend,
}: {
  messages: ChatMessage[]
  onSend: (message: string) => Promise<void>
}) {
  const [value, setValue] = useState('')
  const [sending, setSending] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = listRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages.length, sending])

  const submit = async (text?: string) => {
    const message = (text ?? value).trim()
    if (!message || sending) return
    setValue('')
    setSending(true)
    try {
      await onSend(message)
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="flex h-full min-h-0 flex-col border-t border-border/60">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-border/60 px-4">
        <span className="text-[11px] text-foreground">追问</span>
        <Chip size="sm" variant="soft" className="h-5 px-1.5 text-[8px] text-muted">
          基于当前报告
        </Chip>
      </div>

      <div ref={listRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="space-y-2">
            <p className="text-[11px] leading-5 text-muted">可以继续问结论依据、止损或风险。</p>
            <div className="flex flex-col items-start gap-1.5">
              {SUGGESTIONS.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => submit(item)}
                  className="rounded-md border border-border px-2 py-1 text-[10px] text-muted transition-colors hover:border-[#3a3a3d] hover:text-foreground"
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-2 ${message.role === 'user' ? 'justify-end' : ''}`}
            >
              {message.role === 'assistant' ? (
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-[7px] text-muted">
                  WT
                </span>
              ) : null}
              <p
                className={`max-w-[92%] whitespace-pre-wrap text-[11px] leading-5 ${
                  message.role === 'user'
                    ? 'rounded-lg bg-[#171718] px-2.5 py-1.5 text-foreground'
                    : 'text-[#c7c7cb]'
                }`}
              >
                {message.content}
              </p>
            </div>
          ))
        )}
        {sending ? (
          <div className="flex items-center gap-2">
            <span className="flex size-5 items-center justify-center rounded-full border border-border text-[7px] text-muted">
              WT
            </span>
            <span className="flex gap-1">
              <span className="thinking-dot" />
              <span className="thinking-dot" />
              <span className="thinking-dot" />
            </span>
          </div>
        ) : null}
      </div>

      <form
        className="flex shrink-0 items-center gap-2 border-t border-border/60 p-3"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <Input
          aria-label="追问"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="继续问这张卡片"
          className="h-9 flex-1 border-border bg-[#0b0b0c] text-[11px]"
        />
        <Button
          isIconOnly
          type="submit"
          size="sm"
          className="size-9 min-w-9 bg-foreground text-background"
          isDisabled={sending || !value.trim()}
          aria-label="发送"
        >
          {sending ? <Spinner size="sm" color="current" /> : <Send size={13} strokeWidth={1.6} />}
        </Button>
      </form>
    </section>
  )
}
