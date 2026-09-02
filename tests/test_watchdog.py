"""watchdog.py — 일일 감시견 로직 (mock macro_data, capture 알림)."""

from __future__ import annotations

import datetime as dt

import pytest

from aegisvest import state, watchdog
from aegisvest.schemas import (
    CrisisFlag,
    CrisisState,
    MacroData,
    NavPoint,
    PaperPortfolio,
    RegimeHistoryPoint,
    ShadowState,
    ToolError,
)
from tests.fixtures.macro import macro


@pytest.fixture(autouse=True)
def _no_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """감시견 로직만 — NAV 마킹·위기 트리거는 no-op. 실 경로 (기본 dry-run 해제)."""
    monkeypatch.setenv("DRY_RUN", "false")
    watchdog.get_settings.cache_clear()
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


def test_dry_run_computes_but_persists_nothing(
    monkeypatch: pytest.MonkeyPatch, alerts: list[str]
) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    watchdog.get_settings.cache_clear()
    _patch_macro(monkeypatch, macro(as_of="2026-09-01", vix=40.0, vix3m=45.0))  # 위기 조건
    result = watchdog.run()
    assert result.crisis_active is True  # 계산은 정상
    assert state.load_list("regime_history.json", RegimeHistoryPoint) == []
    assert state.load_model("crisis_state.json", CrisisState) is None
    assert state.load_model("crisis_flag.json", CrisisFlag) is None
    assert alerts == []  # 알림 스킵


@pytest.mark.usefixtures("alerts")
def test_history_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    base = dt.date(2026, 4, 1)
    seed = [  # _MAX_HISTORY 를 넉넉히 초과하는 시드
        RegimeHistoryPoint(date=(base + dt.timedelta(days=d)).isoformat(), total_score=1)
        for d in range(watchdog._MAX_HISTORY + 25)
    ]
    state.save_list("regime_history.json", seed)
    for i in range(5):
        _patch_macro(monkeypatch, macro(as_of=f"2026-09-{i + 1:02d}"))
        watchdog.run()
    hist = state.load_list("regime_history.json", RegimeHistoryPoint)
    assert len(hist) == watchdog._MAX_HISTORY  # 정확히 상한으로 절삭


def test_mark_nav_guard_uses_marked_portfolio_and_carries_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.undo()  # _mark_nav 실제 실행 (autouse no-op 해제)
    # 부트스트랩: org 비어있고 det 가 라이브 (broker/shadow.py 문서화 상태)
    det = PaperPortfolio(
        cash_usd=100.0,
        history=[NavPoint(date="2026-09-04", nav_usd=100.0, nav_krw=133000.0)],  # 암시환율 1330
    )
    state.save_model("shadow.json", ShadowState(deterministic=det, organization=PaperPortfolio()))
    monkeypatch.setattr(watchdog, "usd_krw", lambda: ToolError(error="net", field="fx"))
    monkeypatch.setattr(watchdog, "market_data", lambda t: ToolError(error="net", field="t"))

    monkeypatch.setattr(watchdog, "_trading_day", lambda _d: "2026-09-04")  # 이미 마킹된 날
    watchdog._mark_nav("2026-09-04")
    sh = state.load_model("shadow.json", ShadowState)
    assert sh is not None and len(sh.deterministic.history) == 1  # guard 가 det 봄 → 재마킹 안 함

    monkeypatch.setattr(watchdog, "_trading_day", lambda _d: "2026-09-08")
    watchdog._mark_nav("2026-09-08")
    sh2 = state.load_model("shadow.json", ShadowState)
    assert sh2 is not None
    np_new = sh2.deterministic.history[-1]
    assert np_new.date == "2026-09-08"
    assert np_new.nav_krw / np_new.nav_usd == pytest.approx(1330.0, abs=1.0)  # 1400 폴백 아님
