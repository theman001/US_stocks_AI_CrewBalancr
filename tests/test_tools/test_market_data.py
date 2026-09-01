"""market_data.py — TEST_GUIDE 시나리오 1."""

from __future__ import annotations

import pandas as pd
import pytest

from aegisvest.schemas import MarketData, ToolError
from aegisvest.tools import market_data as md
from tests.fixtures.prices import price_frame


@pytest.fixture(autouse=True)
def _mock_history(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_history(symbol: str, ttl_hours: float) -> pd.DataFrame:
        if symbol == "ZZZZ":
            return pd.DataFrame()
        seed = 1 if symbol == "^GSPC" else 7
        return price_frame(n=400, seed=seed)

    monkeypatch.setattr(md, "history", fake_history)


def test_schema_all_fields() -> None:
    r = md.market_data("AAPL")
    assert isinstance(r, MarketData)
    d = r.model_dump()
    expected = set(MarketData.model_fields)
    assert set(d) == expected
    assert d["ticker"] == "AAPL"
    assert d["last_price"] > 0
    assert d["sma_50"] is not None and d["sma_200"] is not None
    assert d["rsi_14"] is not None and 0 <= d["rsi_14"] <= 100
    assert d["as_of"] == "2026-08-31"


def test_bad_ticker_returns_error_no_raise() -> None:
    r = md.market_data("ZZZZ")
    assert isinstance(r, ToolError)
    assert r.field == "ticker"


def test_empty_ticker() -> None:
    r = md.market_data("   ")
    assert isinstance(r, ToolError)


def test_network_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> pd.DataFrame:
        raise ConnectionError("no net")

    monkeypatch.setattr(md, "history", boom)
    r = md.market_data("AAPL")
    assert isinstance(r, ToolError)
    assert r.field == "network"
