"""FundamentalsTool — 재무제표 기반 지표 + 파생 스코어. 소스: FMP **stable** API. docs/TOOLS.md §2.

FMP stable API (`/stable/<ep>?symbol=X`). 필드명은 2026-09 라이브 검증 완료.
파생 지표(Piotroski F / Altman Z / 배당 연속증배·성장률)는 `_derived.py` 순수 함수.
`eps_revision_3m`, `credit_rating` 은 별도 엔드포인트 필요 — 아직 None (3b).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

from aegisvest.config import get_settings
from aegisvest.schemas import Fundamentals, ToolError
from aegisvest.tools import _derived as dv
from aegisvest.tools._io import cached_json

_BASE = "https://financialmodelingprep.com/stable"
_RF = 0.042  # 무위험 이자율 근사 (WACC CAPM)
_ERP = 0.050  # 주식 리스크 프리미엄 근사


def _get(endpoint: str, key: str, **params: Any) -> list[dict[str, Any]]:
    """FMP stable GET. 에러/None 은 빈 리스트로 정규화."""
    data = cached_json(
        f"{_BASE}/{endpoint}",
        {"symbol": params.pop("symbol"), **params, "apikey": key},
        ttl_hours=get_settings().cache_ttl_hours,
    )
    return data if isinstance(data, list) else []


def _row(rows: list[dict[str, Any]], i: int = 0) -> dict[str, Any]:
    return rows[i] if len(rows) > i else {}


def _first(d: dict[str, Any] | None, *names: str) -> Any:
    if not d:
        return None
    for n in names:
        if d.get(n) is not None:
            return d[n]
    return None


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _nums(rows: list[dict[str, Any]], *names: str) -> list[float | None]:
    return [_num(_first(r, *names)) for r in rows]


def _cagr(latest_first: list[float | None], years: int) -> float | None:
    vals = [v for v in latest_first if v is not None]
    if len(vals) <= years or vals[years] <= 0 or vals[0] <= 0:
        return None
    return float((vals[0] / vals[years]) ** (1 / years) - 1.0)


def _op_margin_trend(income: list[dict[str, Any]]) -> str | None:
    margins: list[float] = []
    for i in income[:3]:
        oi = _num(_first(i, "operatingIncome", "ebit"))
        rev = _num(_first(i, "revenue"))
        if oi is not None and rev:
            margins.append(oi / rev)
    if len(margins) < 3:
        return None
    if margins[0] > margins[1] > margins[2]:
        return "rising"
    if margins[0] < margins[1] < margins[2]:
        return "falling"
    return "flat"


def _median(values: list[float | None]) -> float | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _annuals(
    income: list[dict[str, Any]],
    balance: list[dict[str, Any]],
    cashflow: list[dict[str, Any]],
) -> list[dv.AnnualFinancials]:
    """FMP 3개 재무제표를 연도별로 zip. 최신이 [0] (FMP 는 desc 반환)."""
    n = min(len(income), len(balance), len(cashflow))
    out: list[dv.AnnualFinancials] = []
    for i in range(n):
        inc, bal, cf = income[i], balance[i], cashflow[i]
        out.append(
            dv.AnnualFinancials(
                total_assets=_num(_first(bal, "totalAssets")),
                total_liabilities=_num(_first(bal, "totalLiabilities")),
                current_assets=_num(_first(bal, "totalCurrentAssets")),
                current_liabilities=_num(_first(bal, "totalCurrentLiabilities")),
                long_term_debt=_num(_first(bal, "longTermDebt")),
                retained_earnings=_num(_first(bal, "retainedEarnings")),
                stockholders_equity=_num(_first(bal, "totalStockholdersEquity", "totalEquity")),
                shares_outstanding=_num(
                    _first(inc, "weightedAverageShsOutDil", "weightedAverageShsOut")
                ),
                revenue=_num(_first(inc, "revenue")),
                gross_profit=_num(_first(inc, "grossProfit")),
                ebit=_num(_first(inc, "operatingIncome", "ebit")),
                net_income=_num(_first(inc, "netIncome")),
                operating_cash_flow=_num(
                    _first(cf, "operatingCashFlow", "netCashProvidedByOperatingActivities")
                ),
            )
        )
    return out


def _roe_5y_avg(annuals: list[dv.AnnualFinancials]) -> float | None:
    roes: list[float] = []
    for y in annuals[:5]:
        ni, eq = y.net_income, y.stockholders_equity
        if ni is not None and eq is not None and eq != 0:
            roes.append(ni / eq)
    return sum(roes) / len(roes) if roes else None


def _next_fy_estimate(estimates: list[dict[str, Any]]) -> dict[str, Any]:
    """FMP analyst-estimates 는 미래 회계연도들을 반환. 가장 가까운 미래 연도를 고른다."""
    today = dt.date.today().isoformat()
    future = sorted(
        (e for e in estimates if str(e.get("date", "")) >= today),
        key=lambda e: str(e["date"]),
    )
    return future[0] if future else (estimates[0] if estimates else {})


def _annual_dividends(rows: list[dict[str, Any]]) -> list[tuple[int, float]]:
    by_year: dict[int, float] = {}
    for r in rows:
        date = r.get("date") or r.get("paymentDate") or ""
        amt = _num(_first(r, "adjDividend", "dividend"))
        if len(date) >= 4 and amt is not None:
            try:
                yr = int(date[:4])
            except ValueError:
                continue
            by_year[yr] = by_year.get(yr, 0.0) + amt
    this_year = dt.date.today().year
    return sorted((y, v) for y, v in by_year.items() if y < this_year)  # 올해는 불완전


def fundamentals(ticker: str) -> Fundamentals | ToolError:
    """`ticker` 재무 지표 + 파생 스코어. FMP 키 필수."""
    ticker = ticker.strip().upper()
    if not ticker:
        return ToolError(error="빈 티커", field="ticker")
    key = get_settings().fmp_api_key
    if not key:
        return ToolError(error="FMP_API_KEY 미설정", field="FMP_API_KEY")

    try:
        # FMP 무료 티어: 재무제표 limit 최대 5. dividends 는 limit 파라미터가 프리미엄.
        profile = _row(_get("profile", key, symbol=ticker))
        rt = _row(_get("ratios-ttm", key, symbol=ticker))
        km = _row(_get("key-metrics-ttm", key, symbol=ticker))
        income = _get("income-statement", key, symbol=ticker, period="annual", limit=5)
        balance = _get("balance-sheet-statement", key, symbol=ticker, period="annual", limit=5)
        cashflow = _get("cash-flow-statement", key, symbol=ticker, period="annual", limit=5)
        annual_ratios = _get("ratios", key, symbol=ticker, period="annual", limit=5)
        estimates = _get("analyst-estimates", key, symbol=ticker, period="annual")
        dividends = _get("dividends", key, symbol=ticker)
    except Exception as exc:
        return ToolError(error=f"FMP 조회 실패: {exc}", field="network")

    if not profile or _first(profile, "symbol") is None:
        return ToolError(error=f"프로필 없음: {ticker}", field="ticker")

    annuals = _annuals(income, balance, cashflow)
    market_cap = _num(_first(profile, "marketCap"))
    beta = _num(_first(profile, "beta"))
    price = _num(_first(profile, "price"))

    revenues = _nums(income, "revenue")
    eps_hist = _nums(income, "eps", "epsDiluted")
    eps_ttm = eps_hist[0] if eps_hist else None
    eps_fwd = _num(_first(_next_fy_estimate(estimates), "epsAvg"))
    eps_growth_fwd = (
        eps_fwd / eps_ttm - 1.0 if eps_fwd is not None and eps_ttm and eps_ttm > 0 else None
    )
    pe_forward = price / eps_fwd if price is not None and eps_fwd and eps_fwd > 0 else None
    peg_forward = (
        pe_forward / (eps_growth_fwd * 100.0)
        if pe_forward is not None and eps_growth_fwd and eps_growth_fwd > 0
        else None
    )

    # 이자보상: FMP TTM 이 이자비용 ~0 일 때 0 을 반환 → EBIT/이자비용 으로 보정.
    icov = _num(_first(rt, "interestCoverageRatioTTM"))
    int_exp = _num(_first(_row(income), "interestExpense"))
    ebit0 = _num(_first(_row(income), "operatingIncome", "ebit"))
    if (icov is None or icov == 0.0) and ebit0 is not None:
        icov = None if not int_exp or abs(int_exp) < 1e-6 else ebit0 / abs(int_exp)

    fcf = _num(_first(_row(cashflow), "freeCashFlow"))
    div_paid = _num(_first(_row(cashflow), "netDividendsPaid", "commonDividendsPaid"))
    fcf_payout = abs(div_paid) / fcf if div_paid is not None and fcf and fcf > 0 else None
    rev_cagr_3y = _cagr(revenues, 3)
    fcf_margin = fcf / revenues[0] if fcf is not None and revenues and revenues[0] else None
    rule_of_40 = (
        (rev_cagr_3y + fcf_margin) * 100.0
        if rev_cagr_3y is not None and fcf_margin is not None
        else None
    )
    div_by_year = _annual_dividends(dividends)

    return Fundamentals(
        ticker=ticker,
        market_cap_usd=market_cap,
        pe_forward=pe_forward,
        pe_ttm=_num(_first(rt, "priceToEarningsRatioTTM", "priceToEarningsDilutedRatioTTM")),
        pe_5y_median=_median(_nums(annual_ratios, "priceToEarningsRatio")),
        ev_ebitda=_num(_first(km, "evToEBITDATTM")),
        peg_forward=peg_forward,
        roe_5y_avg=_roe_5y_avg(annuals),
        roic=_num(_first(km, "returnOnInvestedCapitalTTM")),
        wacc_est=(_RF + beta * _ERP) if beta is not None else None,
        gross_margin=_num(_first(rt, "grossProfitMarginTTM")),
        op_margin_trend_3y=_op_margin_trend(income),
        rev_cagr_3y=rev_cagr_3y,
        eps_growth_fwd=eps_growth_fwd,
        eps_revision_3m=None,
        fcf_ttm_usd=fcf,
        fcf_payout=fcf_payout,
        eps_payout=_num(_first(rt, "dividendPayoutRatioTTM")),
        net_debt_ebitda=_num(_first(km, "netDebtToEBITDATTM")),
        interest_coverage=icov,
        div_streak_years=dv.dividend_streak_years(div_by_year),
        dgr_5y=dv.dgr(div_by_year, 5),
        div_yield=_num(_first(rt, "dividendYieldTTM")),
        div_yield_5y_median=_median(_nums(annual_ratios, "dividendYield")),
        piotroski_f=dv.piotroski_f(annuals),
        altman_z=dv.altman_z(annuals[0], market_cap) if annuals else None,
        rule_of_40=rule_of_40,
        eps_positive_years_10=(
            sum(1 for e in eps_hist[:10] if e is not None and e > 0) if eps_hist else None
        ),
        credit_rating=None,
        sector=_first(profile, "sector"),
        as_of=str(_first(_row(income), "date") or dt.date.today().isoformat()),
    )
