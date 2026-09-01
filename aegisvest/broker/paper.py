"""PaperBroker — 모의투자 가상 원장. 근거: report/phase-3 §7.

체결가는 호출자(파이프라인)가 공급 (신호 다음 미국장 개장가). 소수점 주식 허용.
비용: 수수료 PAPER_COMMISSION_PCT, 환전 스프레드 PAPER_FX_SPREAD_PCT (config 노브).
LLM 관여 0.
"""

from __future__ import annotations

from aegisvest.config import get_settings
from aegisvest.schemas import (
    Contribution,
    ExecutionResult,
    Fill,
    NavPoint,
    Order,
    PaperPortfolio,
    PaperPosition,
)


def nav_usd(pf: PaperPortfolio, prices: dict[str, float]) -> float:
    """호출자는 보유 티커 전부의 체결가를 공급해야 한다.
    ponytail: 누락 시 avg_cost 로 대체 — 파이프라인 실수로 NAV 가 유령 급락하는 것만 막는다.
    """
    equity = sum(
        p.shares * prices.get(t, p.avg_cost_usd) for t, p in pf.positions.items() if p.shares > 0
    )
    return pf.cash_usd + equity


def add_contribution(
    pf: PaperPortfolio, krw: float, fx_rate_base: float, date: str
) -> Contribution:
    """KRW 입금 → 환전 스프레드 반영 후 USD 로 현금에 추가. fx_rate_base: 시장 KRW/USD."""
    eff_rate = fx_rate_base * (1.0 + get_settings().paper_fx_spread_pct)  # 살 때 불리하게
    usd = krw / eff_rate
    c = Contribution(date=date, krw=round(krw, 2), usd=round(usd, 2), fx_rate=round(eff_rate, 4))
    pf.contributions.append(c)
    pf.cash_usd += usd
    return c


def _order_shares(o: Order, price: float, held: float) -> float:
    s = o.shares if o.shares is not None else (o.notional_usd or 0.0) / price
    return min(s, held) if o.side == "sell" else s


def _buy(pf: PaperPortfolio, o: Order, px: float, comm_pct: float) -> Fill | None:
    pos = pf.positions.get(o.ticker, PaperPosition(shares=0.0, avg_cost_usd=0.0))
    shares = _order_shares(o, px, pos.shares)
    notional = shares * px
    if notional * (1.0 + comm_pct) > pf.cash_usd + 1e-6:  # 현금 한도로 축소
        shares = max(0.0, pf.cash_usd / (px * (1.0 + comm_pct)))
        notional = shares * px
    if shares <= 1e-9:
        return None
    comm = notional * comm_pct
    pf.cash_usd -= notional + comm
    total = pos.shares + shares
    pos.avg_cost_usd = (pos.shares * pos.avg_cost_usd + notional) / total
    pos.shares = total
    pos.category = o.category or pos.category
    pos.sector = o.sector or pos.sector
    pf.positions[o.ticker] = pos
    return Fill(
        ticker=o.ticker,
        side="buy",
        shares=round(shares, 6),
        price_usd=round(px, 4),
        commission_usd=round(comm, 4),
        notional_usd=round(notional, 2),
    )


def _sell(pf: PaperPortfolio, o: Order, px: float, comm_pct: float) -> Fill | None:
    pos = pf.positions.get(o.ticker)
    if pos is None:
        return None
    shares = _order_shares(o, px, pos.shares)
    if shares <= 1e-9:
        return None
    notional = shares * px
    comm = notional * comm_pct
    pf.cash_usd += notional - comm
    pos.shares -= shares
    if pos.shares <= 1e-9:
        pf.positions.pop(o.ticker, None)
    else:
        pf.positions[o.ticker] = pos
    return Fill(
        ticker=o.ticker,
        side="sell",
        shares=round(shares, 6),
        price_usd=round(px, 4),
        commission_usd=round(comm, 4),
        notional_usd=round(notional, 2),
    )


def execute(pf: PaperPortfolio, orders: list[Order], prices: dict[str, float]) -> ExecutionResult:
    """매도 먼저 체결(현금 확보) → 매수. 체결가 없거나 현금 부족은 skipped."""
    comm_pct = get_settings().paper_commission_pct
    fills: list[Fill] = []
    skipped: list[str] = []

    for side, handler in (("sell", _sell), ("buy", _buy)):
        for o in orders:
            if o.side != side:
                continue
            px = prices.get(o.ticker)
            if px is None or px <= 0:
                skipped.append(o.ticker)
                continue
            fill = handler(pf, o, px, comm_pct)
            if fill is None:
                skipped.append(o.ticker)
            else:
                fills.append(fill)

    return ExecutionResult(
        fills=fills,
        total_commission_usd=round(sum(f.commission_usd for f in fills), 4),
        cash_after_usd=round(pf.cash_usd, 2),
        skipped=sorted(set(skipped)),
    )


def mark_to_market(
    pf: PaperPortfolio, prices: dict[str, float], date: str, fx_rate: float
) -> NavPoint:
    """일일 종가 평가 → history 에 append (같은 날짜는 갱신)."""
    n = nav_usd(pf, prices)
    point = NavPoint(date=date, nav_usd=round(n, 2), nav_krw=round(n * fx_rate, 2))
    if pf.history and pf.history[-1].date == date:
        pf.history[-1] = point
    else:
        pf.history.append(point)
    return point
