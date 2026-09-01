"""constraints.py — TEST_GUIDE 시나리오 4 (배분 가드레일, 필수)."""

from __future__ import annotations

from aegisvest.schemas import DraftPortfolio, Position
from aegisvest.tools.constraints import check_constraints


def _dp(**kw: object) -> DraftPortfolio:
    base: dict[str, object] = {
        "category_weights": {"low": 0.46, "mid": 0.27, "high": 0.12, "cash": 0.15},
        "positions": [],
    }
    base.update(kw)
    return DraftPortfolio(**base)  # type: ignore[arg-type]


def test_clean_portfolio_passes() -> None:
    r = check_constraints(_dp())
    assert r.verdict == "PASS"
    assert r.violations == []


def test_high_abs_cap_violation() -> None:
    r = check_constraints(
        _dp(category_weights={"low": 0.40, "mid": 0.25, "high": 0.22, "cash": 0.13})
    )
    assert r.verdict == "FAIL"
    assert any(v.rule == "high_abs_cap" for v in r.violations)


def test_high_exactly_at_cap_passes() -> None:
    r = check_constraints(
        _dp(category_weights={"low": 0.40, "mid": 0.27, "high": 0.20, "cash": 0.13})
    )
    assert not any(v.rule == "high_abs_cap" for v in r.violations)


def test_cash_floor_violation() -> None:
    r = check_constraints(
        _dp(category_weights={"low": 0.50, "mid": 0.30, "high": 0.18, "cash": 0.02})
    )
    assert any(v.rule == "cash_floor" for v in r.violations)


def test_single_name_cap() -> None:
    r = check_constraints(_dp(positions=[Position(ticker="NVDA", category="HIGH", weight=0.09)]))
    assert any(v.rule == "single_name_cap" and "NVDA" in v.detail for v in r.violations)


def test_sector_cap() -> None:
    pos = [
        Position(ticker="AAPL", category="MID", weight=0.06, sector="Technology"),
        Position(ticker="MSFT", category="MID", weight=0.07, sector="Technology"),
        Position(ticker="NVDA", category="HIGH", weight=0.07, sector="Technology"),
        Position(ticker="AVGO", category="HIGH", weight=0.06, sector="Technology"),
        Position(ticker="CRM", category="MID", weight=0.06, sector="Technology"),
    ]
    r = check_constraints(_dp(positions=pos))  # 0.32 > 0.30
    assert any(v.rule == "sector_cap" for v in r.violations)


def test_weights_sum() -> None:
    r = check_constraints(
        _dp(category_weights={"low": 0.5, "mid": 0.3, "high": 0.15, "cash": 0.10})
    )
    assert any(v.rule == "weights_sum" for v in r.violations)  # 1.05


def test_max_change_per_rebal() -> None:
    r = check_constraints(
        _dp(prior_category_weights={"low": 0.30, "mid": 0.27, "high": 0.12})  # low +16%p
    )
    assert any(v.rule == "max_change_per_rebal" for v in r.violations)


def test_no_prior_skips_change_check() -> None:
    r = check_constraints(_dp())  # prior 없음
    assert not any(v.rule == "max_change_per_rebal" for v in r.violations)
