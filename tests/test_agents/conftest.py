"""스크립트 LLM — DeepSeek 없이 크루를 태운다 (TESTING 시나리오 6)."""

from __future__ import annotations

from typing import Any

import pytest
from crewai.llm import BaseLLM
from pydantic import Field

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


class ScriptedLLM(BaseLLM):
    """response_model 이름 또는 태스크 expected_output 마커로 canned JSON 반환."""

    responses: dict[str, str] = Field(default_factory=dict)

    def __init__(self, responses: dict[str, str], **kw: Any) -> None:
        super().__init__(model="scripted/test", responses=responses, **kw)

    def call(self, messages: Any, *args: Any, **kwargs: Any) -> str:
        rm = kwargs.get("response_model")
        if rm is not None and rm.__name__ in self.responses:
            return self.responses[rm.__name__]
        ft = kwargs.get("from_task")
        hay = f"{ft.name or ''} {ft.expected_output or ''}" if ft is not None else ""
        for marker, payload in self.responses.items():
            if marker in hay:
                return payload
        return next(iter(self.responses.values()))

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 16000


def _md(t: str) -> MarketData:
    return MarketData(
        ticker=t,
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


def make_pipeline_result(*, crisis: bool = False, constraints_fail: bool = False) -> PipelineResult:
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
        category_targets_sleeve={"low": 0.85, "mid": 0.15, "high": 0.0}
        if crisis
        else {"low": 0.44, "mid": 0.4, "high": 0.16},
        category_targets_total={"low": 0.425, "mid": 0.075, "high": 0.0}
        if crisis
        else {"low": 0.4, "mid": 0.36, "high": 0.14},
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
            as_of="2026-09-01",
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
            as_of="2026-09-01",
        ),
        "high": ScoringResult(category="HIGH", scores=[], errored=[], as_of="2026-09-01"),
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
        as_of="2026-09-01",
    )
    draft = DraftPortfolio(
        category_weights=sizing.category_weights,
        positions=[
            Position(ticker=p.ticker, category=p.category, weight=p.weight, sector=p.sector)
            for p in sizing.positions
        ],
    )
    constraints = ConstraintResult(
        verdict="FAIL" if constraints_fail else "PASS",
        violations=[],
    )
    plan = RebalancePlan(
        new_cash_deployable_usd=70.0,
        buys_from_new_cash=[],
        sell_needed=False,
        sell_orders=[],
        cooldown_blocked=[],
        post_action_weights={"low": 0.05, "mid": 0.04, "high": 0.0, "cash": 0.91},
    )
    return PipelineResult(
        as_of="2026-09-01",
        nav_usd=1000.0,
        regime=regime,
        allocation=alloc,
        screen_counts={"low": 5, "mid": 4, "high": 0},
        scoring=scoring,
        rebalance_plan=plan,
        sizing=sizing,
        draft=draft,
        constraints=constraints,
        orders=[],
        prices={"L0": 100.0, "M0": 100.0},
        notes=[],
    )


@pytest.fixture
def pipeline_result() -> PipelineResult:
    return make_pipeline_result()
