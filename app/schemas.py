"""Pydantic contracts shared by the agent, API and frontend."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Action = Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid"]
DataQuality = Literal["ok", "partial", "stale"]

ACTION_LABELS = {
    "buy": "买入",
    "add": "加仓",
    "hold": "持有",
    "reduce": "减仓",
    "sell": "卖出",
    "watch": "观望",
    "avoid": "回避",
}

ACTION_TONE = {
    "buy": "positive",
    "add": "positive",
    "hold": "neutral",
    "watch": "neutral",
    "reduce": "negative",
    "sell": "negative",
    "avoid": "negative",
}


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: str
    label: str
    summary: str
    as_of: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class ThesisItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    evidence_ids: List[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    severity: Literal["low", "medium", "high"] = "medium"
    evidence_ids: List[str] = Field(default_factory=list)


class TradePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    position_pct: Optional[float] = None
    horizon: str = "5d"


class DecisionReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    name: str
    as_of: str
    action: Action
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    summary: str
    thesis: List[ThesisItem] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    plan: TradePlan = Field(default_factory=TradePlan)
    data_quality: DataQuality = "ok"
    evidence: List[Evidence] = Field(default_factory=list)
    validation_notes: List[str] = Field(default_factory=list)
    generated_by: str = "demo-policy"
    disclaimer: str = "仅供研究与演示，不构成投资建议。"


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    step: int
    kind: str
    tool: str = ""
    args: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    latency_ms: int = 0
    summary: str = ""
    error: Optional[str] = None


class RunDetail(BaseModel):
    run: Dict[str, Any]
    report: Optional[Dict[str, Any]] = None
    trace: List[TraceStep] = Field(default_factory=list)
    chat: List[Dict[str, Any]] = Field(default_factory=list)


class StockCreate(BaseModel):
    symbol: str
    name: Optional[str] = None


class AnalyzeRequest(BaseModel):
    symbol: str
    trigger: str = "manual"


class ChatRequest(BaseModel):
    run_id: str
    message: str


class ChatResponse(BaseModel):
    answer: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)


class EvalCaseResult(BaseModel):
    id: str
    symbol: str
    passed: bool
    required_tool_coverage: float
    schema_valid: bool
    action: str
    steps: int
    latency_ms: int
    issues: List[str] = Field(default_factory=list)


class EvalSummary(BaseModel):
    generated_at: str
    mode: str
    cases: int
    passed: int
    pass_rate: float
    required_tool_coverage: float
    schema_validity: float
    action_accuracy: float
    evidence_coverage: float
    avg_latency_ms: float
    p95_latency_ms: float
    results: List[EvalCaseResult] = Field(default_factory=list)


class BacktestSignal(BaseModel):
    date: str
    symbol: str
    action: str
    score: int
    forward_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    outcome: Literal["hit", "miss", "neutral"]


class BacktestSummary(BaseModel):
    generated_at: str
    mode: str
    signals: int
    direction_hit_rate: float
    overall_hit_rate: float = 0.0
    neutral_band_accuracy: float = 0.0
    always_long_hit_rate: float = 0.0
    avg_forward_return_pct: float
    buy_signal_avg_forward_return_pct: float = 0.0
    avg_excess_return_pct: float
    avg_benchmark_return_pct: float
    bullish_signals: int
    bearish_signals: int
    neutral_signals: int
    methodology: str = ""
    results: List[BacktestSignal] = Field(default_factory=list)


class ResearchAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ResearchReportCreate(BaseModel):
    template: str = Field(default="brief", pattern="^(brief|full)$")
    metric_keys: List[str] = Field(default_factory=list, max_length=80)
    message_ids: List[int] = Field(default_factory=list, max_length=40)
    snippets: List[Dict[str, Any]] = Field(default_factory=list, max_length=80)
    title: str = Field(default="", max_length=160)


class ResearchReportUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    sections: List[Dict[str, Any]]
    note: str = Field(default="人工编辑", max_length=120)


class ResearchCandidateConfirm(BaseModel):
    ids: List[str] = Field(default_factory=list, max_length=200)


class ResearchSessionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=120)
    question: str = Field(default="", max_length=500)
