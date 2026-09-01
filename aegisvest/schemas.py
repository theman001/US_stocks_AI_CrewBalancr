"""공유 Pydantic 스키마 — 열거형과 기본 타입.

각 빌드 단계가 자신의 모델을 여기에 추가한다 (add-tool / add-agent 스킬 참조).
숫자 필드는 항상 툴 출처를 추적할 수 있어야 한다 (Metric).
"""

from __future__ import annotations

from enum import StrEnum

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
    eps_growth_fwd: float | None
    eps_revision_3m: str | None = Field(description="up | flat | down")
    fcf_ttm_usd: float | None
    fcf_payout: float | None
    eps_payout: float | None
    net_debt_ebitda: float | None
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
