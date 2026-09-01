"""allocation.py — 보간·CRISIS·nav_tier (phase-2 §2.2)."""

from __future__ import annotations

import pytest

from aegisvest.schemas import AllocationTargets, ToolError
from aegisvest.tools.allocation import allocation_targets


def test_anchor_exact_score_zero() -> None:
    a = allocation_targets(0.0, mode="paper")
    assert isinstance(a, AllocationTargets)
    assert a.equity_sleeve_pct == pytest.approx(0.85)
    assert a.cash_pct == pytest.approx(0.15)
    assert a.category_targets_sleeve == pytest.approx({"low": 0.55, "mid": 0.32, "high": 0.13})
    # 전체 포트 = sleeve x sleeve비중
    assert a.category_targets_total["low"] == pytest.approx(0.4675)
    assert a.category_targets_total["mid"] == pytest.approx(0.272)


def test_linear_interpolation_midpoint() -> None:
    # score +2 → 앵커 0 과 4 의 중간
    a = allocation_targets(2.0, mode="paper")
    assert a.interp_anchors == [0, 4]
    # sleeve: (85 + 90) / 2 = 87.5
    assert a.equity_sleeve_pct == pytest.approx(0.875)


def test_clamp_beyond_range() -> None:
    assert allocation_targets(20.0, mode="paper").interp_anchors == [12, 12]
    assert allocation_targets(-20.0, mode="paper").interp_anchors == [-12, -12]


def test_crisis_snaps_to_min_anchor() -> None:
    a = allocation_targets(8.0, crisis=True, mode="paper")
    assert a.crisis is True
    assert a.equity_sleeve_pct == pytest.approx(0.50)
    assert a.category_targets_total["high"] == 0.0


def test_high_abs_cap_enforced() -> None:
    # score +12 → high sleeve 20% x sleeve 95% = 19% (< 20% cap, OK)
    a = allocation_targets(12.0, mode="paper")
    assert a.category_targets_total["high"] <= 0.20 + 1e-9


def test_paper_vs_live_max_positions() -> None:
    assert allocation_targets(0.0, mode="paper").max_positions == {"low": 20, "mid": 15, "high": 15}
    small = allocation_targets(0.0, nav_usd=5000.0, mode="live")
    assert small.max_positions == {"low": 5, "mid": 4, "high": 3}
    big = allocation_targets(0.0, nav_usd=50000.0, mode="live")
    assert big.max_positions == {"low": 20, "mid": 15, "high": 15}


def test_bad_mode() -> None:
    r = allocation_targets(0.0, mode="turbo")
    assert isinstance(r, ToolError)
    assert r.field == "mode"
