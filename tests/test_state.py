"""state.py — JSON persistence 라운드트립 + degrade."""

from __future__ import annotations

from aegisvest import state
from aegisvest.config import get_settings
from aegisvest.schemas import CrisisState, RegimeHistoryPoint


def test_load_model_missing_returns_none() -> None:
    assert state.load_model("nope.json", CrisisState) is None


def test_model_roundtrip() -> None:
    state.save_model("cs.json", CrisisState(active=True, triggered_date="2026-09-01"))
    got = state.load_model("cs.json", CrisisState)
    assert got is not None and got.active and got.triggered_date == "2026-09-01"


def test_list_roundtrip() -> None:
    pts = [RegimeHistoryPoint(date="2026-09-01", total_score=3)]
    state.save_list("h.json", pts)
    got = state.load_list("h.json", RegimeHistoryPoint)
    assert [p.model_dump() for p in got] == [p.model_dump() for p in pts]


def _write_raw(name: str, text: str) -> None:
    d = get_settings().state_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)


def test_corrupt_model_degrades_to_none() -> None:
    _write_raw("bad.json", "{not json")
    assert state.load_model("bad.json", CrisisState) is None


def test_corrupt_list_degrades_to_empty() -> None:
    _write_raw("badlist.json", "[[[")
    assert state.load_list("badlist.json", RegimeHistoryPoint) == []
