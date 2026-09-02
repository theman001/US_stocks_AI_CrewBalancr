"""fundamentals.py — TEST_GUIDE 시나리오 1 (mock yfinance 번들)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from aegisvest.schemas import Fundamentals, ToolError
from aegisvest.tools import fundamentals as fun

_COLS = pd.to_datetime(["2025-09-30", "2024-09-30", "2023-09-30", "2022-09-30", "2021-09-30"])

_INFO: dict[str, Any] = {
    "marketCap": 3.0e12,
    "trailingPE": 30.0,
    "forwardPE": 26.0,
    "forwardEps": 7.0,
    "trailingEps": 6.5,
    "beta": 1.2,
    "dividendYield": 0.55,  # 퍼센트 → 0.0055
    "fiveYearAvgDividendYield": 0.60,
    "payoutRatio": 0.15,
    "returnOnEquity": 1.5,
    "grossMargins": 0.45,
    "debtToEquity": 45.0,  # 퍼센트 → 0.45
    "freeCashflow": 95.0,
    "revenueGrowth": 0.10,
    "pegRatio": 1.8,
    "enterpriseToEbitda": 22.0,
    "sector": "Technology",
}
_BALANCE = pd.DataFrame(
    {
        _COLS[0]: [350, 280, 130, 120, 90, 5, 62, 40],
        _COLS[1]: [340, 275, 128, 125, 95, 4, 60, 45],
        _COLS[2]: [330, 270, 125, 128, 100, 3, 58, 50],
        _COLS[3]: [320, 268, 122, 130, 105, 2, 55, 55],
        _COLS[4]: [310, 265, 120, 132, 110, 1, 52, 60],
    },
    index=[
        "Total Assets",
        "Total Liabilities Net Minority Interest",
        "Current Assets",
        "Current Liabilities",
        "Long Term Debt",
        "Retained Earnings",
        "Stockholders Equity",
        "Net Debt",
    ],
)
_INCOME = pd.DataFrame(
    {
        _COLS[0]: [400, 180, 120, 120, 100, 6.5, 15.0, 3.0, 140],
        _COLS[1]: [380, 168, 110, 110, 95, 6.0, 15.5, 3.0, 130],
        _COLS[2]: [360, 155, 100, 100, 88, 5.5, 16.0, 3.0, 120],
        _COLS[3]: [330, 140, 90, 90, 80, 5.0, 16.5, 3.0, 108],
        _COLS[4]: [300, 125, 78, 78, 70, 4.5, 17.0, 3.0, 95],
    },
    index=[
        "Total Revenue",
        "Gross Profit",
        "EBIT",
        "Operating Income",
        "Net Income",
        "Diluted EPS",
        "Diluted Average Shares",
        "Interest Expense",
        "EBITDA",
    ],
)
_CASHFLOW = pd.DataFrame(
    {
        _COLS[0]: [95, 110, -15],
        _COLS[1]: [90, 105, -14],
        _COLS[2]: [85, 100, -13],
        _COLS[3]: [80, 95, -12],
        _COLS[4]: [70, 85, -11],
    },
    index=["Free Cash Flow", "Operating Cash Flow", "Cash Dividends Paid"],
)
_DIVS = pd.Series(
    [0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15],
    index=pd.to_datetime(
        [
            "2019-05-01",
            "2020-05-01",
            "2021-05-01",
            "2022-05-01",
            "2023-05-01",
            "2024-05-01",
            "2025-05-01",
        ]
    ),
)
_BUNDLE: dict[str, Any] = {
    "info": _INFO,
    "balance": _BALANCE,
    "income": _INCOME,
    "cashflow": _CASHFLOW,
    "dividends": _DIVS,
}


@pytest.fixture
def _mock_yf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fun, "_yf_bundle", lambda ticker, ttl: _BUNDLE)
    monkeypatch.setattr(fun, "history", lambda *a, **k: pd.DataFrame())  # pe_5y_median → None


@pytest.mark.usefixtures("_mock_yf")
def test_schema_and_derived() -> None:
    r = fun.fundamentals("aapl")
    assert isinstance(r, Fundamentals)
    assert set(r.model_dump()) == set(Fundamentals.model_fields)
    assert r.ticker == "AAPL"
    assert r.market_cap_usd == 3.0e12
    assert r.sector == "Technology"
    assert r.pe_ttm == 30.0
    assert r.div_yield == pytest.approx(0.0055)
    assert r.div_yield_5y_median == pytest.approx(0.0060)
    assert r.debt_to_equity == pytest.approx(0.45)
    assert r.eps_growth_fwd == pytest.approx(7.0 / 6.5 - 1.0)
    assert r.op_margin_trend_3y == "rising"
    assert r.roe_5y_avg is not None and r.roe_5y_avg > 0
    assert r.roic is not None and r.roic > 0
    assert r.interest_coverage == pytest.approx(120.0 / 3.0)  # EBIT / 이자비용
    assert r.net_debt_ebitda == pytest.approx(40.0 / 140.0)
    assert r.div_streak_years == 6  # 2019→2025 매년 증가 (2026 미도래)
    assert r.dgr_5y == pytest.approx((1.15 / 0.90) ** (1 / 5) - 1.0)
    assert r.piotroski_f is not None and 0 <= r.piotroski_f <= 9
    assert r.altman_z is not None
    assert r.fcf_payout == pytest.approx(15.0 / 95.0)
    assert r.eps_positive_years_10 == 5


def test_empty_ticker() -> None:
    r = fun.fundamentals("  ")
    assert isinstance(r, ToolError)
    assert r.field == "ticker"


@pytest.mark.usefixtures("_mock_yf")
def test_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fun,
        "_yf_bundle",
        lambda t, ttl: {
            "info": {},
            "balance": pd.DataFrame(),
            "income": pd.DataFrame(),
            "cashflow": pd.DataFrame(),
            "dividends": pd.Series(dtype=float),
        },
    )
    r = fun.fundamentals("ZZZZ")
    assert isinstance(r, ToolError)
    assert r.field == "ticker"


@pytest.mark.usefixtures("_mock_yf")
def test_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> Any:
        raise ConnectionError("down")

    monkeypatch.setattr(fun, "_yf_bundle", boom)
    r = fun.fundamentals("AAPL")
    assert isinstance(r, ToolError)
    assert r.field == "network"


def test_cagr_positional_index_with_interior_gap() -> None:
    # [R0, R1, None, R3] years=3 → 기준은 R3 (3년 전), 압축 시 R1 로 어긋났었음
    assert fun._cagr([8.0, 7.0, None, 4.0], 3) == pytest.approx((8.0 / 4.0) ** (1 / 3) - 1.0)
    # 기준 연도 자체가 결측이면 계산 불가 → None (엉뚱한 해로 대체 안 함)
    assert fun._cagr([8.0, 7.0, None, None], 3) is None
    assert fun._cagr([8.0, 7.0], 3) is None  # 데이터 부족
