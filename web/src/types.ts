export type Action =
  | 'buy'
  | 'add'
  | 'hold'
  | 'reduce'
  | 'sell'
  | 'watch'
  | 'avoid'

export type DataQuality = 'ok' | 'partial' | 'stale' | 'missing'

export interface Evidence {
  id: string
  kind: string
  label: string
  summary: string
  as_of: string
  payload: Record<string, unknown>
}

export interface Thesis {
  text: string
  evidence_ids: string[]
}

export interface Risk {
  text: string
  severity: 'low' | 'medium' | 'high'
  evidence_ids: string[]
}

export interface TradePlan {
  entry_low: number | null
  entry_high: number | null
  stop_loss: number | null
  target_price: number | null
  position_pct: number | null
  horizon: string
}

export interface Report {
  id?: string
  run_id?: string
  symbol: string
  name: string
  as_of: string
  action: Action
  score: number
  confidence: number
  summary: string
  thesis: Thesis[]
  risks: Risk[]
  plan: TradePlan
  data_quality: DataQuality
  evidence: Evidence[]
  validation_notes: string[]
  generated_by: string
  disclaimer: string
  markdown?: string
  created_at?: string
}

export interface Run {
  id: string
  symbol: string
  status: 'running' | 'success' | 'partial' | 'failed'
  trigger: string
  started_at: string
  finished_at?: string
  latency_ms: number
  model: string
  mode: string
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
  error?: string
}

export interface TraceStep {
  id: number
  step: number
  kind: string
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
  ok: boolean
  latency_ms: number
  summary: string
  error?: string
}

export interface ChatMessage {
  id: number
  run_id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface RunDetail {
  run: Run
  report: Report | null
  trace: TraceStep[]
  chat: ChatMessage[]
}

export interface Quote {
  symbol?: string
  as_of?: string
  price?: number
  open?: number
  high?: number
  low?: number
  prev_close?: number
  change_pct?: number
  volume?: number
  source?: string
  data_quality?: string
}

export interface LatestReportSummary {
  id: string
  run_id: string
  as_of: string
  action: Action
  action_label: string
  score: number
  confidence: number
  data_quality: DataQuality
  summary: string
  plan: TradePlan
  created_at: string
}

export interface Stock {
  symbol: string
  name: string
  market: string
  industry: string
  created_at: string
  quote: Quote
  sparkline: number[]
  latest_report: LatestReportSummary | null
}

export interface EvalCaseResult {
  id: string
  symbol: string
  label: string
  passed: boolean
  required_tool_coverage: number
  schema_valid: boolean
  action: string
  score: number
  evidence_coverage: number
  data_quality: string
  steps: number
  latency_ms: number
  issues: string[]
}

export interface EvalSummary {
  available: boolean
  generated_at: string
  mode: string
  cases: number
  passed: number
  pass_rate: number
  required_tool_coverage: number
  schema_validity: number
  action_accuracy: number
  evidence_coverage: number
  avg_latency_ms: number
  p95_latency_ms: number
  results: EvalCaseResult[]
  message?: string
}

export interface BacktestSignal {
  date: string
  end_date: string
  symbol: string
  name: string
  action: Action
  score: number
  data_quality: string
  forward_return_pct: number
  benchmark_return_pct: number
  excess_return_pct: number
  outcome: 'hit' | 'miss'
}

export interface BacktestSummary {
  available: boolean
  generated_at: string
  mode: string
  signals: number
  direction_hit_rate: number
  overall_hit_rate: number
  neutral_band_accuracy: number
  always_long_hit_rate: number
  avg_forward_return_pct: number
  buy_signal_avg_forward_return_pct: number
  avg_excess_return_pct: number
  avg_benchmark_return_pct: number
  bullish_signals: number
  bearish_signals: number
  neutral_signals: number
  methodology: string
  results: BacktestSignal[]
  message?: string
}

export interface Health {
  status: string
  mode: string
  model: string
  provider: string
  stocks: number
}


export interface ResearchSource {
  id: string
  name: string
  year: number | null
  research_year?: number | null
  page_count: number
  file_url: string
  page_url: string
}

export interface ResearchCell {
  period: string
  value: number | null
  status: 'verified' | 'missing' | 'needs_review' | string
  page: number | null
  quote: string
  document_id: string
  metric_key?: string
  label?: string
  unit?: string
}

export interface ResearchMetric {
  key: string
  label: string
  unit: string
  cells: Record<string, ResearchCell>
  available: number
  missing: string[]
}

export interface ResearchCandidate {
  id: string
  candidate_id: string
  metric_key: string
  label: string
  unit: string
  period: string
  value: number
  document_id: string
  document_name: string
  page: number
  quote: string
  status: string
}

export interface ResearchCandidateGroup {
  metric_key: string
  label: string
  unit: string
  cells: Record<string, ResearchCandidate>
  periods: string[]
  priority: number
}

export interface ResearchSession {
  id: string
  symbol: string
  name: string
  question: string
  status: string
  created_at: string
  periods: string[]
  sources: ResearchSource[]
  metrics: ResearchMetric[]
  quality: {
    available_cells: number
    expected_cells: number
    citation_rate: number
    missing_cells: number
    verified_cells: number
  }
  cards: unknown[]
  candidates?: ResearchCandidateGroup[]
  messages?: ResearchMessage[]
}


export interface ResearchCitation {
  id: string
  kind: string
  label: string
  summary: string
  as_of: string
  document_id?: string
  page?: number
  quote?: string
  payload: Record<string, any> & {
    document_id?: string
    page?: number
    quote?: string
    metric_key?: string
    period?: string
  }
}

export interface ResearchMessage {
  id: number
  session_id: string
  role: 'user' | 'assistant'
  content: string
  data: {
    citations?: ResearchCitation[]
    artifacts?: { kind: string; title: string; metric_keys?: string[] }[]
    gaps?: string[]
    trace?: Record<string, unknown>[]
    generated_by?: string
    error?: string | null
  }
  created_at: string
}

export interface ResearchAskResponse {
  session_id: string
  user_message: string
  message: ResearchMessage
  answer: string
  citations: ResearchCitation[]
  artifacts: { kind: string; title: string; metric_keys?: string[] }[]
  gaps: string[]
  trace: Record<string, unknown>[]
  generated_by: string
  error?: string | null
}


export interface ResearchSessionSummary {
  id: string
  symbol: string
  name: string
  question: string
  status: string
  created_at: string
  updated_at: string
}


export interface ResearchReportRow {
  key: string
  label: string
  unit: string
  values: Record<string, number | null>
  sources?: Record<string, ResearchCitation | null>
}

export interface ResearchReportSection {
  id: string
  title: string
  kind: 'text' | 'metric_table' | 'list' | 'sources'
  body?: string
  items?: (string | { name: string; year?: number; page_count?: number; file_url?: string })[]
  periods?: string[]
  rows?: ResearchReportRow[]
  citations?: ResearchCitation[]
}

export interface ResearchReport {
  id: string
  session_id: string
  title: string
  template: 'brief' | 'full'
  sections: ResearchReportSection[]
  review: {
    sections: number
    citations: number
    sources: number
    metrics: number
    missing: number
    template: string
    checks: string[]
    edited?: boolean
    polished?: boolean
  }
  version: number
  created_at: string
  updated_at: string
}

export interface ResearchReportSummary {
  id: string
  session_id: string
  title: string
  template: 'brief' | 'full'
  review: ResearchReport['review']
  created_at: string
  updated_at: string
}


export interface ResearchReportVersion {
  id: string
  report_id: string
  version: number
  title: string
  review: ResearchReport['review']
  sections?: ResearchReportSection[]
  note: string
  created_at: string
}


export interface ResearchSnippet {
  id: string
  kind: 'text' | 'metric_table' | 'market_snapshot'
  title: string
  body?: string
  metric_keys?: string[]
  citations: ResearchCitation[]
}
