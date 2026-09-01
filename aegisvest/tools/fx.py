"""환율 — USD/KRW (1 USD = N KRW). 모의투자 원화 입금 환산용. docs/TOOLS.md §14.

yfinance `KRW=X` 일봉 마지막 종가. 캐시. 예외 raise 안 함.
"""

from __future__ import annotations

from aegisvest.config import get_settings
from aegisvest.schemas import ToolError
from aegisvest.tools._prices import history

_SYMBOL = "KRW=X"  # yfinance: USD 기준 KRW


def usd_krw(ttl_hours: float | None = None) -> float | ToolError:
    ttl = ttl_hours if ttl_hours is not None else float(get_settings().cache_ttl_hours)
    try:
        h = history(_SYMBOL, ttl)
    except Exception as e:
        return ToolError(error=f"환율 조회 실패: {e}", field="fx")
    if h.empty or "Close" not in h.columns:
        return ToolError(error="환율 데이터 없음", field="fx")
    rate = float(h["Close"].iloc[-1])
    if not 500.0 < rate < 3000.0:  # 상식 범위 밖 → 데이터 오류
        return ToolError(error=f"환율 이상치: {rate}", field="fx")
    return rate
