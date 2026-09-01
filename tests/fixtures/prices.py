"""합성 가격 데이터 빌더 — 툴 테스트용."""

from __future__ import annotations

import numpy as np
import pandas as pd


def price_frame(
    n: int = 400,
    start: float = 100.0,
    drift: float = 0.0005,
    seed: int = 0,
    vol: float = 0.01,
) -> pd.DataFrame:
    """결정적 랜덤워크 OHLCV DataFrame (tz-aware 일봉 인덱스)."""
    rng = np.random.default_rng(seed)
    rets = drift + vol * rng.standard_normal(n)
    close = start * np.cumprod(1.0 + rets)
    high = close * (1.0 + np.abs(rng.standard_normal(n)) * 0.003)
    low = close * (1.0 - np.abs(rng.standard_normal(n)) * 0.003)
    open_ = np.concatenate([[start], close[:-1]])
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.bdate_range(end="2026-08-31", periods=n, tz="America/New_York")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )
