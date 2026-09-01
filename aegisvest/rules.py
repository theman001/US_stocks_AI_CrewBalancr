"""config/*.yaml 를 Pydantic 으로 검증해 로드한다. 임계값의 단일 진입점.

각 룰셋은 `report/` 명세를 코드로 옮긴 것 — 값 변경 시 명세도 갱신할 것.
"""

from __future__ import annotations

from functools import lru_cache

import yaml
from pydantic import BaseModel

from aegisvest.config import CONFIG_DIR


class FiveLevel(BaseModel):
    """5단계 신호 임계값. p2>p1>z0>n1 이면 상향, 역이면 하향(값이 낮을수록 +) 신호."""

    p2: float
    p1: float
    z0: float
    n1: float


class VixAxis(BaseModel):
    calm_max: float
    stress_max: float


class BreadthAxis(BaseModel):
    strong_min: float
    weak_max: float


class YieldAxis(BaseModel):
    deep_inversion_bp: float
    deepening_4w_bp: float
    resteepen_4w_bp: float


class CreditAxis(BaseModel):
    calm_max_bp: float
    stress_max_bp: float
    spike_4w_bp: float


class EconomyAxis(BaseModel):
    wei: FiveLevel
    regional: FiveLevel
    claims_3m: FiveLevel


class Axes(BaseModel):
    # spx_trend 축은 config 임계값이 없다 (0 = "+2도 -2도 아님"). phase-2 §1 "±2% 횡보"는
    # 점수에 영향 없어 별도 파라미터를 두지 않는다.
    vix: VixAxis
    breadth: BreadthAxis
    yield_policy: YieldAxis
    credit: CreditAxis
    economy: EconomyAxis


class Label(BaseModel):
    bull_min: int
    bear_max: int


class Crisis(BaseModel):
    vix_max: float
    vix_1d_spike_pct: float
    hy_oas_max_bp: float
    spx_below_200sma_frac: float
    exit_score_smooth_min: float
    exit_trading_days: int


class RegimeRules(BaseModel):
    ema_span: int
    min_axes_for_label: int
    axes: Axes
    label: Label
    crisis: Crisis


@lru_cache(maxsize=8)
def _load(name: str) -> dict[str, object]:
    data = yaml.safe_load((CONFIG_DIR / name).read_text())
    if not isinstance(data, dict):
        msg = f"{name}: 최상위가 매핑이 아님"
        raise ValueError(msg)
    return data


@lru_cache(maxsize=1)
def regime_rules() -> RegimeRules:
    return RegimeRules.model_validate(_load("regime_rules.yaml"))


# ─────────────────────── 스크리닝 필터 (3a-5) ───────────────────────


class FilterSpec(BaseModel):
    """하드 필터 하나. `ref` 가 있으면 다른 필드와 비교 (roic > wacc_est)."""

    field: str
    op: str  # ">=" | "<=" | ">" | "<" | "between" | "in" | "ne"
    value: float | int | list[float] | list[str] | str | None = None
    ref: str | None = None
    optional: bool = False  # True 면 데이터 없을 때 통과, False 면 탈락
    note: str = ""


class CategoryFilters(BaseModel):
    category: str
    hard_filters: list[FilterSpec]


class ScoringComponent(BaseModel):
    """스코어 구성요소. metrics 각각을 percentile rank 로 정규화 후 방향 적용."""

    name: str
    weight: float
    metrics: list[str]
    directions: list[int]  # +1 = 높을수록 좋음, -1 = 낮을수록 좋음
    llm_fed: bool = False  # True 면 theme_strength_overrides 로 주입 (기본 중립 0.5)


class SubtierRule(BaseModel):
    name: str
    filters: list[FilterSpec]  # 전부 만족하면 이 서브티어


class CategoryScoring(BaseModel):
    category: str
    max_positions: int
    components: list[ScoringComponent]
    subtiers: list[SubtierRule]


@lru_cache(maxsize=8)
def category_filters(category: str) -> CategoryFilters:
    return CategoryFilters.model_validate(_load(f"filters/{category.lower()}.yaml"))


@lru_cache(maxsize=8)
def category_scoring(category: str) -> CategoryScoring:
    return CategoryScoring.model_validate(_load(f"scoring/{category.lower()}.yaml"))
