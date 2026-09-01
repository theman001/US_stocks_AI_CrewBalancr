"""결정론 코어 — 매크로 → 레짐 → 배분 → 스크리닝 → 스코어 → 사이징 → 리밸런싱 → 주문.

근거: report/phase-2 §8.3, phase-3 §4·§9. **LLM 관여 0** — 백테스트(3a-11)가 그대로 재사용.
에이전트 레이어(3a-9+)는 이 결과를 받아 재량 틸트만 얹는다.

run_pipeline() 은 state 를 읽지도 쓰지도 않는다 (호출자가 주입·persist). 실행도 안 한다
(Order 리스트만 반환 → main.py 가 PaperBroker.execute).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from aegisvest.schemas import (
    AllocationTargets,
    CrisisState,
    DraftPortfolio,
    MacroData,
    Order,
    PaperPortfolio,
    PipelineResult,
    Position,
    RegimeHistoryPoint,
    ScoredTicker,
    ScoringResult,
    SizingResult,
    ToolError,
)
from aegisvest.state import load_list, load_model
from aegisvest.tools.allocation import allocation_targets
from aegisvest.tools.breadth import market_breadth
from aegisvest.tools.constraints import check_constraints
from aegisvest.tools.macro_data import macro_data
from aegisvest.tools.market_data import market_data
from aegisvest.tools.portfolio_math import size_positions
from aegisvest.tools.rebalance import cash_flow_rebalance
from aegisvest.tools.regime import regime_score
from aegisvest.tools.scoring import score_category
from aegisvest.tools.screener import screen
from aegisvest.tools.universe import get_universe

_CATS = ("low", "mid", "high")
_MIN_ORDER_USD = 1.0
_log = logging.getLogger("aegisvest.pipeline")


def _prices_for(tickers: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in sorted(set(tickers)):
        md = market_data(t)
        if not isinstance(md, ToolError) and md.last_price > 0:
            out[t] = md.last_price
    return out


def _as_float(x: object) -> float | None:
    return float(x) if isinstance(x, int | float) else None


def _with_breadth(macro: MacroData, universe_tickers: list[str], notes: list[str]) -> MacroData:
    b = market_breadth(universe_tickers)
    if isinstance(b, ToolError):
        notes.append(f"market_breadth 실패: {b.error} — breadth 축 결측")
        return macro
    # model_copy(update=) 는 재검증 안 함 → 명시적으로 float|None 강제
    return macro.model_copy(
        update={
            "pct_above_200dma": _as_float(b.get("pct_above_200dma")),
            "pct_above_200dma_4w_change": _as_float(b.get("pct_above_200dma_4w_change")),
        }
    )


def _category_usd(pf: PaperPortfolio, prices: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = dict.fromkeys(_CATS, 0.0)
    for t, pos in pf.positions.items():
        if pos.shares <= 0:
            continue
        cat = (pos.category or "").lower()
        if cat in out:
            out[cat] += pos.shares * prices.get(t, pos.avg_cost_usd)
    return out


def _build_orders(
    sizing: SizingResult,
    pf: PaperPortfolio,
    prices: dict[str, float],
    plan_buy: dict[str, float],
    plan_sell: dict[str, float],
) -> list[Order]:
    """cash_flow_rebalance 의 카테고리별 매수/매도 금액을 draft 종목에 분배.
    적금형: 목표 초과 보유분은 plan 이 그 카테고리 매도를 지시할 때만 매도.
    """
    targets = {p.ticker: p for p in sizing.positions}
    cur_usd = {
        t: pos.shares * prices.get(t, 0.0) for t, pos in pf.positions.items() if pos.shares > 1e-9
    }
    orders: list[Order] = []
    dropped_usd: dict[str, float] = defaultdict(float)

    # 1. draft 에서 빠진 보유 종목 → 전량 매도 (대금은 같은 카테고리 매수에 재투입)
    for t, pos in pf.positions.items():
        if t in targets or pos.shares <= 1e-9 or not prices.get(t):
            continue
        cat = (pos.category or "").lower() or None
        orders.append(Order(ticker=t, side="sell", shares=pos.shares, category=cat))
        if cat:
            dropped_usd[cat] += cur_usd.get(t, 0.0)

    for cat in _CATS:
        names = [p for p in sizing.positions if p.category == cat and prices.get(p.ticker)]
        if not names:
            continue
        gaps_buy = {
            p.ticker: max(0.0, targets[p.ticker].target_usd - cur_usd.get(p.ticker, 0.0))
            for p in names
        }
        gaps_sell = {
            p.ticker: max(0.0, cur_usd.get(p.ticker, 0.0) - targets[p.ticker].target_usd)
            for p in names
        }
        buy_budget = plan_buy.get(cat, 0.0) + dropped_usd.get(cat, 0.0)
        for tk, amt in _split(gaps_buy, buy_budget).items():
            orders.append(
                Order(
                    ticker=tk, side="buy", notional_usd=amt, category=cat, sector=targets[tk].sector
                )
            )
        for tk, amt in _split(gaps_sell, plan_sell.get(cat, 0.0)).items():
            orders.append(Order(ticker=tk, side="sell", notional_usd=amt, category=cat))
    return orders


def _split(gaps: dict[str, float], budget: float) -> dict[str, float]:
    """`budget` 을 각 종목의 gap 비율로 분배. 최소주문 미만은 제외."""
    total = sum(gaps.values())
    if budget <= _MIN_ORDER_USD or total <= 1e-6:
        return {}
    spend = min(budget, total)
    out = {t: round(spend * g / total, 2) for t, g in gaps.items() if g > 0}
    return {t: a for t, a in out.items() if a >= _MIN_ORDER_USD}


def run_pipeline(
    *,
    portfolio: PaperPortfolio,
    pending_contribution_usd: float = 0.0,
    macro: MacroData | None = None,
    regime_history: list[RegimeHistoryPoint] | None = None,
    crisis_state: CrisisState | None = None,
    universe: str = "combined",
    mode: str = "paper",
) -> PipelineResult:
    notes: list[str] = []
    universe_tickers = get_universe(universe)

    macro = macro or _with_breadth(macro_data(), universe_tickers, notes)
    regime = regime_score(macro, regime_history or [], crisis_state or CrisisState())

    held_prices = _prices_for(list(portfolio.positions))
    nav = (
        portfolio.cash_usd
        + sum(
            pos.shares * held_prices.get(t, pos.avg_cost_usd)
            for t, pos in portfolio.positions.items()
        )
        + pending_contribution_usd
    )

    alloc: AllocationTargets | ToolError = allocation_targets(
        regime.score_smooth, nav, crisis=regime.crisis_active, mode=mode
    )
    if isinstance(alloc, ToolError):
        raise RuntimeError(
            f"allocation_targets 실패: {alloc.error}"
        )  # 설정 오류 — 조용히 넘기면 안 됨

    scoring: dict[str, ScoringResult] = {}
    scored_lists: dict[str, list[ScoredTicker]] = {}
    screen_counts: dict[str, int] = {}
    for cat in _CATS:
        sr = screen(cat, universe)
        if isinstance(sr, ToolError):
            notes.append(f"screen({cat}) 실패: {sr.error}")
            screen_counts[cat] = 0
            scored_lists[cat] = []
            continue
        screen_counts[cat] = len(sr.passed)
        tickers = [t.ticker for t in sr.passed]
        sc = score_category(cat, tickers) if tickers else ToolError(error="통과 0", field="tickers")
        if isinstance(sc, ToolError):
            notes.append(f"score_category({cat}): {sc.error}")
            scored_lists[cat] = []
        else:
            scoring[cat] = sc
            scored_lists[cat] = sc.scores

    current_cat_usd = _category_usd(portfolio, held_prices)
    plan = cash_flow_rebalance(
        alloc.category_targets_total,
        current_cat_usd,
        portfolio.cash_usd,
        pending_contribution_usd,
        dict(portfolio.cooldown_days),
        crisis=regime.crisis_active,
    )
    if isinstance(plan, ToolError):
        raise RuntimeError(f"cash_flow_rebalance 실패: {plan.error}")

    # 사이징 예산 = plan 이 지시한 "이번 회차 실현" 카테고리 비중 (목표가 아님).
    # 초기/대전환 시 max_change_per_rebal(카테고리 10%p/회) 때문에 목표까지 여러 주에 걸쳐 램프업.
    budgets = {c: plan.post_action_weights.get(c, 0.0) for c in _CATS}
    target = alloc.category_targets_total
    if any(abs(budgets[c] - target[c]) > 0.02 for c in _CATS):
        notes.append(
            "배분 램프업 중: post_action "
            + str({c: round(budgets[c], 3) for c in _CATS})
            + " vs 목표 "
            + str({c: round(target[c], 3) for c in _CATS})
        )
    sizing = size_positions(budgets, scored_lists, alloc.max_positions, nav, as_of=macro.as_of)
    if isinstance(sizing, ToolError):
        raise RuntimeError(f"size_positions 실패: {sizing.error}")
    notes.extend(sizing.notes)

    draft = DraftPortfolio(
        category_weights=sizing.category_weights,
        positions=[
            Position(ticker=p.ticker, category=p.category, weight=p.weight, sector=p.sector)
            for p in sizing.positions
        ],
    )
    constraints = check_constraints(draft)

    order_prices = {**held_prices, **_prices_for([p.ticker for p in sizing.positions])}
    orders = _build_orders(
        sizing,
        portfolio,
        order_prices,
        {o.category: o.amount_usd for o in plan.buys_from_new_cash},
        {o.category: o.amount_usd for o in plan.sell_orders},
    )

    return PipelineResult(
        as_of=macro.as_of,
        nav_usd=round(nav, 2),
        regime=regime,
        allocation=alloc,
        screen_counts=screen_counts,
        scoring=scoring,
        rebalance_plan=plan,
        sizing=sizing,
        draft=draft,
        constraints=constraints,
        orders=orders,
        prices=order_prices,
        notes=notes,
    )


def _demo() -> None:  # 수동 스모크 — python -m aegisvest.pipeline
    logging.basicConfig(level="INFO", format="%(name)s %(levelname)s %(message)s")
    pf = load_model("paper_portfolio.json", PaperPortfolio) or PaperPortfolio()
    hist = load_list("regime_history.json", RegimeHistoryPoint)
    cs = load_model("crisis_state.json", CrisisState)
    res = run_pipeline(
        portfolio=pf, pending_contribution_usd=70.0, regime_history=hist, crisis_state=cs
    )
    _log.info(
        "%s regime=%s nav=$%.2f targets=%s constraints=%s orders=%d",
        res.as_of,
        res.regime.regime.value,
        res.nav_usd,
        {k: round(v, 3) for k, v in res.draft.category_weights.items()},
        res.constraints.verdict,
        len(res.orders),
    )
    for n in res.notes:
        _log.info("  note: %s", n)


if __name__ == "__main__":
    _demo()
