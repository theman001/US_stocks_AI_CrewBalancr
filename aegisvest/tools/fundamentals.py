"""FundamentalsTool — 재무제표 기반 지표 + 파생 스코어. 소스: yfinance. docs/TOOLS.md §2.

FMP 무료 티어가 대부분 종목·엔드포인트를 제한(402)해 yfinance 로 전환 (2026-09).
`Ticker.info` (사전 계산 비율) + `.balance_sheet`/`.income_stmt`/`.cashflow` (5년) + `.dividends`.
파생 지표(Piotroski F / Altman Z / 배당 연속증배)는 `_derived.py` 순수 함수.
`eps_revision_3m`, `credit_rating` 은 소스 없음 → None.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import pandas as pd
import yfinance as yf

from aegisvest.config import get_settings
from aegisvest.schemas import Fundamentals, ToolError
from aegisvest.tools import _derived as dv
from aegisvest.tools._io import cached
from aegisvest.tools._prices import history

_RF = 0.042  # 무위험 이자율 근사 (WACC CAPM)
_ERP = 0.050  # 주식 리스크 프리미엄 근사


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _yield_frac(v: Any) -> float | None:
    """yfinance 1.7 배당수익률은 퍼센트 (ABT 2.28 = 2.28%). /100 → 소수. 비정상값 배제."""
    f = _num(v)
    if f is None or f < 0 or f > 50:
        return None
    return f / 100.0


def _row(df: pd.DataFrame | None, *names: str) -> list[float | None]:
    """재무제표에서 한 항목의 연도별 값 (최신이 [0]). 여러 이름 중 첫 매치."""
    if df is None or df.empty:
        return []
    for name in names:
        if name in df.index:
            return [_num(x) for x in list(df.loc[name])]
    return []


def _at(vals: list[float | None], i: int = 0) -> float | None:
    return vals[i] if len(vals) > i else None


def _median(values: list[float | None]) -> float | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _cagr(latest_first: list[float | None], years: int) -> float | None:
    # 위치 인덱스 유지 — None 을 걸러 압축하면 중간 결측 시 기준연도가 어긋남
    if len(latest_first) <= years:
        return None
    latest, base = latest_first[0], latest_first[years]
    if latest is None or base is None or base <= 0 or latest <= 0:
        return None
    return float((latest / base) ** (1 / years) - 1.0)


def _op_margin_trend(op_income: list[float | None], revenue: list[float | None]) -> str | None:
    """최근 3년 영업이익률 방향. ±1.5%p 이내 변동은 flat (노이즈 허용)."""
    m = [oi / r for oi, r in zip(op_income[:3], revenue[:3], strict=False) if oi is not None and r]
    if len(m) < 3:
        return None
    delta = m[0] - m[2]  # 최신 - 2년전
    if delta > 0.015:
        return "rising"
    if delta < -0.015:
        return "falling"
    return "flat"


def _annuals(bs: pd.DataFrame, inc: pd.DataFrame, cf: pd.DataFrame) -> list[dv.AnnualFinancials]:
    ta = _row(bs, "Total Assets")
    tl = _row(bs, "Total Liabilities Net Minority Interest", "Total Liabilities")
    ca = _row(bs, "Current Assets")
    cl = _row(bs, "Current Liabilities")
    ltd = _row(bs, "Long Term Debt")
    re = _row(bs, "Retained Earnings")
    eq = _row(bs, "Stockholders Equity", "Common Stock Equity")
    shs = _row(inc, "Diluted Average Shares", "Basic Average Shares")
    rev = _row(inc, "Total Revenue", "Operating Revenue")
    gp = _row(inc, "Gross Profit")
    ebit = _row(inc, "EBIT", "Operating Income")
    ni = _row(inc, "Net Income")
    ocf = _row(cf, "Operating Cash Flow")
    n = max((len(x) for x in (ta, rev, ni)), default=0)
    return [
        dv.AnnualFinancials(
            total_assets=_at(ta, i),
            total_liabilities=_at(tl, i),
            current_assets=_at(ca, i),
            current_liabilities=_at(cl, i),
            long_term_debt=_at(ltd, i),
            retained_earnings=_at(re, i),
            stockholders_equity=_at(eq, i),
            shares_outstanding=_at(shs, i),
            revenue=_at(rev, i),
            gross_profit=_at(gp, i),
            ebit=_at(ebit, i),
            net_income=_at(ni, i),
            operating_cash_flow=_at(ocf, i),
        )
        for i in range(n)
    ]


def _annual_dividends(divs: pd.Series) -> list[tuple[int, float]]:
    """(연도, 정규화 연간배당). calendar-year 합산은 지급시기 이동(2017 TCJA 선지급 등)에
    취약 → 연도별 지급액 중앙값 * 정규 지급빈도(전 기간 최빈 연간 지급횟수)로 환산.
    분기·월 배당이면 특별배당 1건은 중앙값이 걸러낸다 (연 1회 배당사는 완화 안 됨)."""
    if divs is None or divs.empty:
        return []
    idx = pd.DatetimeIndex(divs.index)
    this_year = dt.date.today().year
    by_year: dict[int, list[float | None]] = {}
    for y, v in zip(idx.year.tolist(), divs.tolist(), strict=True):
        if y < this_year:
            by_year.setdefault(y, []).append(float(v))
    if not by_year:
        return []
    counts = [len(p) for p in by_year.values()]
    freq = max(sorted(set(counts)), key=counts.count)  # 분기=4 · 월=12 · 반기=2 · 연=1
    return sorted((y, (_median(p) or 0.0) * freq) for y, p in by_year.items())


def _pe_5y_median(inc: pd.DataFrame, ticker: str, ttl: float) -> float | None:
    eps = _row(inc, "Diluted EPS", "Basic EPS")
    if not eps or inc.empty:
        return None
    try:
        px = history(ticker, ttl)["Close"]
    except Exception:
        return None
    idx = pd.DatetimeIndex(px.index)
    pes: list[float | None] = []
    for date, e in zip(inc.columns, eps, strict=False):
        if e is None or e <= 0:
            continue
        d = pd.Timestamp(date, tz=idx.tz)
        near = px[idx <= d]
        if not near.empty:
            pes.append(float(near.iloc[-1]) / e)
    return _median(pes)


def _yf_bundle(ticker: str, ttl: float) -> dict[str, Any]:
    def _fetch() -> dict[str, Any]:
        t = yf.Ticker(ticker)
        return {
            "info": dict(t.info),
            "balance": t.balance_sheet,
            "income": t.income_stmt,
            "cashflow": t.cashflow,
            "dividends": t.dividends,
        }

    return cached(f"yf:fund:{ticker}", ttl, _fetch)


def fundamentals(ticker: str) -> Fundamentals | ToolError:
    """`ticker` 재무 지표 + 파생 스코어. 소스 yfinance (키 불필요)."""
    ticker = ticker.strip().upper()
    if not ticker:
        return ToolError(error="빈 티커", field="ticker")
    ttl = float(get_settings().cache_ttl_hours)
    try:
        b = _yf_bundle(ticker, ttl)
    except Exception as exc:
        return ToolError(error=f"yfinance 조회 실패: {exc}", field="network")

    info: dict[str, Any] = b["info"]
    if not info or _num(info.get("marketCap")) is None:
        return ToolError(error=f"펀더멘털 없음: {ticker}", field="ticker")
    bs, inc, cf = b["balance"], b["income"], b["cashflow"]
    annuals = _annuals(bs, inc, cf)

    market_cap = _num(info.get("marketCap"))
    beta = _num(info.get("beta"))
    revenue = _row(inc, "Total Revenue", "Operating Revenue")
    op_income = _row(inc, "Operating Income", "EBIT")
    eps_diluted = _row(inc, "Diluted EPS", "Basic EPS")
    ebit0 = _at(_row(inc, "EBIT", "Operating Income"))
    int_exp = _at(_row(inc, "Interest Expense"))
    ebitda0 = _at(_row(inc, "EBITDA", "Normalized EBITDA"))
    net_debt0 = _at(_row(bs, "Net Debt"))

    eps_fwd = _num(info.get("forwardEps"))
    eps_ttm = _num(info.get("trailingEps")) or _at(eps_diluted)
    eps_growth_fwd = (
        eps_fwd / eps_ttm - 1.0 if eps_fwd is not None and eps_ttm and eps_ttm > 0 else None
    )
    pe_fwd = _num(info.get("forwardPE"))
    peg = _num(info.get("pegRatio")) or (
        pe_fwd / (eps_growth_fwd * 100.0)
        if pe_fwd is not None and eps_growth_fwd and eps_growth_fwd > 0
        else None
    )

    fcf = _num(info.get("freeCashflow")) or _at(_row(cf, "Free Cash Flow"))
    div_paid = _at(_row(cf, "Cash Dividends Paid", "Common Stock Dividend Paid"))
    fcf_payout = abs(div_paid) / fcf if div_paid is not None and fcf and fcf > 0 else None

    rev_cagr_3y = _cagr(revenue, 3)
    rev_growth_yoy = _num(info.get("revenueGrowth")) or (
        revenue[0] / revenue[1] - 1.0
        if len(revenue) >= 2 and revenue[0] is not None and revenue[1]
        else None
    )
    fcf_margin = fcf / revenue[0] if fcf is not None and revenue and revenue[0] else None
    rule_of_40 = (
        (rev_cagr_3y + fcf_margin) * 100.0
        if rev_cagr_3y is not None and fcf_margin is not None
        else None
    )

    icov = ebit0 / abs(int_exp) if ebit0 is not None and int_exp and abs(int_exp) > 1e-6 else None
    net_debt_ebitda = (
        net_debt0 / ebitda0 if net_debt0 is not None and ebitda0 and ebitda0 > 0 else None
    )
    dte = _num(info.get("debtToEquity"))
    div_by_year = _annual_dividends(b["dividends"])

    return Fundamentals(
        ticker=ticker,
        market_cap_usd=market_cap,
        pe_forward=pe_fwd,
        pe_ttm=_num(info.get("trailingPE")),
        pe_5y_median=_pe_5y_median(inc, ticker, ttl),
        ev_ebitda=_num(info.get("enterpriseToEbitda")),
        peg_forward=peg,
        roe_5y_avg=dv.mean_roe(annuals) or _num(info.get("returnOnEquity")),
        roic=dv.roic(annuals[0]) if annuals else None,
        wacc_est=(_RF + beta * _ERP) if beta is not None else None,
        gross_margin=_num(info.get("grossMargins")),
        op_margin_trend_3y=_op_margin_trend(op_income, revenue),
        rev_cagr_3y=rev_cagr_3y,
        rev_growth_yoy=rev_growth_yoy,
        eps_growth_fwd=eps_growth_fwd,
        eps_revision_3m=None,
        fcf_ttm_usd=fcf,
        fcf_payout=fcf_payout,
        eps_payout=_num(info.get("payoutRatio")),
        net_debt_ebitda=net_debt_ebitda,
        interest_coverage=icov,
        div_streak_years=dv.dividend_streak_years(div_by_year),
        dgr_5y=dv.dgr(div_by_year, 5),
        div_yield=_yield_frac(info.get("dividendYield")),
        div_yield_5y_median=_yield_frac(info.get("fiveYearAvgDividendYield")),
        piotroski_f=dv.piotroski_f(annuals),
        altman_z=dv.altman_z(annuals, market_cap) if annuals else None,
        rule_of_40=rule_of_40,
        eps_positive_years_10=(
            sum(1 for e in eps_diluted if e is not None and e > 0) if eps_diluted else None
        ),
        credit_rating=None,
        sector=info.get("sector"),
        as_of=(str(inc.columns[0].date()) if not inc.empty else dt.date.today().isoformat()),
        debt_to_equity=dte / 100.0 if dte is not None else None,
    )
