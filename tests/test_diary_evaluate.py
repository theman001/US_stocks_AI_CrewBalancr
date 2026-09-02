"""diary/evaluate.py — 100% 결정론 채점 (TESTING 시나리오 8). 합성 데이터."""

from __future__ import annotations

import pandas as pd
import pytest

from aegisvest.diary import evaluate
from aegisvest.diary import logger as diary
from aegisvest.diary.logger import load_entries
from aegisvest.schemas import DiaryEntry, NavPoint, PaperPortfolio, RegimeHistoryPoint, ShadowState
from aegisvest.state import save_list, save_model


def _hist(navs: list[tuple[str, float]]) -> list[NavPoint]:
    return [NavPoint(date=d, nav_usd=v, nav_krw=v * 1400.0) for d, v in navs]


def _frame(prices: dict[str, float]) -> pd.DataFrame:
    idx = pd.to_datetime(sorted(prices))
    return pd.DataFrame({"Close": [prices[d] for d in sorted(prices)]}, index=idx)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evaluate, "history", lambda ticker, ttl: pd.DataFrame())


def _log_entry(**kw: object) -> str:
    e = diary.log(**kw)  # type: ignore[arg-type]
    assert hasattr(e, "id")
    return e.evaluate_after[-1]  # type: ignore[union-attr,no-any-return]


def test_allocation_tilt_hit_from_shadow_delta() -> None:
    end = _log_entry(
        run_id="2026-01-01",
        agent="PM",
        claim_type="allocation_tilt",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={"tilts_pp": {"high": -0.03}},
    )
    save_model(
        "shadow.json",
        ShadowState(
            deterministic=PaperPortfolio(history=_hist([("2026-01-01", 1000.0), (end, 1000.0)])),
            organization=PaperPortfolio(history=_hist([("2026-01-01", 1000.0), (end, 1010.0)])),
        ),
    )
    counts = evaluate.run(today=end)
    assert counts == {"evaluated": 1, "expired": 0, "not_due": 0, "queued_for_reflection": 0}
    updated = load_entries()[0]
    assert updated.status == "evaluated"
    assert updated.outcome is not None
    assert updated.outcome["verdict"] == "hit"
    assert updated.outcome["score"] >= 1
    assert updated.outcome["attribution"] == "high"


def test_not_due_yet_stays_open() -> None:
    _log_entry(
        run_id="2026-01-01",
        agent="PM",
        claim_type="allocation_tilt",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={},
    )
    counts = evaluate.run(today="2026-01-02")
    assert counts["not_due"] == 1
    assert load_entries()[0].status == "open"


def test_missing_shadow_data_expires() -> None:
    end = _log_entry(
        run_id="2026-01-01",
        agent="PM",
        claim_type="allocation_tilt",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={},
    )
    counts = evaluate.run(today=end)  # shadow.json 없음
    assert counts["expired"] == 1
    assert load_entries()[0].status == "expired"


def test_exclusion_avoiding_loser_is_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    end = _log_entry(
        run_id="2026-01-01",
        agent="Fundamental",
        claim_type="exclusion",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={"excluded": ["BADCO"], "enforced": False},
    )
    frames = {
        "BADCO": _frame({"2026-01-01": 100.0, end: 80.0}),
        "SPY": _frame({"2026-01-01": 100.0, end: 102.0}),
    }
    monkeypatch.setattr(evaluate, "history", lambda t, ttl: frames.get(t, pd.DataFrame()))
    counts = evaluate.run(today=end)
    assert counts["evaluated"] == 1
    o = load_entries()[0].outcome
    assert o is not None
    assert o["verdict"] == "hit"  # -20% 종목을 피함 (벤치마크 +2%) → 회피 성공
    assert o["excess_vs_spy_pct"] > 0


def test_catalyst_underperform_is_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    end = _log_entry(
        run_id="2026-01-01",
        agent="Thematic",
        claim_type="catalyst",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={"catalysts": [{"ticker": "MEME", "date": "2026-01-15"}]},
    )
    frames = {
        "MEME": _frame({"2026-01-01": 100.0, end: 90.0}),
        "SPY": _frame({"2026-01-01": 100.0, end: 105.0}),
    }
    monkeypatch.setattr(evaluate, "history", lambda t, ttl: frames.get(t, pd.DataFrame()))
    counts = evaluate.run(today=end)
    assert counts["evaluated"] == 1
    o = load_entries()[0].outcome
    assert o is not None
    assert o["verdict"] == "miss"


def test_event_risk_occurred_when_market_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    end = _log_entry(
        run_id="2026-01-01",
        agent="News",
        claim_type="event_risk",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={"events": [{"event": "fomc", "severity": "high"}]},
    )
    frames = {"SPY": _frame({"2026-01-01": 100.0, end: 92.0})}  # -8% > high 임계 5%
    monkeypatch.setattr(evaluate, "history", lambda t, ttl: frames.get(t, pd.DataFrame()))
    counts = evaluate.run(today=end)
    assert counts["evaluated"] == 1
    o = load_entries()[0].outcome
    assert o is not None
    assert o["occurred_proxy"] is True
    assert o["verdict"] == "hit"
    assert o["attribution"] == "low"  # 방향 미검증 — 항상 보수적


def test_regime_call_matches_history() -> None:
    end = _log_entry(
        run_id="2026-01-01",
        agent="Macro",
        claim_type="regime_call",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={"regime": "BULL", "watch_items": []},
    )
    # BULL 예측과 일치하는 고득점 이력 (config/regime_rules.yaml bull_min 이상)
    save_list(
        "regime_history.json",
        [RegimeHistoryPoint(date=d, total_score=8) for d in ("2026-01-08", "2026-02-01", end)],
    )
    counts = evaluate.run(today=end)
    assert counts["evaluated"] == 1
    o = load_entries()[0].outcome
    assert o is not None
    assert o["days_matching_ratio"] == 1.0
    assert o["verdict"] == "hit"


def test_regime_call_normalizes_freeform_and_expires_on_unknown() -> None:
    assert evaluate._normalize_regime("cautiously bullish") == "BULL"
    assert evaluate._normalize_regime("Bear (weakening)") == "BEAR"
    assert evaluate._normalize_regime("sideways chop") is None

    end = _log_entry(
        run_id="2026-01-01",
        agent="Macro",
        claim_type="regime_call",
        claim="c",
        reasoning="r",
        data_snapshot={},
        decision={"regime": "sideways chop"},  # 파싱 불가
    )
    save_list("regime_history.json", [RegimeHistoryPoint(date=end, total_score=8)])
    evaluate.run(today=end)
    assert load_entries()[0].status == "expired"  # 오채점 대신 만료


def test_needs_reflection_forced_for_miss_and_low_attribution() -> None:

    base = {
        "id": "x",
        "run_id": "2026-01-01",
        "agent": "a",
        "created_at": "2026-01-01T00:00:00Z",
        "claim_type": "exclusion",
        "claim": "c",
        "reasoning": "r",
        "horizon_weeks": 12,
    }
    miss = DiaryEntry(**base, outcome={"verdict": "miss", "score": -2, "attribution": "high"})
    low_attr = DiaryEntry(**base, outcome={"verdict": "hit", "score": 1, "attribution": "low"})
    assert evaluate.needs_reflection(miss) is True
    assert evaluate.needs_reflection(low_attr) is True


def test_needs_reflection_is_deterministic_per_entry() -> None:

    e = DiaryEntry(
        id="stable-id",
        run_id="2026-01-01",
        agent="a",
        created_at="2026-01-01T00:00:00Z",
        claim_type="exclusion",
        claim="c",
        reasoning="r",
        horizon_weeks=12,
        outcome={"verdict": "hit", "score": 2, "attribution": "high"},
    )
    assert evaluate.needs_reflection(e) == evaluate.needs_reflection(e)
