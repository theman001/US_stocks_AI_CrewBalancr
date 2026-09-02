"""시장 폭 — 유니버스 구성종목 중 200일선 상회 비율. macro_data 의 breadth 축을 채운다.

3a-8 파이프라인이 유니버스 티커로 호출해 MacroData.pct_above_200dma 를 패치한다.
"""

from __future__ import annotations

import datetime as dt

from aegisvest.config import get_settings
from aegisvest.schemas import ToolError
from aegisvest.tools import indicators as ind
from aegisvest.tools._prices import history


def market_breadth(tickers: list[str]) -> dict[str, float | str | None] | ToolError:
    """{pct_above_200dma, pct_above_200dma_4w_change(%p), n, as_of}. 값은 퍼센트 0~100."""
    if not tickers:
        return ToolError(error="빈 티커 리스트", field="tickers")
    ttl = float(get_settings().cache_ttl_hours)
    above_now = above_4w = evaluated = evaluated_4w = 0
    as_of = dt.date.today().isoformat()

    for t in tickers:
        try:
            h = history(t, ttl)
        except Exception:
            continue
        if h.empty or "Close" not in h.columns:
            continue
        close = h["Close"]
        sma200 = ind.sma(close, 200)
        sma200_4w = ind.sma_prev(close, 200, back=20)
        if sma200 is None:
            continue
        evaluated += 1
        as_of = str(close.index[-1].date())
        if float(close.iloc[-1]) > sma200:
            above_now += 1
        if sma200_4w is not None and len(close) > 20:  # 4주 전 SMA 가능한 종목만 별도 분모
            evaluated_4w += 1
            if float(close.iloc[-21]) > sma200_4w:
                above_4w += 1

    if evaluated < 10:
        return ToolError(error=f"평가 가능 종목 부족: {evaluated}", field="tickers")

    pct_now = 100.0 * above_now / evaluated
    pct_4w = 100.0 * above_4w / evaluated_4w if evaluated_4w else pct_now
    return {
        "pct_above_200dma": round(pct_now, 1),
        "pct_above_200dma_4w_change": round(pct_now - pct_4w, 1),
        "n": evaluated,
        "as_of": as_of,
    }
