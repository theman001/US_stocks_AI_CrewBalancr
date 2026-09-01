"""판단 일기 스키마 + 로거 (TESTING 시나리오 8 일부 — 라운드트립)."""

from __future__ import annotations

import datetime as dt

from aegisvest.diary import logger as diary
from aegisvest.diary.schema import default_horizon_weeks, derive_tags, evaluate_dates
from aegisvest.schemas import DiaryEntry


def test_entry_roundtrip() -> None:
    e = diary.log(
        run_id="2026-09-06",
        agent="Macro Strategist",
        claim_type="regime_call",
        claim="레짐 BULL 유지 전망",
        reasoning="금리 안정 + 신용 양호",
        data_snapshot={"score_smooth": 6.0, "regime": "BULL"},
        decision={"regime": "BULL"},
        situation_text="[상황] 2026-09 BULL",
        tags=derive_tags(regime="BULL", claim_type="regime_call"),
    )
    assert isinstance(e, DiaryEntry)
    reloaded = diary.load_entries()
    assert len(reloaded) == 1
    assert reloaded[0].model_dump() == e.model_dump()
    assert reloaded[0].status == "open"
    assert reloaded[0].outcome is None  # Phase 4 append 대상


def test_regime_call_two_horizons() -> None:
    dates = evaluate_dates(dt.date(2026, 9, 6), "regime_call", 12)
    assert dates == ["2026-10-04", "2026-11-29"]  # +4주, +12주
    assert default_horizon_weeks("regime_call") == 12


def test_unknown_claim_type_errors() -> None:
    r = diary.log(
        run_id="2026-09-06",
        agent="X",
        claim_type="bogus",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={},
    )
    assert hasattr(r, "error") and r.field == "claim_type"


def test_bad_run_id_errors() -> None:
    r = diary.log(
        run_id="not-a-date",
        agent="X",
        claim_type="exclusion",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={},
    )
    assert hasattr(r, "error") and r.field == "run_id"


def test_append_only() -> None:
    for i in range(3):
        diary.log(
            run_id=f"2026-09-0{i + 1}",
            agent="CIO",
            claim_type="cio_override",
            claim=f"hold {i}",
            reasoning="r",
            data_snapshot={},
            decision={},
        )
    assert len(diary.load_entries()) == 3


def test_derive_tags_shape() -> None:
    tags = derive_tags(
        regime="NEUTRAL",
        claim_type="allocation_tilt",
        sleeve="high",
        action="defensive_tilt",
        magnitude="large",
        signals=("credit_spread_widening",),
    )
    assert "regime:neutral" in tags
    assert "sleeve:high" in tags
    assert "signal:credit_spread_widening" in tags
