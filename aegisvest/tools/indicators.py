"""기술 지표 — pandas/numpy 직접 계산 (pandas-ta 미사용).

전부 순수 함수. 데이터 부족 시 None. 마지막(최신) 값을 반환한다.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _last_float(series: pd.Series) -> float | None:
    if series.empty:
        return None
    val = series.iloc[-1]
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def sma(close: pd.Series, window: int) -> float | None:
    if len(close) < window:
        return None
    return _last_float(close.rolling(window).mean())


def sma_prev(close: pd.Series, window: int, back: int = 1) -> float | None:
    """`back` 봉 전의 SMA (골든/데드크로스 판정용)."""
    if len(close) < window + back:
        return None
    return _last_float(close.rolling(window).mean().shift(back))


def rsi(close: pd.Series, window: int = 14) -> float | None:
    if len(close) < window + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    last_loss = _last_float(avg_loss)
    last_gain = _last_float(avg_gain)
    if last_gain is None or last_loss is None:
        return None
    if last_loss == 0.0:
        return 100.0
    rs = last_gain / last_loss
    return 100.0 - 100.0 / (1.0 + rs)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> float | None:
    if len(close) < window + 1:
        return None
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1
    )
    return _last_float(tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean())


def beta(asset_close: pd.Series, market_close: pd.Series, months: int = 60) -> float | None:
    """월간 수익률 기준 베타. 최근 `months` 개월 (최소 24)."""
    a = asset_close.resample("ME").last().pct_change().dropna().rename("asset")
    m = market_close.resample("ME").last().pct_change().dropna().rename("market")
    joined = pd.concat([a, m], axis=1, join="inner").dropna().tail(months)
    if len(joined) < 24:
        return None
    cov = np.cov(joined["asset"].to_numpy(), joined["market"].to_numpy())
    market_var = float(cov[1, 1])
    if market_var == 0.0:
        return None
    return float(cov[0, 1] / market_var)


def total_return(close: pd.Series, trading_days: int) -> float | None:
    """최근 `trading_days` 거래일 총수익률 (소수)."""
    if len(close) < trading_days + 1:
        return None
    past = float(close.iloc[-trading_days - 1])
    now = float(close.iloc[-1])
    if past == 0.0:
        return None
    return now / past - 1.0


def momentum_12_1(close: pd.Series) -> float | None:
    """12개월 수익률 - 최근 1개월 수익률 (약 252 / 21 거래일)."""
    r12 = total_return(close, 252)
    r1 = total_return(close, 21)
    if r12 is None or r1 is None:
        return None
    return r12 - r1


def pct_from_52w_high(close: pd.Series, window: int = 252) -> float | None:
    if len(close) < 2:
        return None
    hi = float(close.tail(window).max())
    if hi == 0.0:
        return None
    return float(close.iloc[-1]) / hi - 1.0
