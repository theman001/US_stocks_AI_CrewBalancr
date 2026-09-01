"""breadth.py — 시장 폭 (mock history)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegisvest.schemas import ToolError
from aegisvest.tools import breadth as br


def _frame(trend_up: bool) -> pd.DataFrame:
    n = 300
    slope = 0.4 if trend_up else -0.4
    close = 100 + slope * np.arange(n) + np.zeros(n)
    idx = pd.bdate_range(end="2026-08-31", periods=n, tz="America/New_York")
    return pd.DataFrame(
        {"Close": close, "High": close, "Low": close, "Open": close, "Volume": 1.0}, index=idx
    )


def test_breadth_pct(monkeypatch: pytest.MonkeyPatch) -> None:
    up = _frame(True)
    down = _frame(False)
    tickers = [f"U{i}" for i in range(7)] + [f"D{i}" for i in range(3)]
    monkeypatch.setattr(br, "history", lambda t, ttl: up if t.startswith("U") else down)
    r = br.market_breadth(tickers)
    assert isinstance(r, dict)
    assert r["pct_above_200dma"] == pytest.approx(70.0)  # 7/10
    assert r["n"] == 10


def test_breadth_empty() -> None:
    assert isinstance(br.market_breadth([]), ToolError)


def test_breadth_too_few_evaluable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(br, "history", lambda t, ttl: pd.DataFrame())
    r = br.market_breadth(["A", "B", "C"])
    assert isinstance(r, ToolError)
    assert r.field == "tickers"
