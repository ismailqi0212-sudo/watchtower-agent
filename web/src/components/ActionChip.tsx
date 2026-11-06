import { Chip } from '@heroui/react'
import type { Action } from '../types'
import { ACTION_LABELS } from '../lib/format'

const COLORS: Record<string, 'success' | 'warning' | 'danger' | 'default'> = {
  buy: 'success',
  add: 'success',
  hold: 'warning',
  watch: 'default',
  reduce: 'danger',
  sell: 'danger',
  avoid: 'danger',
}

export function ActionChip({
  action,
  size = 'sm',
  className = '',
}: {
  action?: Action | string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  if (!action) {
    return (
      <Chip size={size} variant="soft" color="default" className={className}>
        未分析
      </Chip>
    )
  }
  return (
    <Chip
      size={size}
      variant="soft"
      color={COLORS[action] ?? 'default'}
      className={className}
    >
      {ACTION_LABELS[action as Action] ?? action}
    </Chip>
  )
}
