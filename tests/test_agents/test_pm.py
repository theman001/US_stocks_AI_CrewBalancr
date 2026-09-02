"""agents/pm.py — PM 틸트 하드 클램프."""

from __future__ import annotations

import pytest

from aegisvest.agents.pm import clamp_pm_draft, eligible_pool
from aegisvest.schemas import PMDraft, Position, ScoredTicker, ScoringResult

_MAXP = {"low": 20, "mid": 15, "high": 15}


def _scoring(prefix: str, n: int, cat: str) -> ScoringResult:
    return ScoringResult(
        category=cat.upper(),
        scores=[
            ScoredTicker(
                ticker=f"{prefix}{i}", score=90.0 - i, rank=i + 1, subtier=None, component_scores={}
            )
            for i in range(n)
        ],
        errored=[],
        as_of="2026-09-01",
    )


_SCORING = {
    "low": _scoring("L", 30, "low"),
    "mid": _scoring("M", 25, "mid"),
    "high": _scoring("H", 10, "high"),
}
_DET = {"low": 0.40, "mid": 0.35, "high": 0.15}


def _pm(pos: list[tuple[str, str, float]]) -> PMDraft:
    return PMDraft(
        category_weights={},
        positions=[Position(ticker=t, category=c, weight=w) for t, c, w in pos],
        tilt_rationale="test",
    )


def test_eligible_pool_size() -> None:
    pool = eligible_pool(_SCORING, _MAXP)
    assert pool["L0"] == "low"
    assert len([t for t, c in pool.items() if c == "high"]) == 10  # min(15*1.5, 10)
    assert len([t for t, c in pool.items() if c == "low"]) == 30  # 20*1.5=30


def test_category_tilt_clamped_to_3pp() -> None:
    # PM 이 low 를 60% 로 밀어붙임 → 목표 40% + 3%p = 43% 로 클램프
    pm = _pm([("L0", "low", 0.30), ("L1", "low", 0.30)])
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=[], nav_usd=10_000
    )
    assert r.category_weights["low"] <= 0.43 + 1e-6
    assert any("±3%p" in n for n in r.notes)


def test_ticker_outside_pool_dropped() -> None:
    pm = _pm([("L0", "low", 0.05), ("ZZZ", "low", 0.05)])  # ZZZ 풀 밖
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=[], nav_usd=1000
    )
    assert {p.ticker for p in r.positions} == {"L0"}
    assert any("풀밖" in n for n in r.notes)


def test_excluded_ticker_forced_out() -> None:
    pm = _pm([("L0", "low", 0.04), ("L1", "low", 0.04)])
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=["L1"], nav_usd=1000
    )
    assert {p.ticker for p in r.positions} == {"L0"}


def test_tier_band_and_single_name_cap() -> None:
    pm = _pm([("L0", "low", 0.20)])  # 단일 종목 20% → 밴드 상한 6% / 단일캡 8% 로
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=[], nav_usd=1000
    )
    assert r.positions[0].weight <= 0.06 + 1e-6


def test_high_abs_cap_enforced() -> None:
    pm = _pm([(f"H{i}", "high", 0.025) for i in range(10)])  # 10 x 2.5% = 25% > 20% 캡
    r = clamp_pm_draft(
        pm,
        det_targets={"low": 0, "mid": 0, "high": 0.20},
        scoring=_SCORING,
        max_positions=_MAXP,
        excluded=[],
        nav_usd=1000,
    )
    assert sum(p.weight for p in r.positions if p.category == "high") <= 0.20 + 1e-6


def test_cash_floor_and_sum() -> None:
    pm = _pm([("L0", "low", 0.04), ("M0", "mid", 0.04), ("H0", "high", 0.02)])
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=[], nav_usd=1000
    )
    assert r.category_weights["cash"] >= 0.03 - 1e-9
    assert sum(r.category_weights.values()) == pytest.approx(1.0, abs=1e-4)


def test_uppercase_category_normalized_not_dropped() -> None:
    pm = _pm([("L0", "LOW", 0.04), ("M0", "Mid", 0.04)])  # LLM 이 대문자로
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=[], nav_usd=1000
    )
    assert {p.ticker for p in r.positions} == {"L0", "M0"}
    assert all(p.category in ("low", "mid", "high") for p in r.positions)


def test_duplicate_ticker_deduped() -> None:
    pm = _pm([("L0", "low", 0.03), ("L0", "low", 0.05), ("L1", "low", 0.03)])
    r = clamp_pm_draft(
        pm, det_targets=_DET, scoring=_SCORING, max_positions=_MAXP, excluded=[], nav_usd=1000
    )
    assert [p.ticker for p in r.positions].count("L0") == 1


def test_sector_cap_enforced() -> None:
    pm = PMDraft(
        category_weights={},
        positions=[
            Position(ticker=f"L{i}", category="low", weight=0.06, sector="Technology")
            for i in range(6)
        ],  # 6 x 6% = 36% Tech > 30% 섹터캡
        tilt_rationale="t",
    )
    r = clamp_pm_draft(
        pm,
        det_targets={"low": 0.40, "mid": 0, "high": 0},
        scoring=_SCORING,
        max_positions=_MAXP,
        excluded=[],
        nav_usd=1000,
    )
    tech = sum(p.weight for p in r.positions if p.sector == "Technology")
    assert tech <= 0.30 + 1e-6
    assert any("섹터" in n for n in r.notes)
