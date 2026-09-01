"""FundamentalsTool — 재무제표 기반 지표. 소스: FMP. docs/TOOLS.md §2.

FMP v3 엔드포인트 기준. **FMP 키로 라이브 검증 필요** — 필드명은 플랜에 따라 다를 수 있어
방어적으로 파싱한다. 절대 추정하지 않는다 (없으면 None).

3a-2 범위: 단건 조회 엔드포인트(profile / ratios-ttm / key-metrics-ttm / analyst-estimates)
+ income-statement 로 계산 가능한 파생값. 나머지 파생 지표(Piotroski F, Altman Z, 배당
연속증배, 5년 중앙값 등)는 3a-5 스크리너에서 재무제표 3종을 받아 채운다.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

from aegisvest.config import get_settings
from aegisvest.schemas import Fundamentals, ToolError
from aegisvest.tools._io import cached_json

_BASE = "https://financialmodelingprep.com/api/v3"


def _get(path: str, key: str, **params: Any) -> list[dict[str, Any]]:
    """FMP GET. 에러 응답({"Error Message": ...})·None 은 빈 리스트로 정규화."""
    data = cached_json(
        f"{_BASE}/{path}",
        {**params, "apikey": key},
        ttl_hours=get_settings().cache_ttl_hours,
    )
    return data if isinstance(data, list) else []


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


def _cagr(latest_first: list[float | None], years: int) -> float | None:
    """리스트[0] 이 최신. `years` 년 전 대비 연복리 성장률."""
    vals = [v for v in latest_first if v is not None]
    if len(vals) <= years or vals[years] <= 0 or vals[0] <= 0:
        return None
    return float((vals[0] / vals[years]) ** (1 / years) - 1.0)


def _op_margin_trend(latest_first: list[float | None]) -> str | None:
    """리스트[0] 이 최신. 최근 3년 영업이익률 방향."""
    v = [x for x in latest_first[:3] if x is not None]
    if len(v) < 3:
        return None
    if v[0] > v[1] > v[2]:
        return "rising"
    if v[0] < v[1] < v[2]:
        return "falling"
    return "flat"


def fundamentals(ticker: str) -> Fundamentals | ToolError:
    """`ticker` 재무 지표. FMP 키 필수."""
    ticker = ticker.strip().upper()
    if not ticker:
        return ToolError(error="빈 티커", field="ticker")
    key = get_settings().fmp_api_key
    if not key:
        return ToolError(error="FMP_API_KEY 미설정", field="FMP_API_KEY")

    try:
        profile = (_get(f"profile/{ticker}", key) or [{}])[0]
        ratios = (_get(f"ratios-ttm/{ticker}", key) or [{}])[0]
        metrics = (_get(f"key-metrics-ttm/{ticker}", key) or [{}])[0]
        income = _get(f"income-statement/{ticker}", key, period="annual", limit=11) or []
        estimates = _get(f"analyst-estimates/{ticker}", key, period="annual", limit=1) or []
    except Exception as exc:
        return ToolError(error=f"FMP 조회 실패: {exc}", field="network")

    if not profile or _first(profile, "symbol") is None:
        return ToolError(error=f"프로필 없음: {ticker}", field="ticker")

    revenues = [_num(_first(i, "revenue")) for i in income]
    eps_hist = [_num(_first(i, "eps", "epsdiluted")) for i in income]
    op_margins = [_num(_first(i, "operatingIncomeRatio")) for i in income]

    rev_cagr_3y = _cagr(revenues, 3)
    eps_ttm = eps_hist[0] if eps_hist else None
    eps_fwd = _num(_first(estimates[0] if estimates else None, "estimatedEpsAvg"))
    price = _num(_first(profile, "price"))

    eps_growth_fwd = (
        eps_fwd / eps_ttm - 1.0 if eps_fwd is not None and eps_ttm and eps_ttm > 0 else None
    )
    pe_forward = price / eps_fwd if price is not None and eps_fwd and eps_fwd > 0 else None
    peg_forward = (
        pe_forward / (eps_growth_fwd * 100.0)
        if pe_forward is not None and eps_growth_fwd and eps_growth_fwd > 0
        else None
    )

    return Fundamentals(
        ticker=ticker,
        market_cap_usd=_num(_first(profile, "mktCap", "marketCap")),
        pe_forward=pe_forward,
        pe_ttm=_num(_first(ratios, "peRatioTTM", "priceEarningsRatioTTM")),
        pe_5y_median=None,
        ev_ebitda=_num(_first(metrics, "enterpriseValueOverEBITDATTM", "evToEbitdaTTM")),
        peg_forward=peg_forward,
        roe_5y_avg=_num(_first(ratios, "returnOnEquityTTM")),
        roic=_num(_first(metrics, "roicTTM", "returnOnInvestedCapitalTTM")),
        wacc_est=None,
        gross_margin=_num(_first(ratios, "grossProfitMarginTTM")),
        op_margin_trend_3y=_op_margin_trend(op_margins),
        rev_cagr_3y=rev_cagr_3y,
        eps_growth_fwd=eps_growth_fwd,
        eps_revision_3m=None,
        fcf_ttm_usd=_num(_first(metrics, "freeCashFlowTTM")),
        fcf_payout=None,
        eps_payout=_num(_first(ratios, "payoutRatioTTM", "dividendPayoutRatioTTM")),
        net_debt_ebitda=_num(_first(metrics, "netDebtToEBITDATTM")),
        interest_coverage=_num(_first(ratios, "interestCoverageTTM")),
        div_streak_years=None,
        dgr_5y=None,
        div_yield=_num(_first(ratios, "dividendYielTTM", "dividendYieldTTM")),
        div_yield_5y_median=None,
        piotroski_f=None,
        altman_z=None,
        rule_of_40=None,
        eps_positive_years_10=(
            sum(1 for e in eps_hist[:10] if e is not None and e > 0) if eps_hist else None
        ),
        credit_rating=None,
        sector=_first(profile, "sector"),
        as_of=str(_first(income[0] if income else {}, "date") or dt.date.today().isoformat()),
    )
