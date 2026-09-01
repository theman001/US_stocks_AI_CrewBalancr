"""universe.py — 파일 파싱 + combined dedup."""

from __future__ import annotations

from aegisvest.tools import universe as u


def test_sp500_file_loads() -> None:
    t = u.get_universe("SP500")
    assert "AAPL" in t and "JPM" in t and len(t) > 50
    assert t == sorted(t)  # 정렬됨
    assert len(t) == len(set(t))  # 중복 없음


def test_nasdaq_file_loads() -> None:
    t = u.get_universe("NASDAQ100")
    assert "NVDA" in t and "COST" in t


def test_combined_dedup() -> None:
    combined = u.get_universe("combined")
    sp = set(u.get_universe("SP500"))
    nq = set(u.get_universe("NASDAQ100"))
    assert set(combined) == sp | nq
    assert len(combined) == len(set(combined))


def test_unknown_universe_returns_empty() -> None:
    assert u.get_universe("RUSSELL2000") == []


def test_comments_and_blanks_stripped() -> None:
    t = u.get_universe("SP500")
    assert all(x and not x.startswith("#") for x in t)
