"""PositionSizer — 카테고리 예산 → 종목 비중. report/phase-1 §B-3.1."""

from __future__ import annotations

import pytest

from aegisvest.schemas import ScoredTicker
from aegisvest.tools import portfolio_math as mod
from aegisvest.tools.portfolio_math import size_positions

_MAXP = {"low": 20, "mid": 15, "high": 15}


def _st(t: str, s: float) -> ScoredTicker:
    return ScoredTicker(ticker=t, score=s, rank=0, subtier=None, component_scores={})


@pytest.fixture(autouse=True)
def _no_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """섹터/ATR 조회를 네트워크 없이 — 기본은 전부 None (균등 폴백)."""

    def _no_sectors(ts: list[str]) -> dict[str, str | None]:
        return dict.fromkeys(ts)

    monkeypatch.setattr(mod, "_sectors", _no_sectors)
    monkeypatch.setattr(mod, "_atr_pct", lambda ts: {})


def _pool(prefix: str, n: int) -> list[ScoredTicker]:
    return [_st(f"{prefix}{i}", 90.0 - i) for i in range(n)]


def test_equal_weight_low_mid_within_band() -> None:
    scored = {"low": _pool("L", 20), "mid": _pool("M", 15), "high": []}
    r = size_positions({"low": 0.4675, "mid": 0.272, "high": 0.0}, scored, _MAXP, nav_usd=10_000)
    assert not isinstance(r, type(size_positions)) and hasattr(r, "positions")
    lows = [p for p in r.positions if p.category == "low"]
    assert len(lows) == int(0.4675 / 0.03)  # 하한 우선: 15종목
    assert all(abs(p.weight - lows[0].weight) < 1e-9 for p in lows)  # 균등
    assert all(0.03 - 1e-9 <= p.weight <= 0.06 + 1e-9 for p in lows)
    assert r.category_weights["low"] == pytest.approx(0.4675, abs=1e-4)
    assert sum(r.category_weights.values()) == pytest.approx(1.0, abs=1e-4)


def test_count_capped_by_max_positions_spills_to_cash() -> None:
    scored = {"low": _pool("L", 20), "mid": [], "high": []}
    r = size_positions(
        {"low": 0.46, "mid": 0.0, "high": 0.0}, scored, {"low": 5, "mid": 0, "high": 0}
    )
    lows = [p for p in r.positions if p.category == "low"]
    assert len(lows) == 5
    assert all(p.weight == pytest.approx(0.06) for p in lows)  # 상한 클램프
    assert r.budget_shortfall["low"] == pytest.approx(0.46 - 0.30, abs=1e-4)
    assert r.category_weights["cash"] == pytest.approx(1.0 - 0.30, abs=1e-4)


def test_high_atr_inverse_weighting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_atr_pct", lambda ts: {"H0": 0.08, "H1": 0.04, "H2": 0.04})
    scored = {"low": [], "mid": [], "high": _pool("H", 3)}
    r = size_positions({"low": 0.0, "mid": 0.0, "high": 0.05}, scored, _MAXP, nav_usd=1000)
    w = {p.ticker: p.weight for p in r.positions}
    assert w["H0"] < w["H1"]  # 변동성 큰 종목이 더 작은 포지션
    assert w["H1"] == pytest.approx(w["H2"])
    assert w["H0"] == pytest.approx(0.01) and w["H1"] == pytest.approx(0.02)
    assert all(0.01 - 1e-9 <= v <= 0.025 + 1e-9 for v in w.values())


def test_high_shortfall_spills_to_mid() -> None:
    scored = {"low": [], "mid": _pool("M", 15), "high": _pool("H", 2)}
    # high 예산 0.11, 종목 2개 x 상한 0.025 = 0.05 -> 0.06 미달분이 mid 로
    r = size_positions({"low": 0.0, "mid": 0.20, "high": 0.11}, scored, _MAXP, nav_usd=1000)
    highs = [p for p in r.positions if p.category == "high"]
    assert sum(p.weight for p in highs) == pytest.approx(0.05, abs=1e-4)
    assert r.category_weights["mid"] > 0.20  # 스필 받음
    assert any("스필" in n for n in r.notes)


def test_sector_cap_scales_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_sectors", lambda ts: dict.fromkeys(ts, "Tech"))
    scored = {"low": [], "mid": _pool("M", 10), "high": []}
    r = size_positions({"low": 0.0, "mid": 0.40, "high": 0.0}, scored, _MAXP, nav_usd=1000)
    tech = sum(p.weight for p in r.positions)
    assert tech == pytest.approx(0.30, abs=1e-4)  # 섹터캡
    assert any("sector" in n for n in r.notes)


def test_missing_category_target_errors() -> None:
    r = size_positions({"low": 0.5, "mid": 0.3}, {}, _MAXP)
    assert hasattr(r, "error") and r.field == "category_targets"
