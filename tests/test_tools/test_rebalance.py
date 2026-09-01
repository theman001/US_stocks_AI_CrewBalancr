"""rebalance.py — TEST_GUIDE 시나리오 5 (현금흐름 리밸런싱)."""

from __future__ import annotations

import pytest

from aegisvest.schemas import RebalancePlan, ToolError
from aegisvest.tools.rebalance import cash_flow_rebalance

# 전체 포트 목표: low 45% / mid 30% / high 15% (cash 10%)
_T = {"low": 0.45, "mid": 0.30, "high": 0.15}


def test_new_cash_fills_underweight_no_sell() -> None:
    # NAV 10000. low 부족(4000 vs 4500), 나머지 목표 근처. 입금 800.
    plan = cash_flow_rebalance(
        _T, {"low": 4000, "mid": 2900, "high": 1400}, cash_usd=100, pending_contribution_usd=800
    )
    assert isinstance(plan, RebalancePlan)
    assert plan.sell_needed is False
    assert any(o.category == "low" for o in plan.buys_from_new_cash)
    assert plan.post_action_weights["low"] > 0.40


def test_sell_when_still_outside_band_after_cash() -> None:
    # high 크게 과대(2500 = 25%), 입금 0 → 매수 불가 → 매도
    plan = cash_flow_rebalance(
        _T, {"low": 4000, "mid": 3000, "high": 2500}, cash_usd=500, pending_contribution_usd=0
    )
    assert plan.sell_needed is True
    assert plan.sell_orders[0].category == "high"
    assert plan.post_action_weights["high"] == pytest.approx(0.15, abs=0.02)


def test_cooldown_blocks_sell(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = cash_flow_rebalance(
        _T,
        {"low": 4000, "mid": 3000, "high": 2500},
        cash_usd=500,
        cooldown_state={"high": 3},  # 3 거래일 전 조정 → 10 미만 → 블록
    )
    assert "high" in plan.cooldown_blocked
    assert plan.sell_orders == []


def test_crisis_bypasses_cooldown() -> None:
    plan = cash_flow_rebalance(
        _T,
        {"low": 4000, "mid": 3000, "high": 2500},
        cash_usd=500,
        cooldown_state={"high": 3},
        crisis=True,
    )
    assert plan.cooldown_blocked == []
    assert plan.sell_needed is True


def test_max_change_caps_move() -> None:
    # high 극단 과대 (5000 = 50%), NAV 10000, max_change 10%p → 최대 $1000 매도
    plan = cash_flow_rebalance(_T, {"low": 3000, "mid": 2000, "high": 5000}, cash_usd=0)
    assert plan.sell_orders[0].amount_usd == pytest.approx(1000.0, abs=1.0)


def test_deployable_respects_cash_floor() -> None:
    # cash 1000, NAV 10000, floor 3% = 300 → deployable = 700 (+ pending)
    plan = cash_flow_rebalance(
        _T, {"low": 3000, "mid": 3000, "high": 3000}, cash_usd=1000, pending_contribution_usd=200
    )
    assert plan.new_cash_deployable_usd == pytest.approx(894.0)  # NAV 10200, floor 306


def test_post_weights_sum_to_one() -> None:
    plan = cash_flow_rebalance(
        _T, {"low": 4000, "mid": 2500, "high": 1200}, cash_usd=100, pending_contribution_usd=500
    )
    assert sum(plan.post_action_weights.values()) == pytest.approx(1.0, abs=0.001)


def test_missing_target_key() -> None:
    r = cash_flow_rebalance({"low": 0.5, "mid": 0.5}, {"low": 100}, cash_usd=0)
    assert isinstance(r, ToolError)
    assert r.field == "targets_total"


def test_zero_nav() -> None:
    r = cash_flow_rebalance(_T, {}, cash_usd=0, pending_contribution_usd=0)
    assert isinstance(r, ToolError)
