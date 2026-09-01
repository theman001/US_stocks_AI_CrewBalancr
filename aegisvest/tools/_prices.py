"""yfinance 일봉 이력 조회 (TTL 캐시). market_data / macro_data 공용."""

from __future__ import annotations

from typing import cast

import pandas as pd
import yfinance as yf

from aegisvest.tools._io import cached

MARKET_SYMBOL = "^GSPC"
HISTORY_PERIOD = "5y"  # 60개월 베타 커버
_COLS = ["Open", "High", "Low", "Close", "Volume"]


def history(symbol: str, ttl_hours: float) -> pd.DataFrame:
    """`symbol` 의 5년 일봉 (auto-adjust). 빈 DataFrame 가능 (상폐/오류)."""

    def _fetch() -> pd.DataFrame:
        df = yf.Ticker(symbol).history(period=HISTORY_PERIOD, interval="1d", auto_adjust=True)
        cols = [c for c in _COLS if c in df.columns]
        return cast("pd.DataFrame", df[cols].dropna())

    return cached(f"yf:hist:{symbol}:{HISTORY_PERIOD}", ttl_hours, _fetch)
