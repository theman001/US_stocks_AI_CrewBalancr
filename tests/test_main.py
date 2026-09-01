"""main.py — 주간 크루 오케스트레이션 (mock: pipeline / fx / prices / crew)."""

from __future__ import annotations

import datetime as dt

import pytest

import aegisvest.agents.crew as crew_mod
from aegisvest import main, state
from aegisvest.schemas import (
    CIODecision,
    Contribution,
    CrewOutcome,
    CrisisFlag,
    FundamentalNotes,
    MacroBrief,
    MarketNarrative,
    Order,
    PaperPortfolio,
    RegimeHistoryPoint,
    ResearchView,
    ThematicNotes,
)
from tests.fixtures.pipeline import make_pipeline_result, market_data_stub


@pytest.fixture(autouse=True)
def _mock_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "usd_krw", lambda: 1400.0)
    monkeypatch.setattr(main, "market_data", market_data_stub)
    monkeypatch.setattr(main, "latest_close_date", lambda ttl: "2026-09-01")


def _pipeline(**kw: object):
    pr = make_pipeline_result()
    pr.orders = [Order(ticker="L0", side="buy", notional_usd=30.0, category="low")]
    pr.prices = {"L0": 100.0, "M0": 100.0}
    return pr


def _crew(verdict: str = "APPROVED") -> CrewOutcome:
    return CrewOutcome(
        run_id="x",
        macro_brief=MacroBrief(regime="BULL", confidence="high"),
        fundamental_notes=FundamentalNotes(),
        thematic_notes=ThematicNotes(),
        market_narrative=MarketNarrative(weekly_summary="ok"),
        research_view=ResearchView(),
        cio=CIODecision(
            verdict=verdict, ic_memo="memo", hold_reason="CRISIS" if verdict == "HOLD" else None
        ),
    )


def test_first_run_contributes_and_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", _pipeline)
    res = main.run()
    assert res.contribution_usd > 0  # 첫 실행 → 적금 납입
    assert res.n_fills >= 1
    assert res.crew_ran is False  # 개발환경 DEEPSEEK 키 없음
    pf = state.load_model("paper_portfolio.json", PaperPortfolio)
    assert pf is not None and pf.history and pf.positions


def test_second_run_same_month_no_double_contribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", _pipeline)
    main.run()
    res2 = main.run()
    assert res2.contribution_usd == 0.0


def test_cio_hold_skips_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    main.get_settings.cache_clear()
    monkeypatch.setattr(main, "run_pipeline", _pipeline)

    monkeypatch.setattr(crew_mod, "run_crew", lambda pr, run_id: _crew("HOLD"))
    res = main.run()
    assert res.held is True
    assert res.n_fills == 0
    assert res.cio_verdict == "HOLD"
    # 납입은 HOLD 여도 발생 (실제 입금)
    assert res.contribution_usd > 0


def test_crisis_trigger_run(monkeypatch: pytest.MonkeyPatch) -> None:
    # crisis_flag 는 감시견 소관 — main 은 읽지도 쓰지도 않는다
    state.save_model(
        "crisis_flag.json", CrisisFlag(active=True, reason="VIX", detected_at="2026-09-01")
    )
    monkeypatch.setattr(main, "run_pipeline", _pipeline)
    res = main.run(trigger="crisis")
    assert res.trigger == "crisis"
    flag = state.load_model("crisis_flag.json", CrisisFlag)
    assert flag is not None and flag.active is True


def test_regime_history_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", _pipeline)
    res = main.run()

    hist = state.load_list("regime_history.json", RegimeHistoryPoint)
    assert hist and hist[-1].total_score == 6
    assert res.report_path.endswith("report.md")


def test_contribution_due_logic() -> None:
    pf = PaperPortfolio()
    assert main._contribution_due(pf, dt.date(2026, 9, 6)) is True

    pf.contributions.append(Contribution(date="2026-09-01", krw=100000, usd=71.0, fx_rate=1407.0))
    assert main._contribution_due(pf, dt.date(2026, 9, 20)) is False
    assert main._contribution_due(pf, dt.date(2026, 10, 1)) is True
