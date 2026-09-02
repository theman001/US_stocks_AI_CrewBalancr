"""MarketDataTool — 가격·이동평균·기술지표. 소스: yfinance. docs/TOOLS.md §1."""

from __future__ import annotations

import math

from aegisvest.config import get_settings
from aegisvest.schemas import MarketData, ToolError
from aegisvest.tools import indicators as ind
from aegisvest.tools._prices import MARKET_SYMBOL, history


def market_data(ticker: str) -> MarketData | ToolError:
    """`ticker` 의 가격·기술지표. 이력은 항상 5년 조회 (60개월 베타 커버)."""
    ticker = ticker.strip().upper()
    if not ticker:
        return ToolError(error="빈 티커", field="ticker")

    ttl = get_settings().cache_ttl_hours
    try:
        hist = history(ticker, ttl)
        spx = history(MARKET_SYMBOL, ttl)
    except Exception as exc:
        return ToolError(error=f"데이터 조회 실패: {exc}", field="network")

    if hist.empty or len(hist) < 2:
        return ToolError(error=f"이력 없음: {ticker}", field="ticker")

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]

    vol_20d = ind.sma(volume, 20)
    _lv = float(volume.iloc[-1])
    last_vol = _lv if not math.isnan(_lv) else None  # 장 직후 Volume=NaN 가능
    adv_20d_usd = float((close * volume).tail(20).mean()) if len(close) >= 20 else None

    r6 = ind.total_return(close, 126)
    spx_r6 = ind.total_return(spx["Close"], 126) if not spx.empty else None
    rs_6m = r6 - spx_r6 if (r6 is not None and spx_r6 is not None) else None

    beta_60m = ind.beta(close, spx["Close"]) if not spx.empty else None

    return MarketData(
        ticker=ticker,
        last_price=float(close.iloc[-1]),
        sma_50=ind.sma(close, 50),
        sma_200=ind.sma(close, 200),
        sma_50_prev=ind.sma_prev(close, 50),
        sma_200_prev=ind.sma_prev(close, 200),
        rsi_14=ind.rsi(close, 14),
        atr_14=ind.atr(high, low, close, 14),
        beta_60m=beta_60m,
        adv_20d_usd=adv_20d_usd,
        rs_vs_spx_6m=rs_6m,
        mom_12_1=ind.momentum_12_1(close),
        pct_from_52w_high=ind.pct_from_52w_high(close),
        vol_20d_avg=vol_20d,
        vol_ratio_latest=(
            last_vol / vol_20d if (last_vol is not None and vol_20d and vol_20d > 0) else None
        ),
        as_of=str(close.index[-1].date()),
    )
