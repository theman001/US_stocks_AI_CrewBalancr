"""broker/benchmarks.py — 벤치마크 시뮬."""

from __future__ import annotations

import pytest

from aegisvest.broker import benchmarks as bm
from aegisvest.schemas import BenchmarkState


def test_contribute_splits_by_allocation() -> None:
    st = BenchmarkState()
    bm.contribute(st, 1000.0, {"SPY": 500.0, "AGG": 100.0, "ACWI": 200.0})
    assert st.holdings["spy"]["SPY"] == pytest.approx(2.0)  # 1000/500
    assert st.holdings["sixtyforty"]["SPY"] == pytest.approx(1.2)  # 600/500
    assert st.holdings["sixtyforty"]["AGG"] == pytest.approx(4.0)  # 400/100
    assert st.holdings["acwi"]["ACWI"] == pytest.approx(5.0)  # 1000/200


def test_mark_to_market_tracks_each() -> None:
    st = BenchmarkState()
    bm.contribute(st, 1000.0, {"SPY": 500.0, "AGG": 100.0, "ACWI": 200.0})
    out = bm.mark_to_market(st, {"SPY": 550.0, "AGG": 100.0, "ACWI": 210.0}, "2026-09-08", 1400.0)
    assert out["spy"].nav_usd == pytest.approx(1100.0)  # 2 * 550
    assert out["acwi"].nav_usd == pytest.approx(1050.0)  # 5 * 210
    assert st.history["spy"][-1].nav_krw == pytest.approx(1100.0 * 1400.0)


def test_same_day_updates() -> None:
    st = BenchmarkState()
    bm.contribute(st, 1000.0, {"SPY": 500.0, "AGG": 100.0, "ACWI": 200.0})
    bm.mark_to_market(st, {"SPY": 550.0, "AGG": 100.0, "ACWI": 210.0}, "2026-09-08", 1400.0)
    bm.mark_to_market(st, {"SPY": 600.0, "AGG": 100.0, "ACWI": 210.0}, "2026-09-08", 1400.0)
    assert len(st.history["spy"]) == 1
    assert st.history["spy"][-1].nav_usd == pytest.approx(1200.0)


def test_partial_pricing_skips_day() -> None:
    st = BenchmarkState()
    bm.contribute(st, 1000.0, {"SPY": 500.0, "AGG": 100.0, "ACWI": 200.0})
    out = bm.mark_to_market(st, {"SPY": 550.0, "ACWI": 210.0}, "2026-09-08", 1400.0)  # AGG 누락
    assert "sixtyforty" not in out  # AGG 없이 60/40 은 기록 안 함
    assert "sixtyforty" not in st.history
    assert out["spy"].nav_usd == pytest.approx(1100.0)


def test_bench_tickers_list() -> None:
    assert set(bm.BENCH_TICKERS) == {"SPY", "AGG", "ACWI"}
