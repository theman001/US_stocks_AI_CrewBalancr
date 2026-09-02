"""scoring.py — percentile rank + 가중합 + subtier."""

from __future__ import annotations

from typing import Any

import pytest

from aegisvest.schemas import ScoringResult, ToolError
from aegisvest.tools import scoring as sco


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}

    def _merged(ticker: str) -> dict[str, Any] | None:
        return store.get(ticker)

    monkeypatch.setattr(sco, "merged_values", _merged)
    return store


def _low_row(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "pe_ttm": 20.0,
        "pe_5y_median": 25.0,
        "ev_ebitda": 12.0,
        "div_yield": 0.03,
        "div_yield_5y_median": 0.025,
        "dgr_5y": 0.06,
        "eps_payout": 0.5,
        "fcf_payout": 0.6,
        "roe_5y_avg": 0.2,
        "roic": 0.18,
        "piotroski_f": 7,
        "altman_z": 5.0,
        "debt_to_equity": 0.5,
        "div_streak_years": 30,
        "beta_60m": 0.7,
        "sector": "Consumer Defensive",
        "sma_50": 105.0,
        "sma_200": 100.0,
        "as_of": "2026-09-01",
    }
    base.update(kw)
    return base


def test_ranking_and_weights(rows: dict[str, Any]) -> None:
    rows["CHEAP"] = _low_row(pe_ttm=15.0, roe_5y_avg=0.30, roic=0.25)  # 싸고 수익성 최고
    rows["MID"] = _low_row(pe_ttm=20.0, roe_5y_avg=0.20, roic=0.18)
    rows["RICH"] = _low_row(pe_ttm=30.0, roe_5y_avg=0.10, roic=0.09)  # 비싸고 수익성 낮음
    r = sco.score_category("LOW", ["CHEAP", "MID", "RICH"])
    assert isinstance(r, ScoringResult)
    assert [s.ticker for s in r.scores] == ["CHEAP", "MID", "RICH"]
    assert r.scores[0].rank == 1 and r.scores[-1].rank == 3
    assert 0 <= r.scores[0].score <= 100
    assert r.scores[0].score > r.scores[-1].score


def test_missing_metric_is_neutral(rows: dict[str, Any]) -> None:
    rows["A"] = _low_row()
    rows["B"] = _low_row(altman_z=None, piotroski_f=None, debt_to_equity=None)
    r = sco.score_category("LOW", ["A", "B"])
    b = next(s for s in r.scores if s.ticker == "B")
    assert b.component_scores["safety"] == pytest.approx(0.5)


def test_subtier_assignment(rows: dict[str, Any]) -> None:
    rows["ARIST"] = _low_row(div_streak_years=40, beta_60m=0.6)
    rows["COMPOUND"] = _low_row(div_streak_years=12, beta_60m=1.0, roic=0.20, dgr_5y=0.10)
    rows["DEFENSIVE"] = _low_row(
        div_streak_years=12, beta_60m=1.0, roic=0.05, dgr_5y=0.02, sector="Utilities"
    )
    r = sco.score_category("LOW", ["ARIST", "COMPOUND", "DEFENSIVE"])
    tiers = {s.ticker: s.subtier for s in r.scores}
    assert tiers["ARIST"] == "LOW-A 배당귀족 코어"
    assert tiers["COMPOUND"] == "LOW-B 퀄리티 컴파운더"
    assert tiers["DEFENSIVE"] == "LOW-C 디펜시브 밸류"


def test_theme_strength_override(rows: dict[str, Any]) -> None:
    hi = {
        "mom_12_1": 0.2,
        "rs_vs_spx_6m": 0.1,
        "pct_from_52w_high": -0.05,
        "sma_50": 110.0,
        "sma_200": 100.0,
        "vol_ratio_latest": 1.2,
        "rev_growth_yoy": 0.4,
        "market_cap_usd": 3.0e10,
        "as_of": "2026-09-01",
    }
    rows["HOT"] = dict(hi)
    rows["COLD"] = dict(hi)
    r = sco.score_category(
        "HIGH", ["HOT", "COLD"], theme_strength_overrides={"HOT": 1.0, "COLD": 0.0}
    )
    hot = next(s for s in r.scores if s.ticker == "HOT")
    cold = next(s for s in r.scores if s.ticker == "COLD")
    assert hot.component_scores["theme_strength"] > cold.component_scores["theme_strength"]
    assert hot.score > cold.score


def test_empty_and_unknown() -> None:
    assert isinstance(sco.score_category("LOW", []), ToolError)
    assert isinstance(sco.score_category("BOGUS", ["X"]), ToolError)


def test_all_data_missing(rows: dict[str, Any]) -> None:
    r = sco.score_category("LOW", ["NOPE"])  # merged_values → None
    assert isinstance(r, ToolError)
    assert r.field == "tickers"


def test_negative_pe_not_scored_as_cheapest(rows: dict[str, Any]) -> None:
    rows["LOSS"] = _low_row(pe_ttm=-15.0)  # 적자 → PE 음수
    rows["OK"] = _low_row(pe_ttm=22.0)
    r = sco.score_category("LOW", ["LOSS", "OK"])
    assert isinstance(r, ScoringResult)
    loss = next(s for s in r.scores if s.ticker == "LOSS")
    # 음수 PE → pe_vs_5y_median None → valuation 컴포넌트 중립 (최고점 아님)
    assert loss.component_scores.get("valuation", 1.0) < 0.95


def test_non_numeric_metric_does_not_raise(rows: dict[str, Any]) -> None:
    rows["WEIRD"] = _low_row(roic="n/a", piotroski_f="unknown")  # 문자열 값
    r = sco.score_category("LOW", ["WEIRD"])
    assert isinstance(r, ScoringResult)  # raise 안 함 — 문자열 metric 은 중립 처리
    assert r.scores and 0.0 <= r.scores[0].score <= 100.0
