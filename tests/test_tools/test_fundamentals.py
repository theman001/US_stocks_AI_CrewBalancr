"""fundamentals.py — TEST_GUIDE 시나리오 1 (mock FMP stable API)."""

from __future__ import annotations

from typing import Any

import pytest

from aegisvest.schemas import Fundamentals, ToolError
from aegisvest.tools import fundamentals as fun

_PROFILE = [
    {"symbol": "AAPL", "price": 190.0, "marketCap": 3.0e12, "beta": 1.2, "sector": "Technology"}
]
_RT = [
    {
        "priceToEarningsRatioTTM": 30.0,
        "grossProfitMarginTTM": 0.45,
        "dividendPayoutRatioTTM": 0.15,
        "interestCoverageRatioTTM": 40.0,
        "dividendYieldTTM": 0.005,
    }
]
_KM = [
    {
        "marketCap": 3.0e12,
        "evToEBITDATTM": 22.0,
        "returnOnInvestedCapitalTTM": 0.55,
        "returnOnEquityTTM": 1.5,
        "netDebtToEBITDATTM": 0.4,
    }
]
_INCOME = [
    {
        "date": "2025-09-30",
        "revenue": 400.0,
        "eps": 6.5,
        "operatingIncome": 120.0,
        "netIncome": 100.0,
        "grossProfit": 180.0,
        "weightedAverageShsOutDil": 15.0,
        "interestExpense": 3.0,
    },
    {
        "date": "2024-09-30",
        "revenue": 380.0,
        "eps": 6.0,
        "operatingIncome": 110.0,
        "netIncome": 95.0,
        "grossProfit": 168.0,
        "weightedAverageShsOutDil": 15.5,
        "interestExpense": 3.0,
    },
    {
        "date": "2023-09-30",
        "revenue": 360.0,
        "eps": 5.5,
        "operatingIncome": 100.0,
        "netIncome": 88.0,
        "grossProfit": 155.0,
        "weightedAverageShsOutDil": 16.0,
        "interestExpense": 3.0,
    },
    {
        "date": "2022-09-30",
        "revenue": 330.0,
        "eps": 5.0,
        "operatingIncome": 90.0,
        "netIncome": 80.0,
        "grossProfit": 140.0,
        "weightedAverageShsOutDil": 16.5,
        "interestExpense": 3.0,
    },
]
_BALANCE = [
    {
        "totalAssets": 350.0,
        "totalLiabilities": 280.0,
        "totalCurrentAssets": 130.0,
        "totalCurrentLiabilities": 140.0,
        "longTermDebt": 90.0,
        "retainedEarnings": 5.0,
        "totalStockholdersEquity": 62.0,
    },
    {
        "totalAssets": 340.0,
        "totalLiabilities": 275.0,
        "totalCurrentAssets": 128.0,
        "totalCurrentLiabilities": 150.0,
        "longTermDebt": 95.0,
        "retainedEarnings": 4.0,
        "totalStockholdersEquity": 60.0,
    },
]
_CASHFLOW = [
    {"freeCashFlow": 95.0, "operatingCashFlow": 110.0, "netDividendsPaid": -15.0},
    {"freeCashFlow": 90.0, "operatingCashFlow": 105.0, "netDividendsPaid": -14.0},
]
_RATIOS_ANNUAL = [
    {"priceToEarningsRatio": 28.0, "dividendYield": 0.006},
    {"priceToEarningsRatio": 26.0, "dividendYield": 0.006},
    {"priceToEarningsRatio": 24.0, "dividendYield": 0.007},
]
_ESTIMATES = [{"date": "2027-09-30", "epsAvg": 7.2}, {"date": "2026-09-30", "epsAvg": 7.0}]
_DIVIDENDS = [
    {"date": f"{y}-05-01", "adjDividend": d}
    for y, d in [
        (2018, 0.68),
        (2019, 0.75),
        (2020, 0.80),
        (2021, 0.85),
        (2022, 0.90),
        (2023, 0.95),
        (2024, 1.00),
        (2025, 1.05),
        (2026, 1.10),
    ]
]

_ALL = {
    "profile": _PROFILE,
    "ratios-ttm": _RT,
    "key-metrics-ttm": _KM,
    "income-statement": _INCOME,
    "balance-sheet-statement": _BALANCE,
    "cash-flow-statement": _CASHFLOW,
    "ratios": _RATIOS_ANNUAL,
    "analyst-estimates": _ESTIMATES,
    "dividends": _DIVIDENDS,
}


@pytest.fixture
def _mock_fmp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    fun.get_settings.cache_clear()
    monkeypatch.setattr(fun, "_get", lambda ep, key, **kw: _ALL.get(ep, []))


@pytest.mark.usefixtures("_mock_fmp")
def test_schema_and_derived() -> None:
    r = fun.fundamentals("aapl")
    assert isinstance(r, Fundamentals)
    assert set(r.model_dump()) == set(Fundamentals.model_fields)
    assert r.ticker == "AAPL"
    assert r.market_cap_usd == 3.0e12
    assert r.sector == "Technology"
    assert r.pe_ttm == 30.0
    assert r.pe_5y_median == 26.0
    assert r.eps_growth_fwd == pytest.approx(7.0 / 6.5 - 1.0)  # 가장 가까운 미래 FY
    assert r.pe_forward == pytest.approx(190.0 / 7.0)
    assert r.op_margin_trend_3y == "rising"
    assert r.roe_5y_avg is not None and r.roe_5y_avg > 0
    assert r.div_streak_years == 7  # 2018→2025 (2026 불완전 제외), 매년 증가
    assert r.dgr_5y == pytest.approx((1.05 / 0.80) ** (1 / 5) - 1.0)  # 2025 vs 2020
    assert r.piotroski_f is not None and 0 <= r.piotroski_f <= 9
    assert r.altman_z is not None
    assert r.fcf_payout == pytest.approx(15.0 / 95.0)
    assert r.eps_positive_years_10 == 4


def test_no_key() -> None:
    r = fun.fundamentals("AAPL")
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


@pytest.mark.usefixtures("_mock_fmp")
def test_interest_coverage_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    patched = {**_ALL, "ratios-ttm": [{**_RT[0], "interestCoverageRatioTTM": 0.0}]}
    monkeypatch.setattr(fun, "_get", lambda ep, key, **kw: patched.get(ep, []))
    r = fun.fundamentals("AAPL")
    assert isinstance(r, Fundamentals)
    assert r.interest_coverage == pytest.approx(120.0 / 3.0)  # EBIT / 이자비용
