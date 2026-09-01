"""성과 지표 — equity curve → CAGR / MDD / 변동성 / 샤프 / 소르티노.

시간가중수익률(TWR): 각 구간 수익률을 그날의 입금액으로 보정해 chain. 근거: report/phase-2 §6.2.
순수 함수.
"""

from __future__ import annotations

import datetime as dt
import math
from itertools import pairwise

from aegisvest.schemas import Contribution, NavPoint

_PPY = 252  # 연간 거래일
_RF_ANNUAL = 0.042


def _daily_returns(history: list[NavPoint], contributions: list[Contribution]) -> list[float]:
    cf_by_date: dict[str, float] = {}
    for c in contributions:
        cf_by_date[c.date] = cf_by_date.get(c.date, 0.0) + c.usd
    rets: list[float] = []
    for prev, cur in pairwise(history):
        if prev.nav_usd <= 0:
            continue
        cf = cf_by_date.get(cur.date, 0.0)
        rets.append((cur.nav_usd - cf) / prev.nav_usd - 1.0)
    return rets


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _max_drawdown(rets: list[float]) -> float:
    peak = 1.0
    equity = 1.0
    mdd = 0.0
    for r in rets:
        equity *= 1.0 + r
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1.0)
    return mdd


_MIN_DAYS_ANNUALIZE = 20  # 이보다 짧으면 연율화(CAGR/Sharpe)는 의미 없음 → None

_EMPTY: dict[str, float | int | None] = {
    "n_days": 0,
    "total_return": None,
    "cagr": None,
    "mdd": None,
    "vol": None,
    "sharpe": None,
    "sortino": None,
    "years": None,
}


def performance_stats(
    history: list[NavPoint], contributions: list[Contribution] | None = None
) -> dict[str, float | int | None]:
    """equity curve 성과. 20일 미만이면 연율 지표는 None (total_return·mdd 만)."""
    contributions = contributions or []
    rets = _daily_returns(history, contributions) if len(history) >= 2 else []
    if not rets:
        return {**_EMPTY, "n_days": len(history)}

    twr = 1.0
    for r in rets:
        twr *= 1.0 + r
    total_return = twr - 1.0
    mdd = _max_drawdown(rets)

    if len(rets) < _MIN_DAYS_ANNUALIZE:
        return {
            "n_days": len(history),
            "total_return": round(total_return, 4),
            "cagr": None,
            "mdd": round(mdd, 4),
            "vol": None,
            "sharpe": None,
            "sortino": None,
            "years": None,
        }

    d0 = dt.date.fromisoformat(history[0].date)
    d1 = dt.date.fromisoformat(history[-1].date)
    years = max((d1 - d0).days / 365.25, 1e-6)
    cagr = twr ** (1.0 / years) - 1.0
    vol = _stdev(rets) * math.sqrt(_PPY)
    # 하방편차: 목표수익률 0 기준 sqrt(mean(min(0,r)^2)) — 표본 stdev 로 디민 하지 않음
    downside = math.sqrt(sum(r * r for r in rets if r < 0.0) / len(rets)) * math.sqrt(_PPY)
    sharpe = (cagr - _RF_ANNUAL) / vol if vol > 1e-9 else None
    sortino = (cagr - _RF_ANNUAL) / downside if downside > 1e-9 else None

    return {
        "total_return": round(total_return, 4),
        "n_days": len(history),
        "years": round(years, 3),
        "cagr": round(cagr, 4),
        "mdd": round(mdd, 4),
        "vol": round(vol, 4),
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "sortino": round(sortino, 3) if sortino is not None else None,
    }
