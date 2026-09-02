"""벤치마크 시뮬 — 전략과 동일한 현금흐름으로 SPY / 60·40 / ACWI 매수보유.

근거: report/phase-3 §7.3. 전략 NAV 와 나란히 추적해 Gate B 판정에 사용.
매 입금 시 각 벤치마크 배분대로 매수 (지속 리밸런싱 없음 — 3a-7 단순화).
"""

from __future__ import annotations

from aegisvest.schemas import BenchmarkState, NavPoint

# 벤치마크명 → {티커: 배분 비중}
BENCHMARKS: dict[str, dict[str, float]] = {
    "spy": {"SPY": 1.0},
    "sixtyforty": {"SPY": 0.6, "AGG": 0.4},
    "acwi": {"ACWI": 1.0},
}
BENCH_TICKERS = sorted({t for alloc in BENCHMARKS.values() for t in alloc})


def contribute(state: BenchmarkState, usd: float, prices: dict[str, float]) -> None:
    """`usd` + 이월된 미체결분을 각 벤치마크 배분대로 매수.

    한 티커라도 가격이 없으면 그 벤치마크의 전체 투입액을 `pending_usd` 로 이월 —
    일부만 사서 영구 저투자되는 것(Gate B 비교 왜곡)을 막는다 (4-post-review).
    """
    for name, alloc in BENCHMARKS.items():
        book = state.holdings.setdefault(name, {})
        available = usd + state.pending_usd.get(name, 0.0)
        if any(not prices.get(t) or prices[t] <= 0 for t in alloc):
            state.pending_usd[name] = available  # 완전 체결 가능할 때까지 보류
            continue
        for ticker, w in alloc.items():
            book[ticker] = book.get(ticker, 0.0) + available * w / prices[ticker]
        state.pending_usd[name] = 0.0


def mark_to_market(
    state: BenchmarkState, prices: dict[str, float], date: str, fx_rate: float
) -> dict[str, NavPoint]:
    out: dict[str, NavPoint] = {}
    for name, book in state.holdings.items():
        if any(t not in prices for t in book):
            continue  # 부분 가격 → 유령 급락 방지, 그날은 기록하지 않음
        nav = sum(sh * prices[t] for t, sh in book.items()) + state.pending_usd.get(name, 0.0)
        point = NavPoint(date=date, nav_usd=round(nav, 2), nav_krw=round(nav * fx_rate, 2))
        hist = state.history.setdefault(name, [])
        if hist and hist[-1].date == date:
            hist[-1] = point
        else:
            hist.append(point)
        out[name] = point
    return out
