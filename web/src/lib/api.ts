import type {
  BacktestSummary,
  EvalSummary,
  Health,
  ResearchAskResponse,
  ResearchReport,
  ResearchReportSummary,
  ResearchReportVersion,
  ResearchSession,
  ResearchSessionSummary,
  ResearchSnippet,
  RunDetail,
  Stock,
} from '../types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // ignore malformed error bodies
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/health'),
  meta: () => request<Record<string, unknown>>('/api/meta'),
  getStocks: () => request<{ items: Stock[] }>('/api/stocks'),
  addStock: (symbol: string, name?: string) =>
    request<{ item: Stock }>('/api/stocks', {
      method: 'POST',
      body: JSON.stringify({ symbol, name: name || null }),
    }),
  deleteStock: (symbol: string) =>
    request<{ ok: boolean }>(`/api/stocks/${encodeURIComponent(symbol)}`, {
      method: 'DELETE',
    }),
  analyze: (symbol: string) =>
    request<RunDetail>('/api/analyze', {
      method: 'POST',
      body: JSON.stringify({ symbol, trigger: 'manual' }),
    }),
  getRun: (runId: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  listRuns: (symbol?: string) =>
    request<{ items: RunDetail['run'][] }>(
      `/api/runs${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),
  chat: (runId: string, message: string) =>
    request<{ answer: string; messages: RunDetail['chat'] }>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, message }),
    }),
  getEval: () => request<EvalSummary>('/api/evals/latest'),
  runEval: () =>
    request<EvalSummary>('/api/evals/run', {
      method: 'POST',
    }),
  bootstrapResearch: () =>
    request<ResearchSession>('/api/research/bootstrap', { method: 'POST' }),
  getResearchSession: (sessionId: string) =>
    request<ResearchSession>(`/api/research/sessions/${encodeURIComponent(sessionId)}`),
  ensureResearchSession: (symbol: string, name?: string, question?: string) =>
    request<ResearchSession>('/api/research/sessions', {
      method: 'POST',
      body: JSON.stringify({ symbol, name: name || '', question: question || '' }),
    }),
  listResearchSessions: (symbol?: string) =>
    request<{ items: ResearchSessionSummary[] }>(
      `/api/research/sessions${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),
  uploadResearchDocument: async (sessionId: string, file: File, year?: number) => {
    const form = new FormData()
    form.append('file', file)
    if (year) form.append('year', String(year))
    const response = await fetch(`/api/research/sessions/${encodeURIComponent(sessionId)}/documents`, {
      method: 'POST',
      body: form,
    })
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`
      try {
        const body = await response.json()
        message = body.detail || message
      } catch {
        // ignore
      }
      throw new Error(message)
    }
    return (await response.json()) as ResearchSession
  },
  createResearchReport: (
    sessionId: string,
    payload: {
      template: 'brief' | 'full'
      metric_keys: string[]
      message_ids: number[]
      snippets?: ResearchSnippet[]
      title?: string
    },
  ) =>
    request<ResearchReport>(`/api/research/sessions/${encodeURIComponent(sessionId)}/reports`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listResearchReports: (sessionId: string) =>
    request<{ items: ResearchReportSummary[] }>(
      `/api/research/sessions/${encodeURIComponent(sessionId)}/reports`,
    ),
  getResearchReport: (reportId: string) =>
    request<ResearchReport>(`/api/research/reports/${encodeURIComponent(reportId)}`),
  updateResearchReport: (
    reportId: string,
    payload: { title: string; sections: ResearchReport['sections']; note?: string },
  ) =>
    request<ResearchReport>(`/api/research/reports/${encodeURIComponent(reportId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  listResearchReportVersions: (reportId: string) =>
    request<{ items: ResearchReportVersion[] }>(
      `/api/research/reports/${encodeURIComponent(reportId)}/versions`,
    ),
  getResearchReportVersion: (reportId: string, version: number) =>
    request<ResearchReportVersion>(
      `/api/research/reports/${encodeURIComponent(reportId)}/versions/${version}`,
    ),
  restoreResearchReportVersion: (reportId: string, version: number) =>
    request<ResearchReport>(
      `/api/research/reports/${encodeURIComponent(reportId)}/versions/${version}/restore`,
      { method: 'POST' },
    ),
  polishResearchReport: (reportId: string) =>
    request<ResearchReport>(`/api/research/reports/${encodeURIComponent(reportId)}/polish`, {
      method: 'POST',
    }),
  downloadResearchReport: async (reportId: string, title: string) => {
    const response = await fetch(`/api/research/reports/${encodeURIComponent(reportId)}/markdown`)
    if (!response.ok) throw new Error('导出失败')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${title}.md`
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
  confirmResearchCandidates: (sessionId: string, ids: string[]) =>
    request<ResearchSession>(`/api/research/sessions/${encodeURIComponent(sessionId)}/metrics/confirm`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),
  askResearch: (sessionId: string, question: string) =>
    request<ResearchAskResponse>(`/api/research/sessions/${encodeURIComponent(sessionId)}/ask`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  getBacktest: () => request<BacktestSummary>('/api/backtest/latest'),
  runBacktest: () =>
    request<BacktestSummary>('/api/backtest/run', {
      method: 'POST',
    }),
}
