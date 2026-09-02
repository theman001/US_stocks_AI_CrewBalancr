"""pipeline.run_pipeline — 결정론 코어 통합 (TESTING 시나리오 5 일부).

데이터 소스(macro/breadth/universe/screen/score/market_data)만 mock 하고
regime_score·allocation_targets·cash_flow_rebalance·size_positions·check_constraints·
주문생성은 실제 코드를 태운다.
"""

from __future__ import annotations

import pytest

from aegisvest import pipeline
from aegisvest.schemas import (
    ConstraintResult,
    ConstraintViolation,
    MarketData,
    PaperPortfolio,
    PaperPosition,
    ScoredTicker,
    ScoringResult,
    ScreenedTicker,
    ScreenResult,
)
from aegisvest.tools import portfolio_math
from tests.fixtures.macro import macro

_UNIVERSE = [f"T{i:02d}" for i in range(30)]


def _screen(cat: str, universe: str = "combined", limit: int | None = None) -> ScreenResult:
    # cat 별로 겹치지 않는 10종목씩
    idx = {"LOW": (0, 12), "MID": (12, 22), "HIGH": (22, 30)}[cat.upper()]
    picks = _UNIVERSE[idx[0] : idx[1]]
    return ScreenResult(
        category=cat.upper(),
        passed=[ScreenedTicker(ticker=t, passed=True, checks={}) for t in picks],
        failed_count=0,
        evaluated_count=len(picks),
        errored=[],
        as_of="2026-09-01",
    )


def _score(
    cat: str, tickers: list[str], overrides: dict[str, float] | None = None
) -> ScoringResult:
    scores = [
        ScoredTicker(ticker=t, score=90.0 - i, rank=i + 1, subtier=None, component_scores={})
        for i, t in enumerate(tickers)
    ]
    return ScoringResult(category=cat.upper(), scores=scores, errored=[], as_of="2026-09-01")


def _md(ticker: str) -> MarketData:
    return MarketData(
        ticker=ticker,
        last_price=100.0,
        sma_50=100.0,
        sma_200=95.0,
        sma_50_prev=99.0,
        sma_200_prev=94.0,
        rsi_14=55.0,
        atr_14=3.0,
        beta_60m=1.0,
        adv_20d_usd=5e7,
        rs_vs_spx_6m=0.05,
        mom_12_1=0.1,
        pct_from_52w_high=-0.05,
        vol_20d_avg=1e6,
        vol_ratio_latest=1.1,
        as_of="2026-09-01",
    )


@pytest.fixture(autouse=True)
def _mock_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "macro_data", macro)
    monkeypatch.setattr(
        pipeline,
        "market_breadth",
        lambda ts: {
            "pct_above_200dma": 55.0,
            "pct_above_200dma_4w_change": 2.0,
            "n": 20,
            "as_of": "2026-09-01",
        },
    )
    monkeypatch.setattr(pipeline, "get_universe", lambda name="combined": list(_UNIVERSE))
    monkeypatch.setattr(pipeline, "screen", _screen)
    monkeypatch.setattr(pipeline, "score_category", lambda c, t, *a, **k: _score(c, t))
    monkeypatch.setattr(pipeline, "market_data", _md)
    monkeypatch.setattr(portfolio_math, "market_data", _md)
    monkeypatch.setattr(portfolio_math, "_sectors", lambda ts: {t: f"S{hash(t) % 6}" for t in ts})


def test_first_run_all_buys_and_valid() -> None:
    res = pipeline.run_pipeline(portfolio=PaperPortfolio(), pending_contribution_usd=70.0)
    assert res.regime.regime.value == "NEUTRAL"
    assert res.nav_usd == pytest.approx(70.0)
    assert res.orders and all(o.side == "buy" for o in res.orders)
    # 신규현금 배포는 cash_flow_rebalance 상한(카테고리별 NAV 10%p) 안
    assert sum(o.notional_usd or 0.0 for o in res.orders) <= 70.0 + 1e-6
    assert res.constraints.verdict == "PASS"  # run_pipeline 이 반환했으면 항상 PASS (불변식)


def test_prior_category_weights_populated_so_max_change_gate_runs() -> None:
    # prior = post_action_weights(스로틀 계획). size_positions 가 계획에 충실하면 PASS.
    pf = PaperPortfolio(cash_usd=1000.0)
    res = pipeline.run_pipeline(portfolio=pf, pending_contribution_usd=0.0)
    assert res.draft.prior_category_weights  # 채워짐 (게이트가 실제로 돌 수 있게)
    changes = {
        c: abs(
            res.sizing.category_weights.get(c, 0.0) - res.draft.prior_category_weights.get(c, 0.0)
        )
        for c in ("low", "mid", "high")
    }
    assert all(ch <= 0.10 + 1e-4 for ch in changes.values())  # 계획↔실현 편차 ≤ 10%p
    assert res.constraints.verdict == "PASS"  # 위반이면 run_pipeline 이 raise 했을 것


def test_post_action_weights_sum_to_one() -> None:
    res = pipeline.run_pipeline(portfolio=PaperPortfolio(), pending_contribution_usd=100.0)
    paw = res.rebalance_plan.post_action_weights
    assert sum(paw.values()) == pytest.approx(1.0, abs=1e-3)


def test_sizing_category_weights_plus_cash_one() -> None:
    res = pipeline.run_pipeline(
        portfolio=PaperPortfolio(cash_usd=5000.0), pending_contribution_usd=0.0
    )
    cw = res.sizing.category_weights
    assert sum(cw.values()) == pytest.approx(1.0, abs=1e-4)
    assert cw["high"] <= 0.20 + 1e-9  # 하드 캡


def test_dropped_holding_is_sold() -> None:
    pf = PaperPortfolio(
        cash_usd=100.0,
        positions={"ZZZ": PaperPosition(shares=2.0, avg_cost_usd=50.0, category="MID")},
    )
    res = pipeline.run_pipeline(portfolio=pf, pending_contribution_usd=0.0)
    assert any(o.ticker == "ZZZ" and o.side == "sell" for o in res.orders)


def test_constraints_fail_raises_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    # 툴 버그로 위반 draft 가 나오는 상황을 시뮬 — run_pipeline 은 조용히 반환하면 안 됨

    monkeypatch.setattr(
        pipeline,
        "check_constraints",
        lambda _d: ConstraintResult(
            verdict="FAIL",
            violations=[ConstraintViolation(rule="high_abs_cap", detail="x", value=0.35)],
        ),
    )
    with pytest.raises(RuntimeError, match="하드 가드레일 위반"):
        pipeline.run_pipeline(portfolio=PaperPortfolio(), pending_contribution_usd=100.0)


def test_crisis_snaps_high_to_zero() -> None:
    res = pipeline.run_pipeline(
        portfolio=PaperPortfolio(),
        pending_contribution_usd=1000.0,
        macro=macro(vix=40.0, vix_1d_change_pct=0.6, hy_oas_bp=800.0),
    )
    assert res.regime.crisis_active
    assert res.allocation.category_targets_total["high"] == pytest.approx(0.0)
    assert res.allocation.equity_sleeve_pct == pytest.approx(0.50)
