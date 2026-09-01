"""macro_data.py — TEST_GUIDE 시나리오 1 + 부분 실패 처리."""

from __future__ import annotations

import pandas as pd
import pytest

from aegisvest.schemas import MacroData
from aegisvest.tools import macro_data as mod
from tests.fixtures.prices import price_frame


def _fake_series(name: str) -> pd.Series:
    idx = pd.to_datetime(pd.bdate_range("2024-01-01", periods=300))
    if "IC4WSA" in name or name == "IC4WSA":
        return pd.Series(
            range(300), index=pd.to_datetime(pd.date_range("2024-01-01", periods=300, freq="W"))
        )
    base = {"T10Y3M": 0.45, "T10Y2Y": 0.30, "BAMLH0A0HYM2": 3.5, "DFF": 4.25, "WEI": 2.1}
    return pd.Series([base.get(name, 5.0)] * 300, index=idx)


@pytest.fixture
def _mock_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(mod, "_fred_series", lambda sid, key, limit=300: _fake_series(sid))
    monkeypatch.setattr(mod, "history", lambda sym, ttl: price_frame(n=300, seed=hash(sym) % 100))
    mod.get_settings.cache_clear()


@pytest.mark.usefixtures("_mock_all")
def test_schema_all_fields() -> None:
    r = mod.macro_data()
    assert isinstance(r, MacroData)
    assert set(r.model_dump()) == set(MacroData.model_fields)
    assert r.yc_10y_3m_bp == pytest.approx(45.0)  # 0.45pp -> 45bp
    assert r.hy_oas_bp == pytest.approx(350.0)
    assert r.vix is not None
    assert r.pct_above_200dma is None  # 3a-5 예정
    assert "fred:no_api_key" not in r.stale_fields


def test_no_fred_key_still_returns_with_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(mod, "history", lambda sym, ttl: price_frame(n=300, seed=1))
    mod.get_settings.cache_clear()
    r = mod.macro_data()
    assert isinstance(r, MacroData)
    assert "fred:no_api_key" in r.stale_fields
    assert r.yc_10y_3m_bp is None
    assert r.vix is not None  # yfinance 부분은 여전히 동작


def test_partial_fred_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    def flaky(sid: str, key: str, limit: int = 300) -> pd.Series:
        if sid == "BAMLH0A0HYM2":
            raise ConnectionError("down")
        return _fake_series(sid)

    monkeypatch.setattr(mod, "_fred_series", flaky)
    monkeypatch.setattr(mod, "history", lambda sym, ttl: price_frame(n=300, seed=1))
    mod.get_settings.cache_clear()
    r = mod.macro_data()
    assert r.hy_oas_bp is None
    assert "fred:hy_oas" in r.stale_fields
    assert r.yc_10y_3m_bp is not None  # 나머지는 정상
