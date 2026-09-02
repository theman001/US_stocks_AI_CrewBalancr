"""공유 Pydantic 스키마 — 열거형과 기본 타입.

각 빌드 단계가 자신의 모델을 여기에 추가한다 (add-tool / add-agent 스킬 참조).
숫자 필드는 항상 툴 출처를 추적할 수 있어야 한다 (Metric).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Category(StrEnum):
    """리스크 3티어."""

    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class Regime(StrEnum):
    """매크로 레짐 라벨."""

    BULL = "BULL"
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"
    CRISIS = "CRISIS"


class Verdict(StrEnum):
    """Risk Officer 판정 / 일기 채점 결과."""

    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"


class ToolError(BaseModel):
    """툴 실패 반환. 툴은 예외를 raise 하지 않고 이 형태를 반환한다."""

    error: str
    field: str


class Metric(BaseModel):
    """추적 가능한 수치 — 에이전트 출력의 모든 숫자는 이 형태로 출처를 남긴다."""

    name: str
    value: float
    source_tool: str
    source_call_id: str = Field(default="", description="이번 실행의 tool_call_id")


# ─────────────────────── Layer 0 툴 출력 (3a-2) ───────────────────────


class MarketData(BaseModel):
    """MarketDataTool 출력. 가격·이동평균·기술지표. docs/TOOLS.md §1."""

    ticker: str
    last_price: float
    sma_50: float | None
    sma_200: float | None
    sma_50_prev: float | None
    sma_200_prev: float | None
    rsi_14: float | None
    atr_14: float | None
    beta_60m: float | None
    adv_20d_usd: float | None = Field(description="20일 평균 거래대금 (USD)")
    rs_vs_spx_6m: float | None = Field(
        description="6개월 총수익률 - SPX 6개월 총수익률 (소수). 백분위 변환은 ScreenerTool"
    )
    mom_12_1: float | None = Field(description="12개월 - 1개월 수익률 (소수)")
    pct_from_52w_high: float | None = Field(description="52주 고점 대비 (소수, 음수)")
    vol_20d_avg: float | None = Field(description="20일 평균 거래량 (주)")
    vol_ratio_latest: float | None = Field(description="최근 거래량 / 20일 평균")
    as_of: str


class Fundamentals(BaseModel):
    """FundamentalsTool 출력. 재무제표 기반 지표 + 파생 스코어. docs/TOOLS.md §2."""

    ticker: str
    market_cap_usd: float | None
    pe_forward: float | None
    pe_ttm: float | None
    pe_5y_median: float | None
    ev_ebitda: float | None
    peg_forward: float | None
    roe_5y_avg: float | None
    roic: float | None
    wacc_est: float | None
    gross_margin: float | None
    op_margin_trend_3y: str | None = Field(description="rising | flat | falling")
    rev_cagr_3y: float | None
    rev_growth_yoy: float | None = Field(description="최근 회계연도 매출 성장률 (소수)")
    eps_growth_fwd: float | None
    eps_revision_3m: str | None = Field(description="up | flat | down")
    fcf_ttm_usd: float | None
    fcf_payout: float | None
    eps_payout: float | None
    net_debt_ebitda: float | None
    debt_to_equity: float | None = Field(default=None, description="부채/자기자본 (소수)")
    interest_coverage: float | None
    div_streak_years: int | None
    dgr_5y: float | None
    div_yield: float | None
    div_yield_5y_median: float | None
    piotroski_f: int | None
    altman_z: float | None
    rule_of_40: float | None
    eps_positive_years_10: int | None
    credit_rating: str | None
    sector: str | None
    as_of: str


class MacroData(BaseModel):
    """MacroDataTool 출력. 레짐 6축 raw 데이터. docs/TOOLS.md §3.

    단위 규약: *_bp = 베이시스포인트, *_pct / *_change_pct / *_slope* = 소수 비율
    (0.05 = 5%), 지수/레벨 값은 원 단위. RegimeScoreCalculator(3a-3) 는 이 규약을 따른다.
    """

    vix: float | None
    vix3m: float | None
    vix_1d_change_pct: float | None = Field(description="VIX 1일 변화율, 소수 (0.05 = +5%)")
    spx_last: float | None
    spx_sma_200: float | None
    spx_sma_50: float | None
    spx_50_slope_20d: float | None = Field(description="50일 SMA 20일 변화율, 소수")
    pct_above_200dma: float | None = Field(
        description="구성종목 중 200일선 상회 비율, 퍼센트 0~100 (3a-5)"
    )
    pct_above_200dma_4w_change: float | None = Field(
        description="위 값 4주 변화, 퍼센트포인트 (3a-5)"
    )
    yc_10y_3m_bp: float | None
    yc_10y_3m_4w_change_bp: float | None
    yc_10y_3m_prev_bp: float | None
    yc_10y_2y_bp: float | None
    fed_funds_trend: str | None = Field(description="hiking | hold | cutting")
    hy_oas_bp: float | None
    hy_oas_4w_change_bp: float | None
    wei: float | None = Field(description="Weekly Economic Index, 퍼센트 (연율 근사)")
    regional_fed_mfg_avg: float | None = Field(description="지역 연준 제조업 지수 평균, 원 단위")
    claims_4w_trend_pct: float | None = Field(description="IC4WSA 3개월 변화율, 소수 (0.10 = +10%)")
    ism_pmi: float | None
    as_of: str
    stale_fields: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    source: str
    published: str = Field(description="YYYY-MM-DD, 미상이면 빈 문자열")
    url: str
    summary: str = ""


class NewsResult(BaseModel):
    """NewsScraperTool 출력. 스크랩만 — 요약·해석은 에이전트. docs/TOOLS.md §11."""

    scope: str = Field(description="macro | ticker")
    ticker: str | None
    headlines: list[NewsItem]
    as_of: str


# ─────────────────────── 스크리너 (3a-5) ───────────────────────


class FilterCheck(BaseModel):
    """하드 필터 하나의 평가 결과."""

    result: str = Field(description="pass | fail | skip")
    value: float | str | None = None


class ScreenedTicker(BaseModel):
    ticker: str
    passed: bool
    checks: dict[str, FilterCheck]
    subtier: str | None = None  # 스크리너 단계에선 None, ScoringCalculator 가 채움


class ScreenResult(BaseModel):
    """ScreenerTool 출력. docs/TOOLS.md §6."""

    category: str
    passed: list[ScreenedTicker]
    failed_count: int
    evaluated_count: int
    errored: list[str] = Field(default_factory=list, description="데이터 조회 실패 티커")
    as_of: str


class ScoredTicker(BaseModel):
    ticker: str
    score: float = Field(description="0~100 가중 종합 점수")
    rank: int
    subtier: str | None
    component_scores: dict[str, float]


class ScoringResult(BaseModel):
    """ScoringCalculator 출력. docs/TOOLS.md §7."""

    category: str
    scores: list[ScoredTicker]  # score 내림차순
    errored: list[str] = Field(default_factory=list)
    as_of: str


# ─────────────────────── 배분·리밸런싱 (3a-6) ───────────────────────


class AllocationTargets(BaseModel):
    """AllocationTableTool 출력. docs/TOOLS.md §5."""

    score_smooth: float
    crisis: bool
    equity_sleeve_pct: float = Field(description="주식 슬리브 비중 (소수)")
    cash_pct: float
    category_targets_sleeve: dict[str, float] = Field(description="슬리브 100 기준 소수")
    category_targets_total: dict[str, float] = Field(
        description="전체 포트 기준 소수 (low/mid/high)"
    )
    max_positions: dict[str, int]
    interp_anchors: list[int] = Field(description="보간에 쓴 상·하 정수 앵커")
    guardrails: dict[str, float]


class Position(BaseModel):
    ticker: str
    category: str  # low | mid | high (소문자; PM 이 대문자로 내도 clamp_pm_draft 가 정규화)
    weight: float = Field(description="전체 포트 대비 소수")
    sector: str | None = None


class DraftPortfolio(BaseModel):
    """리밸런싱·제약 검증 입력. category_weights 는 low/mid/high/cash."""

    category_weights: dict[str, float]
    positions: list[Position] = Field(default_factory=list)
    prior_category_weights: dict[str, float] = Field(default_factory=dict)


class RebalanceOrder(BaseModel):
    category: str
    amount_usd: float


class RebalancePlan(BaseModel):
    """CashFlowRebalancer 출력. docs/TOOLS.md §8."""

    new_cash_deployable_usd: float
    buys_from_new_cash: list[RebalanceOrder]
    sell_needed: bool
    sell_orders: list[RebalanceOrder]
    cooldown_blocked: list[str]
    post_action_weights: dict[str, float]


class ConstraintViolation(BaseModel):
    rule: str
    detail: str
    value: float


class ConstraintResult(BaseModel):
    """ConstraintChecker 출력. docs/TOOLS.md §9."""

    verdict: str = Field(description="PASS | FAIL")
    violations: list[ConstraintViolation]


# ─────────────────────── PaperBroker (3a-7) ───────────────────────


class PaperPosition(BaseModel):
    shares: float
    avg_cost_usd: float
    category: str | None = None
    sector: str | None = None


class Contribution(BaseModel):
    date: str  # YYYY-MM-DD
    krw: float
    usd: float
    fx_rate: float = Field(description="KRW per USD (환전 스프레드 반영 후)")


class NavPoint(BaseModel):
    date: str
    nav_usd: float
    nav_krw: float


class PaperPortfolio(BaseModel):
    """state/paper_portfolio.json — 모의투자 가상 원장. report/phase-3 §7.1."""

    cash_usd: float = 0.0
    positions: dict[str, PaperPosition] = Field(default_factory=dict)
    contributions: list[Contribution] = Field(default_factory=list)
    history: list[NavPoint] = Field(default_factory=list)
    cooldown_days: dict[str, int] = Field(
        default_factory=dict, description="카테고리→마지막 조정 후 경과 거래일"
    )


class Order(BaseModel):
    """PaperBroker 주문. notional_usd 또는 shares 중 하나 지정."""

    ticker: str
    side: Literal["buy", "sell"]
    notional_usd: float | None = None
    shares: float | None = None
    category: str | None = None
    sector: str | None = None


class Fill(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    shares: float
    price_usd: float
    commission_usd: float
    notional_usd: float


class ExecutionResult(BaseModel):
    fills: list[Fill]
    total_commission_usd: float
    cash_after_usd: float
    skipped: list[str] = Field(default_factory=list, description="체결가 없음/현금 부족")


class BenchmarkState(BaseModel):
    """state/benchmarks.json — 동일 현금흐름 벤치마크 시뮬."""

    holdings: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="benchmark명 → {ticker: shares}"
    )
    pending_usd: dict[str, float] = Field(
        default_factory=dict,
        description="benchmark명 → 가격 결측으로 미체결된 현금 (다음 납입 시 재시도)",
    )
    history: dict[str, list[NavPoint]] = Field(default_factory=dict)


class ShadowState(BaseModel):
    """state/shadow.json — 섀도 A/B. report/phase-3 §7.3.

    deterministic = 순수 결정론 코어. organization = 에이전트 틸트 반영 (3b 부터).
    """

    deterministic: PaperPortfolio = Field(default_factory=PaperPortfolio)
    organization: PaperPortfolio = Field(default_factory=PaperPortfolio)


# ─────────────────────── 레짐 엔진 (3a-3) ───────────────────────


class RegimeHistoryPoint(BaseModel):
    """감시견이 state/regime_history.json 에 누적하는 일별 점수."""

    date: str  # YYYY-MM-DD
    total_score: int


class CrisisState(BaseModel):
    """CRISIS 래치 상태 — 감시견이 state 로 persist. 해제엔 5거래일 경과 필요."""

    active: bool = False
    triggered_date: str | None = None  # 마지막으로 CRISIS 조건이 충족된 날 (YYYY-MM-DD)


class CrisisFlag(BaseModel):
    """state/crisis_flag.json — 감시견이 쓰고 main.py(3a-10)가 읽어 크루를 즉시 실행."""

    active: bool
    reason: str | None = None
    detected_at: str = ""  # YYYY-MM-DD
    cleared_at: str = ""


class RegimeResult(BaseModel):
    """RegimeScoreCalculator 출력. LLM 관여 0. docs/TOOLS.md §4."""

    axis_scores: dict[str, int | None] = Field(
        description="6축(vix/spx_trend/breadth/yield_policy/credit/economy), 각 -2~+2 또는 None"
    )
    economy_subscores: dict[str, int | None] = Field(
        description="wei/regional/claims, 각 -2~+2 또는 None"
    )
    n_axes_present: int = Field(description="점수 계산에 쓰인 축 수 (정규화 분모)")
    low_confidence: bool = Field(
        description="present 축 < min_axes_for_label — 라벨을 NEUTRAL 로 강등"
    )
    total_score: int = Field(description="-12~+12, 데이터 없는 축 제외 후 6축 스케일로 정규화")
    score_smooth: float = Field(description="total_score 의 5일 EMA (adjust=False)")
    regime: Regime
    crisis_active: bool
    crisis_reason: str | None
    crisis_state: CrisisState = Field(description="갱신된 래치 상태 — 호출자가 persist")
    rationale: dict[str, str] = Field(description="축별 임계값 대입 설명")


# ─────────────────────── 사이징·파이프라인 (3a-8) ───────────────────────


class SizedPosition(BaseModel):
    ticker: str
    category: str  # low | mid | high (config·constraints 와 동일 소문자)
    weight: float = Field(description="전체 포트 대비 소수")
    target_usd: float
    score: float
    sector: str | None = None
    atr_pct: float | None = Field(default=None, description="ATR14/종가 — 고위험만")


class SizingResult(BaseModel):
    """PositionSizer 출력 — 카테고리 예산 → 종목별 목표 비중. report/phase-1 §B-3.1."""

    positions: list[SizedPosition]
    category_weights: dict[str, float] = Field(description="low/mid/high/cash 실현 비중")
    budget_shortfall: dict[str, float] = Field(
        default_factory=dict, description="카테고리별 미달분 (현금화, 스필 후 잔여)"
    )
    notes: list[str] = Field(default_factory=list)
    as_of: str


class PipelineResult(BaseModel):
    """run_pipeline() 출력 — 결정론 코어 전체 조립. 에이전트/백테스트가 소비. LLM 관여 0."""

    as_of: str
    nav_usd: float
    macro: MacroData = Field(description="일기 data_snapshot·signal 태깅용 원자료 (Phase 4)")
    regime: RegimeResult
    allocation: AllocationTargets
    screen_counts: dict[str, int]
    scoring: dict[str, ScoringResult]
    rebalance_plan: RebalancePlan
    sizing: SizingResult
    draft: DraftPortfolio
    constraints: ConstraintResult
    orders: list[Order]
    prices: dict[str, float] = Field(description="주문 실행용 — 호출자가 PaperBroker 에 전달")
    notes: list[str] = Field(default_factory=list)


# ─────────────────────── 에이전트 계층 (3a-9) ───────────────────────


class MacroBrief(BaseModel):
    """① Macro Strategist 출력. 해설·판단만 — 배분 숫자 언급 금지. report/phase-3 §3 ①."""

    regime: str
    confidence: str = Field(description="high | medium | low")
    axis_conflicts: list[str] = Field(default_factory=list, description="축 간 상충 서술")
    risk_scenarios: list[str] = Field(default_factory=list, description="향후 2~4주 시나리오")
    watch_items: list[str] = Field(default_factory=list)


class FundamentalNote(BaseModel):
    """② Fundamental Analyst — 종목별 재무 코멘트. report/phase-3 §3 ②."""

    ticker: str
    thesis_1line: str
    quality_flags: list[str] = Field(
        default_factory=list, description="이익 피크아웃·일회성·소송 등"
    )
    valuation_trap: bool = False
    exclude_recommended: bool = False


class FundamentalNotes(BaseModel):
    notes: list[FundamentalNote] = Field(default_factory=list)


class ThematicNote(BaseModel):
    """③ Thematic/Momentum Analyst — HIGH 종목별 테마·촉매·크라우딩. report/phase-3 §3 ③."""

    ticker: str
    themes: list[str] = Field(default_factory=list)
    catalyst: str = ""
    catalyst_date: str | None = None
    crowding_flag: bool = False
    momentum_durability: str = Field(default="med", description="high | med | low")
    theme_strength_adj: float = Field(
        default=0.0, description="스코어 테마강도 조정 권고, -0.2~+0.2 (3b-2 PM 이 적용)"
    )
    exclude_recommended: bool = False


class ThematicNotes(BaseModel):
    notes: list[ThematicNote] = Field(default_factory=list)


class EventRisk(BaseModel):
    event: str
    date: str | None = None
    affected_sleeve: str = Field(default="all", description="low | mid | high | all")
    severity: str = Field(default="medium", description="low | medium | high")


class MarketNarrative(BaseModel):
    """④ News & Sentiment Analyst — 주간 내러티브 + 이벤트 리스크. report/phase-3 §3 ④."""

    weekly_summary: str = ""
    event_risks: list[EventRisk] = Field(default_factory=list)


class SleeveStance(BaseModel):
    stance: str = Field(description="overweight | neutral | underweight")
    reason: str = ""


class ResearchView(BaseModel):
    """⑤ Research Director — 노트 4종 종합 하우스뷰. report/phase-3 §3 ⑤.

    3b-1: 생산만 (PM 미도입). 3b-2 부터 ⑥ PM 이 sleeve_stance 로 ±3%p 틸트.
    """

    sleeve_stance: dict[str, SleeveStance] = Field(default_factory=dict, description="low/mid/high")
    cross_risks: list[str] = Field(default_factory=list)
    excluded_tickers: list[str] = Field(default_factory=list)
    notes: str = ""


class PMDraft(BaseModel):
    """⑥ Portfolio Manager 출력 — 하우스뷰 틸트 반영 초안. report/phase-3 §3 ⑥.

    LLM 이 비중을 제안하나 `agents.pm._clamp_pm` 이 하드 한계로 클램프:
    카테고리 ±3%p, 종목은 스코어 상위 풀(max_positions x1.5) 내, excluded_tickers 강제 제외,
    신규 편입 불가, 티어 밴드·단일종목·고위험캡·현금하한 불가침 (사용자 결정 2026-09-01).
    """

    category_weights: dict[str, float] = Field(description="low/mid/high/cash 제안 비중 (소수)")
    positions: list[Position] = Field(default_factory=list)
    tilt_rationale: str = ""


class RiskReview(BaseModel):
    """⑦ Risk Officer 출력. report/phase-3 §3 ⑦."""

    verdict: str = Field(description="APPROVED | CONDITIONAL | REJECTED")
    conditions: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class CIODecision(BaseModel):
    """⑧ CIO 출력. 승인 또는 보류만 — 주문 수량·비중 불변. report/phase-3 §3 ⑧ + 사용자 결정."""

    verdict: str = Field(description="APPROVED | HOLD")
    ic_memo: str
    concerns: list[str] = Field(default_factory=list)
    hold_reason: str | None = Field(default=None, description="HOLD 시 필수")


class ReviewerOutput(BaseModel):
    """⑨ Performance Reviewer LLM 출력. report/phase-4 §4.1·§4.2.

    사후확신 편향 방지: `missed_signal` / `underestimated_because` / `what_would_change` 를
    강제해 "당시 관점" 으로 서술하게 한다. 점수·verdict 는 건드리지 않는다 (evaluate.py 소관).
    event/theme/mistake 태그는 통제 어휘(config/diary_taxonomy.yaml)에서만 — reviewer.py 가 검증.
    """

    what_happened: str = Field(description="결과 1~2문장, outcome 수치만 인용")
    missed_signal: str = Field(
        description="당시 가용했으나 놓친 신호 (인용). 없었으면 'none: <이유>'"
    )
    underestimated_because: str = Field(description="그 신호를 저평가한 이유")
    what_would_change: str = Field(description="다음에 적용할 구체적 수정 휴리스틱")
    root_cause: str | None = Field(default=None, description="miss/partial 근본 원인, hit 면 null")
    lesson: str = Field(description="일반화 가능한 교훈 한 문장")
    base_rate_note: str = Field(description="유사 셋업 과거 기저율")
    lesson_card: str = Field(description="25 토큰 이내 요약 (reviewer.py 가 절삭)")
    event_tags: list[str] = Field(
        default_factory=list, description="event:* (semi-open, YAML 목록)"
    )
    theme_tags: list[str] = Field(
        default_factory=list, description="theme:* (semi-open, YAML 목록)"
    )
    mistake_tag: str = Field(default="none", description="mistake:* (closed, YAML 목록) 1개")


class CrewOutcome(BaseModel):
    """run_organization() 결과. 3b-2: ① + ②③④ → ⑤ → [⑥ PM ↔ ⑦ Risk (반려 1회)] → ⑧ CIO.

    `org_orders` = PM 틸트 반영 주문 (클램프 후). `rebalance_held` = Risk 2회 REJECTED 또는
    CIO HOLD → 이번 주 매매 스킵. 결정론 코어(run_pipeline)는 그대로 (섀도 A/B 는 3b-3).
    """

    run_id: str
    macro_brief: MacroBrief
    fundamental_notes: FundamentalNotes
    thematic_notes: ThematicNotes
    market_narrative: MarketNarrative
    research_view: ResearchView
    pm_draft: DraftPortfolio | None = None
    risk_review: RiskReview | None = None
    risk_rounds: int = 0
    cio: CIODecision
    org_orders: list[Order] = Field(default_factory=list)
    rebalance_held: bool = False
    diary_ids: list[str] = Field(default_factory=list)
    llm_used: bool = True


class WeeklyRunResult(BaseModel):
    """main.run() 출력 — 주간 크루 1회 실행 요약. 리포트·알림·테스트 공용."""

    run_id: str
    trigger: str = Field(description="scheduled | crisis")
    held: bool = Field(description="CIO HOLD 로 매매 스킵")
    crew_ran: bool
    contribution_usd: float = 0.0
    nav_usd: float
    nav_krw: float
    n_orders: int
    n_fills: int
    regime: str
    crisis_active: bool
    constraints_verdict: str
    cio_verdict: str | None = None
    report_path: str = ""
    diary_ids: list[str] = Field(default_factory=list)


class DiaryEntry(BaseModel):
    """판단 일기 항목. report/phase-4 §2.2. 기록 시점엔 결정·상황만, 결과·교훈은 Phase 4 append."""

    id: str
    run_id: str
    agent: str
    created_at: str  # ISO8601
    claim_type: str  # regime_call | exclusion | cio_override | ...
    claim: str
    reasoning: str
    supporting_refs: list[str] = Field(default_factory=list)
    data_snapshot: dict[str, float | int | str | None] = Field(default_factory=dict)
    decision: dict[str, object] = Field(default_factory=dict)
    horizon_weeks: int
    evaluate_after: list[str] = Field(default_factory=list, description="YYYY-MM-DD 채점 예정일")
    shadow_link: str | None = None
    status: str = "open"
    situation_text: str = ""
    tags: list[str] = Field(default_factory=list)
    # ── Phase 4 append 대상 (기록 시 None) ──
    situation_vector_id: str | None = None
    outcome: dict[str, object] | None = None
    post_mortem: dict[str, object] | None = None  # 4-2 Reviewer: root_cause/lesson/base_rate_note/…
    lesson_card: str | None = None
    lesson_vector_id: str | None = None
    rag_status: str = "pending_schema"
