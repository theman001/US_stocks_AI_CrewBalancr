"""fundamentals.py — TEST_GUIDE 시나리오 1 (mock FMP)."""

from __future__ import annotations

from typing import Any

import pytest

from aegisvest.schemas import Fundamentals, ToolError
from aegisvest.tools import fundamentals as fun

_PROFILE = [{"symbol": "AAPL", "price": 190.0, "mktCap": 3.0e12, "sector": "Technology"}]
_RATIOS = [
    {
        "peRatioTTM": 30.0,
        "returnOnEquityTTM": 1.5,
        "grossProfitMarginTTM": 0.45,
        "payoutRatioTTM": 0.15,
        "interestCoverageTTM": 40.0,
        "dividendYieldTTM": 0.005,
    }
]
_METRICS = [
    {
        "enterpriseValueOverEBITDATTM": 22.0,
        "roicTTM": 0.55,
        "netDebtToEBITDATTM": 0.4,
        "freeCashFlowTTM": 9.0e10,
    }
]
_INCOME = [
    {"date": "2025-09-30", "revenue": 400.0, "eps": 6.5, "operatingIncomeRatio": 0.30},
    {"date": "2024-09-30", "revenue": 380.0, "eps": 6.0, "operatingIncomeRatio": 0.29},
    {"date": "2023-09-30", "revenue": 360.0, "eps": 5.5, "operatingIncomeRatio": 0.28},
    {"date": "2022-09-30", "revenue": 330.0, "eps": 5.0, "operatingIncomeRatio": 0.27},
]
_ESTIMATES = [{"estimatedEpsAvg": 7.2}]


@pytest.fixture
def _mock_fmp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    fun.get_settings.cache_clear()

    def fake_get(path: str, key: str, **params: Any) -> Any:
        if path.startswith("profile"):
            return _PROFILE
        if path.startswith("ratios-ttm"):
            return _RATIOS
        if path.startswith("key-metrics-ttm"):
            return _METRICS
        if path.startswith("income-statement"):
            return _INCOME
        if path.startswith("analyst-estimates"):
            return _ESTIMATES
        return []

    monkeypatch.setattr(fun, "_get", fake_get)


@pytest.mark.usefixtures("_mock_fmp")
def test_schema_and_derived() -> None:
    r = fun.fundamentals("aapl")
    assert isinstance(r, Fundamentals)
    assert set(r.model_dump()) == set(Fundamentals.model_fields)
    assert r.ticker == "AAPL"
    assert r.market_cap_usd == 3.0e12
    assert r.sector == "Technology"
    assert r.rev_cagr_3y is not None and r.rev_cagr_3y > 0
    assert r.eps_growth_fwd == pytest.approx(7.2 / 6.5 - 1.0)
    assert r.pe_forward == pytest.approx(190.0 / 7.2)
    assert r.op_margin_trend_3y == "rising"
    assert r.eps_positive_years_10 == 4


def test_no_key() -> None:
    r = fun.fundamentals("AAPL")  # 키 미설정 (conftest 가 삭제)
    assert isinstance(r, ToolError)
    assert r.field == "FMP_API_KEY"


@pytest.mark.usefixtures("_mock_fmp")
def test_unknown_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fun, "_get", lambda *a, **k: [])
    r = fun.fundamentals("ZZZZ")
    assert isinstance(r, ToolError)
    assert r.field == "ticker"


@pytest.mark.usefixtures("_mock_fmp")
def test_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> Any:
        raise ConnectionError("down")

    monkeypatch.setattr(fun, "_get", boom)
    r = fun.fundamentals("AAPL")
    assert isinstance(r, ToolError)
    assert r.field == "network"
