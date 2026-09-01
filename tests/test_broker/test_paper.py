"""broker/paper.py — 모의투자 원장."""

from __future__ import annotations

import pytest

from aegisvest.broker import paper
from aegisvest.schemas import Order, PaperPortfolio


@pytest.fixture(autouse=True)
def _costs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_COMMISSION_PCT", "0.001")
    monkeypatch.setenv("PAPER_FX_SPREAD_PCT", "0.005")
    paper.get_settings.cache_clear()


def test_contribution_applies_fx_spread() -> None:
    pf = PaperPortfolio()
    c = paper.add_contribution(pf, krw=1_407_000, fx_rate_base=1400.0, date="2026-09-07")
    assert c.fx_rate == pytest.approx(1407.0)  # 1400 * 1.005
    assert c.usd == pytest.approx(1000.0, abs=0.01)
    assert pf.cash_usd == pytest.approx(1000.0, abs=0.01)


def test_buy_updates_position_and_cash() -> None:
    pf = PaperPortfolio(cash_usd=1000.0)
    res = paper.execute(
        pf, [Order(ticker="AAPL", side="buy", notional_usd=400.0, category="MID")], {"AAPL": 200.0}
    )
    assert res.fills[0].shares == pytest.approx(2.0)
    assert res.fills[0].commission_usd == pytest.approx(0.4)
    assert pf.cash_usd == pytest.approx(1000.0 - 400.0 - 0.4)
    assert pf.positions["AAPL"].shares == pytest.approx(2.0)
    assert pf.positions["AAPL"].category == "MID"


def test_buy_shrinks_to_available_cash() -> None:
    pf = PaperPortfolio(cash_usd=100.0)
    res = paper.execute(pf, [Order(ticker="AAPL", side="buy", notional_usd=400.0)], {"AAPL": 200.0})
    assert res.fills[0].notional_usd <= 100.0
    assert pf.cash_usd >= -1e-6  # 현금 전액 소진 시 부동소수 잔차 허용


def test_avg_cost_averaging() -> None:
    pf = PaperPortfolio(cash_usd=1000.0)
    paper.execute(pf, [Order(ticker="X", side="buy", shares=1.0)], {"X": 100.0})
    paper.execute(pf, [Order(ticker="X", side="buy", shares=1.0)], {"X": 200.0})
    assert pf.positions["X"].avg_cost_usd == pytest.approx(150.0)


def test_sell_reduces_and_removes_at_zero() -> None:
    pf = PaperPortfolio(cash_usd=1000.0)
    paper.execute(pf, [Order(ticker="X", side="buy", shares=2.0)], {"X": 100.0})
    paper.execute(pf, [Order(ticker="X", side="sell", shares=1.0)], {"X": 110.0})
    assert pf.positions["X"].shares == pytest.approx(1.0)
    paper.execute(
        pf, [Order(ticker="X", side="sell", shares=5.0)], {"X": 110.0}
    )  # 초과 매도 → 보유만큼
    assert "X" not in pf.positions


def test_sells_execute_before_buys() -> None:
    pf = PaperPortfolio(cash_usd=10.0)
    paper.execute(pf, [Order(ticker="OLD", side="buy", shares=1.0)], {"OLD": 5.0})
    pf.cash_usd = 1.0
    res = paper.execute(
        pf,
        [
            Order(ticker="NEW", side="buy", notional_usd=90.0),
            Order(ticker="OLD", side="sell", shares=1.0),
        ],
        {"OLD": 100.0, "NEW": 50.0},
    )
    assert any(f.ticker == "NEW" and f.side == "buy" for f in res.fills)  # 매도 대금으로 매수 가능


def test_missing_price_skipped() -> None:
    pf = PaperPortfolio(cash_usd=1000.0)
    res = paper.execute(pf, [Order(ticker="NOPX", side="buy", notional_usd=100.0)], {})
    assert res.skipped == ["NOPX"]
    assert res.fills == []


def test_mark_to_market_appends_and_updates() -> None:
    pf = PaperPortfolio(cash_usd=500.0)
    paper.execute(pf, [Order(ticker="X", side="buy", shares=1.0)], {"X": 100.0})
    paper.mark_to_market(pf, {"X": 120.0}, "2026-09-08", 1400.0)
    assert pf.history[-1].nav_usd == pytest.approx(pf.cash_usd + 120.0)
    assert pf.history[-1].nav_krw == pytest.approx((pf.cash_usd + 120.0) * 1400.0)
    paper.mark_to_market(pf, {"X": 130.0}, "2026-09-08", 1400.0)  # 같은 날 → 갱신
    assert len(pf.history) == 1
    assert pf.history[-1].nav_usd == pytest.approx(pf.cash_usd + 130.0)
