"""watchdog.py — 일일 감시견 로직 (mock macro_data, capture 알림)."""

from __future__ import annotations

import pytest

from aegisvest import state, watchdog
from aegisvest.schemas import CrisisFlag, CrisisState, MacroData, RegimeHistoryPoint
from tests.fixtures.macro import macro


@pytest.fixture(autouse=True)
def _no_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """감시견 로직만 테스트 — NAV 마킹·위기 트리거(네트워크·크루)는 no-op."""
    monkeypatch.setattr(watchdog, "_mark_nav", lambda _d: None)
    monkeypatch.setattr(watchdog, "_trigger_weekly_crew", lambda: None)


@pytest.fixture
def alerts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(watchdog, "post", lambda text, **_kw: captured.append(text) or True)
    return captured


def _patch_macro(monkeypatch: pytest.MonkeyPatch, m: MacroData) -> None:
    monkeypatch.setattr(watchdog, "macro_data", lambda: m)


def test_normal_run_persists_history_and_state(
    monkeypatch: pytest.MonkeyPatch, alerts: list[str]
) -> None:
    _patch_macro(monkeypatch, macro(as_of="2026-09-01"))
    watchdog.run()
    hist = state.load_list("regime_history.json", RegimeHistoryPoint)
    assert len(hist) == 1 and hist[0].date == "2026-09-01"
    assert state.load_model("crisis_state.json", CrisisState) is not None
    assert alerts == []  # 위기 아님


@pytest.mark.usefixtures("alerts")
def test_same_day_updates_not_appends(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_macro(monkeypatch, macro(as_of="2026-09-01"))  # 중립 → total 0
    watchdog.run()
    _patch_macro(monkeypatch, macro(as_of="2026-09-01", vix=12.0, vix3m=20.0))  # vix +2
    watchdog.run()
    hist = state.load_list("regime_history.json", RegimeHistoryPoint)
    assert len(hist) == 1
    assert hist[0].total_score == 2  # 재실행이 값을 덮어씀


@pytest.mark.usefixtures("alerts")
def test_next_day_appends(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_macro(monkeypatch, macro(as_of="2026-09-01"))
    watchdog.run()
    _patch_macro(monkeypatch, macro(as_of="2026-09-02"))
    watchdog.run()
    hist = state.load_list("regime_history.json", RegimeHistoryPoint)
    assert [h.date for h in hist] == ["2026-09-01", "2026-09-02"]


@pytest.mark.usefixtures("alerts")
def test_low_confidence_day_not_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_macro(
        monkeypatch,
        macro(
            as_of="2026-09-01",
            yc_10y_3m_bp=None,
            hy_oas_bp=None,
            wei=None,
            regional_fed_mfg_avg=None,
            claims_4w_trend_pct=None,
            pct_above_200dma=None,
        ),
    )
    result = watchdog.run()
    assert result.low_confidence is True
    assert state.load_list("regime_history.json", RegimeHistoryPoint) == []
    assert state.load_model("crisis_state.json", CrisisState) is not None


def test_crisis_sets_flag_and_alerts(monkeypatch: pytest.MonkeyPatch, alerts: list[str]) -> None:
    _patch_macro(monkeypatch, macro(as_of="2026-09-01", vix=40.0, vix3m=45.0))
    result = watchdog.run()
    assert result.crisis_active is True
    flag = state.load_model("crisis_flag.json", CrisisFlag)
    assert flag is not None and flag.active is True
    assert any("CRISIS 발동" in a for a in alerts)


def test_crisis_alert_not_repeated(monkeypatch: pytest.MonkeyPatch, alerts: list[str]) -> None:
    _patch_macro(monkeypatch, macro(as_of="2026-09-01", vix=40.0, vix3m=45.0))
    watchdog.run()
    _patch_macro(monkeypatch, macro(as_of="2026-09-02", vix=41.0, vix3m=45.0))
    watchdog.run()
    assert sum("CRISIS 발동" in a for a in alerts) == 1  # 최초 1회만


def test_crisis_clears_and_alerts(monkeypatch: pytest.MonkeyPatch, alerts: list[str]) -> None:
    _patch_macro(monkeypatch, macro(as_of="2026-09-01", vix=40.0, vix3m=45.0))
    watchdog.run()
    # 조건 해소 + 충분히 경과 (triggered 9-01, now 9-10)
    _patch_macro(monkeypatch, macro(as_of="2026-09-10"))
    watchdog.run()
    flag = state.load_model("crisis_flag.json", CrisisFlag)
    assert flag is not None and flag.active is False
    assert any("CRISIS 해제" in a for a in alerts)


@pytest.mark.usefixtures("alerts")
def test_history_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    seed = [RegimeHistoryPoint(date=f"2026-07-{d:02d}", total_score=1) for d in range(1, 30)]
    state.save_list("regime_history.json", seed)
    _patch_macro(monkeypatch, macro(as_of="2026-09-01"))
    for i in range(20):
        _patch_macro(monkeypatch, macro(as_of=f"2026-09-{i + 1:02d}"))
        watchdog.run()
    hist = state.load_list("regime_history.json", RegimeHistoryPoint)
    assert len(hist) <= watchdog._MAX_HISTORY
