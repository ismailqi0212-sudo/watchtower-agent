import type { Action, DataQuality } from '../types'

export const ACTION_LABELS: Record<Action, string> = {
  buy: '买入',
  add: '加仓',
  hold: '持有',
  reduce: '减仓',
  sell: '卖出',
  watch: '观望',
  avoid: '回避',
}

export const ACTION_SHORT: Record<Action, string> = {
  buy: 'BUY',
  add: 'ADD',
  hold: 'HOLD',
  reduce: 'TRIM',
  sell: 'SELL',
  watch: 'WATCH',
  avoid: 'AVOID',
}

export const QUALITY_LABELS: Record<string, string> = {
  ok: '数据完整',
  partial: '部分缺失',
  stale: '数据过期',
  missing: '数据缺失',
}

export function actionTone(action?: string): string {
  if (!action) return 'neutral'
  if (action === 'buy' || action === 'add') return 'positive'
  if (action === 'reduce' || action === 'sell' || action === 'avoid') return 'negative'
  return 'neutral'
}

export function qualityTone(quality?: DataQuality | string): string {
  if (quality === 'ok') return 'positive'
  if (quality === 'partial') return 'warning'
  return 'negative'
}

export function formatPct(value?: number | null, digits = 1): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}%`
}

export function formatPrice(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  return value.slice(0, 10)
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatLatency(ms?: number | null): string {
  if (ms === undefined || ms === null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function percent(value?: number | null, digits = 0): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}
