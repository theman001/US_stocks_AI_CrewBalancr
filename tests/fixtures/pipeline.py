"""합성 PipelineResult 빌더 — 크루·main·리포트 테스트 공용."""

from __future__ import annotations

from aegisvest.schemas import (
    AllocationTargets,
    ConstraintResult,
    CrisisState,
    DraftPortfolio,
    MarketData,
    PipelineResult,
    Position,
    RebalancePlan,
    Regime,
    RegimeResult,
    ScoredTicker,
    ScoringResult,
    SizedPosition,
    SizingResult,
)
from tests.fixtures.macro import macro as macro_stub


def market_data_stub(ticker: str, price: float = 100.0) -> MarketData:
    return MarketData(
        ticker=ticker,
        last_price=price,
        sma_50=price,
        sma_200=price * 0.95,
        sma_50_prev=price * 0.99,
        sma_200_prev=price * 0.94,
        rsi_14=55.0,
        atr_14=price * 0.03,
        beta_60m=1.0,
        adv_20d_usd=5e7,
        rs_vs_spx_6m=0.05,
        mom_12_1=0.1,
        pct_from_52w_high=-0.05,
        vol_20d_avg=1e6,
        vol_ratio_latest=1.1,
        as_of="2026-09-01",
    )


def make_pipeline_result(
    *, crisis: bool = False, constraints_fail: bool = False, as_of: str = "2026-09-01"
) -> PipelineResult:
    regime = RegimeResult(
        axis_scores={
            "vix": 1,
            "spx_trend": 2,
            "breadth": 1,
            "yield_policy": 0,
            "credit": 1,
            "economy": 1,
        },
        economy_subscores={"wei": 1, "regional": 0, "claims": 1},
        n_axes_present=6,
        low_confidence=False,
        total_score=-12 if crisis else 6,
        score_smooth=-12.0 if crisis else 6.0,
        regime=Regime.CRISIS if crisis else Regime.BULL,
        crisis_active=crisis,
        crisis_reason="VIX>35" if crisis else None,
        crisis_state=CrisisState(),
        rationale={"vix": "낮음", "total": "합 6"},
    )
    alloc = AllocationTargets(
        score_smooth=regime.score_smooth,
        crisis=crisis,
        equity_sleeve_pct=0.5 if crisis else 0.9,
        cash_pct=0.5 if crisis else 0.1,
        category_targets_sleeve=(
            {"low": 0.85, "mid": 0.15, "high": 0.0}
            if crisis
            else {"low": 0.44, "mid": 0.4, "high": 0.16}
        ),
        category_targets_total=(
            {"low": 0.425, "mid": 0.075, "high": 0.0}
            if crisis
            else {"low": 0.4, "mid": 0.36, "high": 0.14}
        ),
        max_positions={"low": 20, "mid": 15, "high": 15},
        interp_anchors=[-12, -8] if crisis else [4, 8],
        guardrails={"high_abs_cap": 0.2},
    )
    scoring = {
        "low": ScoringResult(
            category="LOW",
            scores=[
                ScoredTicker(
                    ticker=f"L{i}", score=90.0 - i, rank=i + 1, subtier="LOW-A", component_scores={}
                )
                for i in range(5)
            ],
            errored=[],
            as_of=as_of,
        ),
        "mid": ScoringResult(
            category="MID",
            scores=[
                ScoredTicker(
                    ticker=f"M{i}", score=80.0 - i, rank=i + 1, subtier=None, component_scores={}
                )
                for i in range(4)
            ],
            errored=[],
            as_of=as_of,
        ),
        "high": ScoringResult(category="HIGH", scores=[], errored=[], as_of=as_of),
    }
    sizing = SizingResult(
        positions=[
            SizedPosition(
                ticker="L0",
                category="low",
                weight=0.05,
                target_usd=50.0,
                score=90.0,
                sector="Healthcare",
            ),
            SizedPosition(
                ticker="M0",
                category="mid",
                weight=0.04,
                target_usd=40.0,
                score=80.0,
                sector="Technology",
            ),
        ],
        category_weights={"low": 0.05, "mid": 0.04, "high": 0.0, "cash": 0.91},
        budget_shortfall={},
        notes=[],
        as_of=as_of,
    )
    draft = DraftPortfolio(
        category_weights=sizing.category_weights,
        positions=[
            Position(ticker=p.ticker, category=p.category, weight=p.weight, sector=p.sector)
            for p in sizing.positions
        ],
    )
    plan = RebalancePlan(
        new_cash_deployable_usd=70.0,
        buys_from_new_cash=[],
        sell_needed=False,
        sell_orders=[],
        cooldown_blocked=[],
        post_action_weights={"low": 0.05, "mid": 0.04, "high": 0.0, "cash": 0.91},
    )
    mc = (
        macro_stub(
            as_of=as_of,
            vix=40.0,
            vix3m=35.0,
            hy_oas_bp=800.0,
            hy_oas_4w_change_bp=150.0,
            spx_last=88.0,  # 위기 = SPX 가 양 SMA 아래, 50<200 (death_cross)
            spx_sma_50=94.0,
            spx_sma_200=100.0,
        )
        if crisis
        else macro_stub(as_of=as_of)
    )
    return PipelineResult(
        as_of=as_of,
        nav_usd=1000.0,
        macro=mc,
        regime=regime,
        allocation=alloc,
        screen_counts={"low": 5, "mid": 4, "high": 0},
        scoring=scoring,
        rebalance_plan=plan,
        sizing=sizing,
        draft=draft,
        constraints=ConstraintResult(verdict="FAIL" if constraints_fail else "PASS", violations=[]),
        orders=[],
        prices={"L0": 100.0, "M0": 100.0},
        notes=[],
    )
