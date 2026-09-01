"""파생 재무 지표 계산 — Piotroski F, Altman Z, 배당 연속증배·성장률.

순수 함수. 정규화된 연간 수치(최신이 [0])를 받는다. 원자료 부족 시 None.
FMP fundamentals.py 가 파싱해서 여기로 넘긴다.
"""

from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel


class AnnualFinancials(BaseModel):
    """한 회계연도. 결측은 None. fundamentals.py 가 FMP 3개 재무제표에서 채운다."""

    total_assets: float | None = None
    total_liabilities: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    long_term_debt: float | None = None
    retained_earnings: float | None = None
    stockholders_equity: float | None = None
    shares_outstanding: float | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    ebit: float | None = None
    net_income: float | None = None
    operating_cash_flow: float | None = None


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def piotroski_f(years: list[AnnualFinancials]) -> int | None:
    """9점. 최근 2개 회계연도 필요."""
    if len(years) < 2:
        return None
    y0, y1 = years[0], years[1]
    roa0 = _ratio(y0.net_income, y0.total_assets)
    roa1 = _ratio(y1.net_income, y1.total_assets)
    ocf0 = y0.operating_cash_flow
    ltd_ratio0 = _ratio(y0.long_term_debt, y0.total_assets)
    ltd_ratio1 = _ratio(y1.long_term_debt, y1.total_assets)
    cr0 = _ratio(y0.current_assets, y0.current_liabilities)
    cr1 = _ratio(y1.current_assets, y1.current_liabilities)
    gm0 = _ratio(y0.gross_profit, y0.revenue)
    gm1 = _ratio(y1.gross_profit, y1.revenue)
    at0 = _ratio(y0.revenue, y0.total_assets)
    at1 = _ratio(y1.revenue, y1.total_assets)

    checks: list[bool | None] = [
        None if roa0 is None else roa0 > 0,
        None if ocf0 is None else ocf0 > 0,
        None if (roa0 is None or roa1 is None) else roa0 > roa1,
        None if (ocf0 is None or y0.net_income is None) else ocf0 > y0.net_income,
        None if (ltd_ratio0 is None or ltd_ratio1 is None) else ltd_ratio0 < ltd_ratio1,
        None if (cr0 is None or cr1 is None) else cr0 > cr1,
        None
        if (y0.shares_outstanding is None or y1.shares_outstanding is None)
        else y0.shares_outstanding <= y1.shares_outstanding,
        None if (gm0 is None or gm1 is None) else gm0 > gm1,
        None if (at0 is None or at1 is None) else at0 > at1,
    ]
    resolved = [c for c in checks if c is not None]
    if len(resolved) < 6:  # 너무 많이 결측이면 신뢰 불가
        return None
    return sum(1 for c in resolved if c)


def _fill(years: list[AnnualFinancials]) -> AnnualFinancials:
    """years[0] 을 기준으로 None 필드를 다음 연도 값으로 메운 최신 스냅샷."""
    if not years:
        return AnnualFinancials()
    merged = years[0].model_dump()
    for later in years[1:]:
        ld = later.model_dump()
        for k, v in merged.items():
            if v is None and ld.get(k) is not None:
                merged[k] = ld[k]
    return AnnualFinancials(**merged)


def altman_z(years: list[AnnualFinancials], market_cap: float | None) -> float | None:
    """제조업 Z-Score. Z>3 안전, <1.8 위험. 최신 연도 결측 필드는 직전 연도로 보완."""
    y0 = _fill(years)
    ta = y0.total_assets
    if ta is None or ta == 0 or market_cap is None:
        return None
    working_capital = (
        y0.current_assets - y0.current_liabilities
        if y0.current_assets is not None and y0.current_liabilities is not None
        else None
    )
    a = _ratio(working_capital, ta)
    b = _ratio(y0.retained_earnings, ta)
    c = _ratio(y0.ebit, ta)
    d = _ratio(market_cap, y0.total_liabilities)
    e = _ratio(y0.revenue, ta)
    if a is None or b is None or c is None or d is None or e is None:
        return None
    return 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e


def dividend_streak_years(annual_dividends: list[tuple[int, float]]) -> int | None:
    """(연도, 연간배당총액) 리스트 → 연속 증배 연수. 오름차순/내림차순 무관."""
    if len(annual_dividends) < 2:
        return None
    ordered = sorted(annual_dividends, key=lambda x: x[0])  # 연도 오름차순
    streak = 0
    for prev, cur in pairwise(ordered):
        if cur[1] > prev[1] + 1e-9:
            streak += 1
        else:
            streak = 0
    return streak


def mean_roe(years: list[AnnualFinancials], n: int = 5) -> float | None:
    """최근 `n` 개 회계연도 ROE 평균 (net income / stockholders equity)."""
    roes: list[float] = []
    for y in years[:n]:
        ni, eq = y.net_income, y.stockholders_equity
        if ni is not None and eq is not None and eq != 0:
            roes.append(ni / eq)
    return sum(roes) / len(roes) if roes else None


def roic(y0: AnnualFinancials, tax_rate: float = 0.21) -> float | None:
    """NOPAT / 투하자본 근사. 투하자본 = 자기자본 + 장기부채."""
    if y0.ebit is None or y0.stockholders_equity is None:
        return None
    invested = y0.stockholders_equity + (y0.long_term_debt or 0.0)
    if invested <= 0:
        return None
    return y0.ebit * (1.0 - tax_rate) / invested


def dgr(annual_dividends: list[tuple[int, float]], years: int = 5) -> float | None:
    """배당 연복리 성장률 (최근 `years` 년)."""
    if len(annual_dividends) <= years:
        return None
    ordered = sorted(annual_dividends, key=lambda x: x[0])
    latest = ordered[-1][1]
    past = ordered[-1 - years][1]
    if past <= 0 or latest <= 0:
        return None
    return float((latest / past) ** (1 / years) - 1.0)
