"""screener.py — TEST_GUIDE 시나리오 3 (합성 유니버스, 경계 필터)."""

from __future__ import annotations

from typing import Any

import pytest

from aegisvest.schemas import ScreenResult, ToolError
from aegisvest.tools import screener as sc

# 저위험 하드 필터를 전부 통과하는 기준 종목
_LOW_OK: dict[str, Any] = {
    "market_cap_usd": 5.0e10,
    "beta_60m": 0.5,
    "div_streak_years": 20,
    "dgr_5y": 0.06,
    "eps_payout": 0.5,
    "fcf_payout": 0.6,
    "net_debt_ebitda": 1.5,
    "interest_coverage": 20.0,
    "roe_5y_avg": 0.25,
    "roic": 0.20,
    "wacc_est": 0.08,
    "eps_positive_years_10": 5,
    "piotroski_f": 8,
    "altman_z": 5.0,
    "credit_rating": None,
    "as_of": "2026-09-01",
}


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any] | None]:
    store: dict[str, dict[str, Any] | None] = {}

    def _universe(name: str) -> list[str]:
        return list(store)

    def _merged(ticker: str) -> dict[str, Any] | None:
        return store.get(ticker)

    monkeypatch.setattr(sc, "get_universe", _universe)
    monkeypatch.setattr(sc, "merged_values", _merged)
    return store


def test_low_pass_and_fail(rows: dict[str, Any]) -> None:
    rows["GOOD"] = dict(_LOW_OK)
    rows["HIBETA"] = {**_LOW_OK, "beta_60m": 1.6}
    rows["LOWF"] = {**_LOW_OK, "piotroski_f": 4}
    r = sc.screen("LOW", "combined")
    assert isinstance(r, ScreenResult)
    assert [st.ticker for st in r.passed] == ["GOOD"]
    assert r.failed_count == 2
    assert r.evaluated_count == 3


def test_ref_comparison_roic_vs_wacc(rows: dict[str, Any]) -> None:
    rows["X"] = {**_LOW_OK, "roic": 0.05, "wacc_est": 0.09}
    r = sc.screen("LOW", "combined")
    assert r.passed == []


def test_optional_filter_skips_on_missing(rows: dict[str, Any]) -> None:
    rows["X"] = dict(_LOW_OK)  # credit_rating None → optional → skip
    r = sc.screen("LOW", "combined")
    assert [st.ticker for st in r.passed] == ["X"]
    assert r.passed[0].checks["credit_rating"].result == "skip"


def test_missing_required_field_fails(rows: dict[str, Any]) -> None:
    rows["X"] = {k: v for k, v in _LOW_OK.items() if k != "piotroski_f"}
    r = sc.screen("LOW", "combined")
    assert r.passed == []


def test_data_error_recorded(rows: dict[str, Any]) -> None:
    rows["GOOD"] = dict(_LOW_OK)
    rows["BADDATA"] = None  # merged_values → None
    r = sc.screen("LOW", "combined")
    assert "BADDATA" in r.errored
    assert [st.ticker for st in r.passed] == ["GOOD"]


def test_unknown_category() -> None:
    r = sc.screen("EXTREME")
    assert isinstance(r, ToolError)
    assert r.field == "category"


def test_empty_universe(rows: dict[str, Any]) -> None:
    r = sc.screen("LOW", "combined")
    assert isinstance(r, ToolError)
    assert r.field == "universe"


def test_high_rs_top30_cut(rows: dict[str, Any]) -> None:
    base = {
        "market_cap_usd": 5.0e9,
        "adv_20d_usd": 1.0e8,
        "rev_growth_yoy": 0.5,
        "last_price": 110.0,
        "sma_200": 100.0,
        "sma_50": 105.0,
        "mom_12_1": 0.2,
        "rsi_14": 60.0,
        "vol_ratio_latest": 1.1,
        "as_of": "2026-09-01",
    }
    for i, rs in enumerate([0.9, 0.7, 0.5, 0.3, 0.1]):
        rows[f"T{i}"] = {**base, "rs_vs_spx_6m": rs}
    r = sc.screen("HIGH", "combined")
    assert {st.ticker for st in r.passed} == {"T0", "T1"}  # round(5*0.3)=2
