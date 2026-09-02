"""broker/metrics.py — 성과 지표."""

from __future__ import annotations

import datetime as dt

import pytest

from aegisvest.broker.metrics import performance_stats
from aegisvest.schemas import Contribution, NavPoint


def _hist(navs: list[tuple[str, float]]) -> list[NavPoint]:
    return [NavPoint(date=d, nav_usd=v, nav_krw=v * 1400) for d, v in navs]


def test_too_short_returns_none_annualized() -> None:
    s = performance_stats(_hist([("2026-09-01", 100.0), ("2026-09-02", 101.0)]))
    assert s["cagr"] is None
    assert s["total_return"] == pytest.approx(0.01)
    assert s["mdd"] == pytest.approx(0.0)


def test_empty_history() -> None:
    s = performance_stats([])
    assert s["n_days"] == 0 and s["cagr"] is None


def test_contribution_not_counted_as_gain() -> None:
    hist = _hist([("2026-01-01", 100.0), ("2026-01-02", 150.0)])
    contribs = [Contribution(date="2026-01-02", krw=70000, usd=50.0, fx_rate=1400.0)]
    s = performance_stats(hist, contribs)
    assert s["total_return"] == pytest.approx(0.0, abs=1e-9)


def test_contribution_date_ahead_of_navpoint_still_matched() -> None:
    # 기여일이 NavPoint 날짜보다 뒤여도 (날짜 규약 어긋남) 수익으로 오인하지 않는다
    hist = _hist([("2026-01-02", 100.0), ("2026-01-09", 150.0)])
    contribs = [Contribution(date="2026-01-11", krw=70000, usd=50.0, fx_rate=1400.0)]
    s = performance_stats(hist, contribs)
    assert s["total_return"] == pytest.approx(0.0, abs=1e-9)  # 마지막 NavPoint 에 귀속


def test_full_stats_on_year_of_data() -> None:
    v = 100.0
    navs: list[tuple[str, float]] = [(str(dt.date(2026, 1, 1)), v)]
    for i in range(1, 260):
        v *= 1.0005
        navs.append((str(dt.date(2026, 1, 1) + dt.timedelta(days=i)), v))
    s = performance_stats(_hist(navs))
    assert s["cagr"] is not None and 0.10 < s["cagr"] < 0.25
    assert s["vol"] == pytest.approx(0.0, abs=1e-6)  # 등속 상승 → 변동성 0
    assert s["mdd"] == pytest.approx(0.0)


def test_drawdown() -> None:
    hist = _hist(
        [(f"2026-01-{d:02d}", v) for d, v in [(1, 100), (2, 110), (3, 90), (4, 95), (5, 105)]]
    )
    s = performance_stats(hist)
    assert s["mdd"] == pytest.approx(90 / 110 - 1.0, abs=1e-4)
