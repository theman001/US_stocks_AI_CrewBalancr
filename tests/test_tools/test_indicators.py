"""indicators.py — 알려진 값 검증 (TEST_GUIDE 시나리오 2 지원)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegisvest.tools import indicators as ind


def test_sma_basic() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.sma(s, 3) == 4.0  # (3+4+5)/3
    assert ind.sma(s, 10) is None  # 데이터 부족


def test_sma_prev() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.sma_prev(s, 3, back=1) == 3.0  # (2+3+4)/3


def test_rsi_all_gains_is_100() -> None:
    s = pd.Series(np.arange(1, 40, dtype=float))
    assert ind.rsi(s, 14) == 100.0


def test_rsi_range() -> None:
    rng = np.random.default_rng(1)
    s = pd.Series(100 + np.cumsum(rng.standard_normal(100)))
    r = ind.rsi(s, 14)
    assert r is not None and 0.0 <= r <= 100.0


def test_atr_positive() -> None:
    rng = np.random.default_rng(2)
    close = pd.Series(100 + np.cumsum(rng.standard_normal(60)))
    high = close + 1.0
    low = close - 1.0
    a = ind.atr(high, low, close, 14)
    assert a is not None and a > 0


def test_beta_of_self_is_one() -> None:
    idx = pd.bdate_range("2020-01-01", periods=800, tz="UTC")  # ~38개월 (>24 최소)
    rng = np.random.default_rng(3)
    px = pd.Series(100 + np.cumsum(rng.standard_normal(800)), index=idx)
    b = ind.beta(px, px)
    assert b is not None and abs(b - 1.0) < 1e-6


def test_beta_none_when_too_short() -> None:
    idx = pd.bdate_range("2024-01-01", periods=200, tz="UTC")
    px = pd.Series(range(200), index=idx, dtype=float)
    assert ind.beta(px, px) is None  # 24개월 미만


def test_total_return() -> None:
    s = pd.Series([100.0] * 10 + [110.0])
    assert ind.total_return(s, 10) == pytest.approx(0.10)


def test_momentum_12_1() -> None:
    s = pd.Series(np.linspace(100, 200, 300))
    m = ind.momentum_12_1(s)
    assert m is not None


def test_pct_from_52w_high() -> None:
    s = pd.Series([100.0, 120.0, 90.0])
    assert ind.pct_from_52w_high(s) == 90.0 / 120.0 - 1.0
