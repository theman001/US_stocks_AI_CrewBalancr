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
    ToolError,
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


def test_first_run_ramp_up_respects_10pp_throttle() -> None:
    # prior = 현재 카테고리 비중(current_cat_usd/nav). 빈 포트 첫 배분은 카테고리당 ≤ 10%p.
    pf = PaperPortfolio(cash_usd=1000.0)
    res = pipeline.run_pipeline(portfolio=pf, pending_contribution_usd=0.0)
    assert res.draft.prior_category_weights  # 채워짐 (게이트가 실제로 돌 수 있게)
    changes = {
        c: abs(
            res.sizing.category_weights.get(c, 0.0) - res.draft.prior_category_weights.get(c, 0.0)
        )
        for c in ("low", "mid", "high")
    }
    assert all(ch <= 0.11 for ch in changes.values())  # 스로틀 10%p + 구조적 여유
    assert res.constraints.verdict == "PASS"  # 절대 가드레일·변동상한 모두 통과


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


def test_absolute_guardrail_fail_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # 절대 가드레일 위반(툴 버그 시뮬) → run_pipeline 은 조용히 반환하면 안 됨
    monkeypatch.setattr(
        pipeline,
        "check_constraints",
        lambda _d: ConstraintResult(
            verdict="FAIL",
            violations=[ConstraintViolation(rule="sector_cap", detail="Tech 35%", value=0.35)],
        ),
    )
    with pytest.raises(RuntimeError, match="절대 가드레일 위반"):
        pipeline.run_pipeline(portfolio=PaperPortfolio(), pending_contribution_usd=100.0)


def test_max_change_fail_is_note_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # max_change_per_rebal 은 rate 정책 — 구조적 초과(screen 결측 등)는 체결 진행 + note
    monkeypatch.setattr(
        pipeline,
        "check_constraints",
        lambda _d: ConstraintResult(
            verdict="FAIL",
            violations=[
                ConstraintViolation(rule="max_change_per_rebal", detail="mid 42%p", value=42.0)
            ],
        ),
    )
    res = pipeline.run_pipeline(portfolio=PaperPortfolio(), pending_contribution_usd=100.0)
    assert res.constraints.verdict == "FAIL"  # 리포트엔 남음
    assert any("리밸 변동상한 초과" in n for n in res.notes)  # 운영자에게 가시화


def test_screen_outage_zeroes_held_category_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 실 시나리오: 포트가 mid 를 크게 물었는데 그 주 mid 스크린이 데이터 결측 → category 0
    # → max_change_per_rebal 실제 위반. 소프트 조건이므로 체결 진행해야 (크래시 금지).
    def _screen_mid_down(cat: str, universe: str = "combined", limit: int | None = None):
        if cat.upper() == "MID":
            return ToolError(error="yfinance 결측", field="mid")
        return _screen(cat, universe, limit)

    monkeypatch.setattr(pipeline, "screen", _screen_mid_down)
    pf = PaperPortfolio(
        cash_usd=100.0,
        positions={"MZ": PaperPosition(shares=6.0, avg_cost_usd=50.0, category="mid")},
    )
    res = pipeline.run_pipeline(portfolio=pf, pending_contribution_usd=0.0)  # raise 안 함
    assert res.sizing.category_weights.get("mid", 0.0) == 0.0  # mid 비워짐
    assert any("변동상한" in n or "screen(mid)" in n for n in res.notes)


def test_crisis_snaps_high_to_zero() -> None:
    res = pipeline.run_pipeline(
        portfolio=PaperPortfolio(),
        pending_contribution_usd=1000.0,
        macro=macro(vix=40.0, vix_1d_change_pct=0.6, hy_oas_bp=800.0),
    )
    assert res.regime.crisis_active
    assert res.allocation.category_targets_total["high"] == pytest.approx(0.0)
    assert res.allocation.equity_sleeve_pct == pytest.approx(0.50)
